from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.indexing.embedder import embed_single

logger = logging.getLogger(__name__)


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


async def hybrid_search(
    query_text: str,
    normalized_text: str,
    session: AsyncSession,
    top_n: int = 50,
    article_hint: str | None = None,
    category_id: str | None = None,
    brand_hint: str | None = None,
    rrf_k: int = 60,
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
    # Get query embedding
    try:
        query_embedding = await embed_single(normalized_text)
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
              AND (article = :article_hint OR code = :article_hint OR manufacturer_code = :article_hint)
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

    candidates = []
    for row in rows:
        candidates.append(SearchCandidate(
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
        ))

    return candidates
