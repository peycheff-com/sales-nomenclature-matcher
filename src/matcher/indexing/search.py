from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.config import settings
from matcher.indexing.embedder import embed_single
from matcher.pipeline.token_tracker import TokenTracker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Catalog count cache (module-level)
# ---------------------------------------------------------------------------

_catalog_count: int | None = None


async def get_catalog_count(session: AsyncSession) -> int:
    """Get the number of active catalog products, cached after first call."""
    global _catalog_count
    if _catalog_count is None:
        result = await session.execute(
            text("SELECT COUNT(*) FROM catalog_products WHERE is_active = true")
        )
        _catalog_count = result.scalar() or 0
    return _catalog_count


def invalidate_catalog_count() -> None:
    """Reset the cached catalog count. Call after import/reindex."""
    global _catalog_count
    _catalog_count = None


@dataclass
class SearchCandidate:
    """A candidate product returned by hybrid search."""

    product_id: str
    name: str
    normalized_name: str
    article: str | None = None
    brand: str | None = None
    normalized_brand: str | None = None
    manufacturer_code: str | None = None
    category_id: str | None = None
    category_path: str | None = None
    unit: str | None = None
    packaging: str | None = None
    search_document: str | None = None
    lexical_score: float = 0.0
    semantic_score: float = 0.0
    exact_match: bool = False
    rrf_score: float = 0.0
    retrieval_rank: int = 0


async def _full_catalog_search(
    session: AsyncSession,
    query_text: str,
    normalized_text: str,
    query_embedding: list[float] | None,
    rrf_k: int,
    top_n: int,
    article_hint: str | None = None,
) -> list[SearchCandidate]:
    """Rank ALL active products without filtering. For small catalogs only."""
    params: dict = {
        "query_text": normalized_text,
        "ts_query": normalized_text,
        "top_n": top_n,
        "rrf_k": rrf_k,
    }

    if article_hint:
        exact_cte = """
        exact_matches AS (
            SELECT product_id, 1 as exact_hit,
                   ROW_NUMBER() OVER (ORDER BY product_id) as rank
            FROM catalog_products
            WHERE is_active = true
              AND (article = :article_hint
                   OR code = :article_hint
                   OR manufacturer_code = :article_hint)
        )"""
        params["article_hint"] = article_hint
    else:
        exact_cte = """
        exact_matches AS (
            SELECT NULL::text as product_id, 0 as exact_hit, 0 as rank
            WHERE false
        )"""

    lexical_cte = """
    lexical_matches AS (
        SELECT product_id,
               GREATEST(
                   ts_rank(search_tsv, plainto_tsquery('russian', :ts_query)),
                   similarity(normalized_name, :query_text) * 0.8,
                   similarity(search_document, :query_text) * 0.5
               ) as lex_score,
               ROW_NUMBER() OVER (
                   ORDER BY GREATEST(
                       ts_rank(search_tsv, plainto_tsquery('russian', :ts_query)),
                       similarity(normalized_name, :query_text) * 0.8,
                       similarity(search_document, :query_text) * 0.5
                   ) DESC
               ) as rank
        FROM catalog_products
        WHERE is_active = true
        ORDER BY lex_score DESC
    )"""

    if query_embedding is not None:
        semantic_cte = """
        semantic_matches AS (
            SELECT e.product_id,
                   1 - (e.embedding_vector <=> CAST(:query_vector AS vector)) as sem_score,
                   ROW_NUMBER() OVER (
                       ORDER BY e.embedding_vector <=> CAST(:query_vector AS vector)
                   ) as rank
            FROM catalog_embeddings e
            JOIN catalog_products p ON e.product_id = p.product_id
            WHERE p.is_active = true
            ORDER BY e.embedding_vector <=> CAST(:query_vector AS vector)
        )"""
        params["query_vector"] = str(query_embedding)
    else:
        semantic_cte = """
        semantic_matches AS (
            SELECT NULL::text as product_id, 0.0::float as sem_score, 0 as rank
            WHERE false
        )"""

    sql = f"""
    WITH
    {exact_cte},
    {lexical_cte},
    {semantic_cte},
    rrf_scores AS (
        SELECT
            COALESCE(e.product_id, l.product_id, s.product_id) as product_id,
            COALESCE(e.exact_hit, 0) as exact_hit,
            COALESCE(l.lex_score, 0) as lex_score,
            COALESCE(s.sem_score, 0) as sem_score,
            CASE WHEN e.product_id IS NOT NULL THEN 1.0 / (:rrf_k + 0) ELSE 0 END
            + CASE WHEN l.product_id IS NOT NULL THEN 1.0 / (:rrf_k + l.rank) ELSE 0 END
            + CASE WHEN s.product_id IS NOT NULL THEN 1.0 / (:rrf_k + s.rank) ELSE 0 END
            as rrf_score
        FROM lexical_matches l
        FULL OUTER JOIN semantic_matches s ON l.product_id = s.product_id
        FULL OUTER JOIN exact_matches e
            ON COALESCE(l.product_id, s.product_id) = e.product_id
    )
    SELECT
        p.product_id, p.name, p.normalized_name, p.article,
        p.brand, p.normalized_brand, p.manufacturer_code,
        p.category_id, p.category_path, p.unit, p.packaging,
        p.search_document,
        r.lex_score, r.sem_score, r.exact_hit, r.rrf_score,
        ROW_NUMBER() OVER (ORDER BY r.rrf_score DESC) as retrieval_rank
    FROM rrf_scores r
    JOIN catalog_products p ON r.product_id = p.product_id
    WHERE p.is_active = true
    ORDER BY r.rrf_score DESC
    LIMIT :top_n
    """

    result = await session.execute(text(sql), params)
    rows = result.fetchall()

    return [
        SearchCandidate(
            product_id=row[0],
            name=row[1],
            normalized_name=row[2],
            article=row[3],
            brand=row[4],
            normalized_brand=row[5],
            manufacturer_code=row[6],
            category_id=row[7],
            category_path=row[8],
            unit=row[9],
            packaging=row[10],
            search_document=row[11],
            lexical_score=float(row[12] or 0),
            semantic_score=float(row[13] or 0),
            exact_match=bool(row[14]),
            rrf_score=float(row[15] or 0),
            retrieval_rank=int(row[16]),
        )
        for row in rows
    ]


async def hybrid_search(
    query_text: str,
    normalized_text: str,
    session: AsyncSession,
    top_n: int = 50,
    article_hint: str | None = None,
    category_id: str | None = None,
    brand_hint: str | None = None,
    rrf_k: int = 60,
    token_tracker: TokenTracker | None = None,
    query_embedding: list[float] | None = ...,
) -> list[SearchCandidate]:
    """Run hybrid search combining exact, lexical, and semantic retrieval.

    Args:
        query_text: Original query text
        normalized_text: Normalized query text (from pipeline)
        session: Async SQLAlchemy session
        top_n: Number of candidates to return
        article_hint: Optional article number for exact lookup
        category_id: Optional category filter
        brand_hint: Optional brand filter
        rrf_k: RRF constant (default 60)

    Returns:
        List of SearchCandidate ordered by RRF score descending.
    """
    # Adaptive retrieval: for small catalogs, rank ALL products (no filtering)
    catalog_count = await get_catalog_count(session)
    if catalog_count <= settings.small_catalog_threshold:
        if query_embedding is ...:
            try:
                query_embedding = await embed_single(normalized_text, token_tracker=token_tracker)
            except Exception as e:
                logger.warning(f"Embedding failed for query: {e}")
                query_embedding = None
        return await _full_catalog_search(
            session,
            query_text,
            normalized_text,
            query_embedding,
            rrf_k,
            top_n,
            article_hint=article_hint,
        )

    # Get query embedding (use pre-computed if provided, ... sentinel means "compute it")
    if query_embedding is ...:
        try:
            query_embedding = await embed_single(normalized_text, token_tracker=token_tracker)
        except Exception as e:
            logger.warning(f"Embedding failed for query, falling back to lexical-only: {e}")
            query_embedding = None

    # Build the hybrid search query
    params: dict = {
        "query_text": normalized_text,
        "ts_query": normalized_text,
        "top_n": top_n,
        "rrf_k": rrf_k,
    }

    # Exact match CTE
    if article_hint:
        exact_cte = """
        exact_matches AS (
            SELECT product_id, 1 as exact_hit,
                   ROW_NUMBER() OVER (ORDER BY product_id) as rank
            FROM catalog_products
            WHERE is_active = true
              AND (article = :article_hint
                   OR code = :article_hint
                   OR manufacturer_code = :article_hint)
        )"""
        params["article_hint"] = article_hint
    else:
        exact_cte = """
        exact_matches AS (
            SELECT NULL::text as product_id, 0 as exact_hit, 0 as rank
            WHERE false
        )"""

    # Lexical CTE (tsvector + trigram)
    lexical_cte = """
    lexical_matches AS (
        SELECT product_id,
               GREATEST(
                   ts_rank(search_tsv, plainto_tsquery('russian', :ts_query)),
                   similarity(normalized_name, :query_text) * 0.8,
                   similarity(search_document, :query_text) * 0.5
               ) as lex_score,
               ROW_NUMBER() OVER (
                   ORDER BY GREATEST(
                       ts_rank(search_tsv, plainto_tsquery('russian', :ts_query)),
                       similarity(normalized_name, :query_text) * 0.8,
                       similarity(search_document, :query_text) * 0.5
                   ) DESC
               ) as rank
        FROM catalog_products
        WHERE is_active = true
          AND (
              search_tsv @@ plainto_tsquery('russian', :ts_query)
              OR similarity(normalized_name, :query_text) > 0.15
              OR similarity(search_document, :query_text) > 0.1
          )
        ORDER BY lex_score DESC
        LIMIT 200
    )"""

    # Semantic CTE (pgvector cosine)
    if query_embedding is not None:
        semantic_cte = """
        semantic_matches AS (
            SELECT e.product_id,
                   1 - (e.embedding_vector <=> :query_vector::vector) as sem_score,
                   ROW_NUMBER() OVER (
                       ORDER BY e.embedding_vector <=> :query_vector::vector
                   ) as rank
            FROM catalog_embeddings e
            JOIN catalog_products p ON e.product_id = p.product_id
            WHERE p.is_active = true
            ORDER BY e.embedding_vector <=> :query_vector::vector
            LIMIT 200
        )"""
        params["query_vector"] = str(query_embedding)
    else:
        semantic_cte = """
        semantic_matches AS (
            SELECT NULL::text as product_id, 0.0::float as sem_score, 0 as rank
            WHERE false
        )"""

    # Category/brand filter clause
    filters = []
    if category_id:
        filters.append("AND p.category_id = :category_id")
        params["category_id"] = category_id
    if brand_hint:
        filters.append("AND p.normalized_brand = :brand_hint")
        params["brand_hint"] = brand_hint
    filter_clause = " ".join(filters)

    # RRF fusion query
    sql = f"""
    WITH
    {exact_cte},
    {lexical_cte},
    {semantic_cte},
    rrf_scores AS (
        SELECT
            COALESCE(e.product_id, l.product_id, s.product_id) as product_id,
            COALESCE(e.exact_hit, 0) as exact_hit,
            COALESCE(l.lex_score, 0) as lex_score,
            COALESCE(s.sem_score, 0) as sem_score,
            -- RRF: 1/(k+rank) for each signal
            CASE WHEN e.product_id IS NOT NULL THEN 1.0 / (:rrf_k + 0) ELSE 0 END
            + CASE WHEN l.product_id IS NOT NULL THEN 1.0 / (:rrf_k + l.rank) ELSE 0 END
            + CASE WHEN s.product_id IS NOT NULL THEN 1.0 / (:rrf_k + s.rank) ELSE 0 END
            as rrf_score
        FROM lexical_matches l
        FULL OUTER JOIN semantic_matches s ON l.product_id = s.product_id
        FULL OUTER JOIN exact_matches e
            ON COALESCE(l.product_id, s.product_id) = e.product_id
    )
    SELECT
        p.product_id, p.name, p.normalized_name, p.article,
        p.brand, p.normalized_brand, p.manufacturer_code,
        p.category_id, p.category_path, p.unit, p.packaging,
        p.search_document,
        r.lex_score, r.sem_score, r.exact_hit, r.rrf_score,
        ROW_NUMBER() OVER (ORDER BY r.rrf_score DESC) as retrieval_rank
    FROM rrf_scores r
    JOIN catalog_products p ON r.product_id = p.product_id
    WHERE p.is_active = true {filter_clause}
    ORDER BY r.rrf_score DESC
    LIMIT :top_n
    """

    result = await session.execute(text(sql), params)
    rows = result.fetchall()

    # Relaxed fallback: if primary search returned nothing, try broader search
    if not rows:
        filter_params = {k: params[k] for k in ("category_id", "brand_hint") if k in params}
        rows = await _relaxed_fallback_search(
            session=session,
            normalized_text=normalized_text,
            query_embedding=query_embedding,
            top_n=top_n // 2,
            rrf_k=rrf_k,
            filter_clause=filter_clause,
            filter_params=filter_params,
        )

    candidates = []
    for row in rows:
        candidates.append(
            SearchCandidate(
                product_id=row[0],
                name=row[1],
                normalized_name=row[2],
                article=row[3],
                brand=row[4],
                normalized_brand=row[5],
                manufacturer_code=row[6],
                category_id=row[7],
                category_path=row[8],
                unit=row[9],
                packaging=row[10],
                search_document=row[11],
                lexical_score=float(row[12] or 0),
                semantic_score=float(row[13] or 0),
                exact_match=bool(row[14]),
                rrf_score=float(row[15] or 0),
                retrieval_rank=int(row[16]),
            )
        )

    return candidates


async def _relaxed_fallback_search(
    session: AsyncSession,
    normalized_text: str,
    query_embedding: list[float] | None,
    top_n: int,
    rrf_k: int,
    filter_clause: str,
    filter_params: dict | None = None,
) -> list:
    """Broader search with lower thresholds and leading-word tsvector.

    Extracts the first meaningful word (the category noun) and searches by that,
    combined with lower trigram thresholds. Universal across industries.
    """
    # Extract leading category word (first alpha token > 3 chars)
    leading_word = None
    for token in normalized_text.split():
        if len(token) > 3 and token.isalpha():
            leading_word = token
            break

    if not leading_word:
        return []

    logger.info("Relaxed fallback: leading_word=%s for query=%s", leading_word, normalized_text)

    params: dict = {
        "query_text": normalized_text,
        "leading_word": leading_word,
        "top_n": top_n,
        "rrf_k": rrf_k,
    }

    lexical_cte = """
    lexical_matches AS (
        SELECT product_id,
               GREATEST(
                   ts_rank(search_tsv, to_tsquery('russian', :leading_word)),
                   similarity(normalized_name, :query_text) * 0.8,
                   similarity(search_document, :query_text) * 0.5
               ) as lex_score,
               ROW_NUMBER() OVER (
                   ORDER BY GREATEST(
                       ts_rank(search_tsv, to_tsquery('russian', :leading_word)),
                       similarity(normalized_name, :query_text) * 0.8,
                       similarity(search_document, :query_text) * 0.5
                   ) DESC
               ) as rank
        FROM catalog_products
        WHERE is_active = true
          AND (
              search_tsv @@ to_tsquery('russian', :leading_word)
              OR similarity(normalized_name, :query_text) > 0.08
              OR similarity(search_document, :query_text) > 0.05
          )
        ORDER BY lex_score DESC
        LIMIT 100
    )"""

    if query_embedding is not None:
        semantic_cte = """
        semantic_matches AS (
            SELECT e.product_id,
                   1 - (e.embedding_vector <=> :query_vector::vector) as sem_score,
                   ROW_NUMBER() OVER (
                       ORDER BY e.embedding_vector <=> :query_vector::vector
                   ) as rank
            FROM catalog_embeddings e
            JOIN catalog_products p ON e.product_id = p.product_id
            WHERE p.is_active = true
            ORDER BY e.embedding_vector <=> :query_vector::vector
            LIMIT 100
        )"""
        params["query_vector"] = str(query_embedding)
    else:
        semantic_cte = """
        semantic_matches AS (
            SELECT NULL::text as product_id, 0.0::float as sem_score, 0 as rank
            WHERE false
        )"""

    sql = f"""
    WITH
    {lexical_cte},
    {semantic_cte},
    rrf_scores AS (
        SELECT
            COALESCE(l.product_id, s.product_id) as product_id,
            0 as exact_hit,
            COALESCE(l.lex_score, 0) as lex_score,
            COALESCE(s.sem_score, 0) as sem_score,
            CASE WHEN l.product_id IS NOT NULL THEN 1.0 / (:rrf_k + l.rank) ELSE 0 END
            + CASE WHEN s.product_id IS NOT NULL THEN 1.0 / (:rrf_k + s.rank) ELSE 0 END
            as rrf_score
        FROM lexical_matches l
        FULL OUTER JOIN semantic_matches s ON l.product_id = s.product_id
    )
    SELECT
        p.product_id, p.name, p.normalized_name, p.article,
        p.brand, p.normalized_brand, p.manufacturer_code,
        p.category_id, p.category_path, p.unit, p.packaging,
        p.search_document,
        r.lex_score, r.sem_score, r.exact_hit, r.rrf_score,
        ROW_NUMBER() OVER (ORDER BY r.rrf_score DESC) as retrieval_rank
    FROM rrf_scores r
    JOIN catalog_products p ON r.product_id = p.product_id
    WHERE p.is_active = true {filter_clause}
    ORDER BY r.rrf_score DESC
    LIMIT :top_n
    """

    if filter_params:
        params.update(filter_params)
    result = await session.execute(text(sql), params)
    return result.fetchall()
