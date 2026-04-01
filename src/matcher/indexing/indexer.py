from __future__ import annotations

import logging
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from matcher.config import settings
from matcher.indexing.embedder import embed_texts

logger = logging.getLogger(__name__)


async def reindex_catalog(
    embedding_model: str | None = None,
    embedding_version: str | None = None,
    batch_size: int = 100,
    session_factory=None,
) -> dict:
    """Reindex the entire catalog: embed products and update search vectors.

    Args:
        embedding_model: Model name for embeddings. Defaults to settings.embedding_model.
        embedding_version: Version tag for embeddings. Defaults to "v1".
        batch_size: Number of products to process per batch.
        session_factory: Optional async session factory (e.g. from worker context).
            If provided, uses it instead of creating a standalone engine.
            This enables connection pooling reuse in worker processes.

    Returns summary stats.
    """
    embedding_model = embedding_model or settings.embedding_model
    embedding_version = embedding_version or "v1"

    # If session_factory is provided, use it; otherwise create a standalone engine
    owns_engine = session_factory is None
    engine = None

    if owns_engine:
        engine = create_async_engine(settings.async_database_url)

    async def _execute_in_transaction(fn):
        """Execute a function within a transaction, using either engine or session_factory."""
        if owns_engine:
            async with engine.begin() as conn:
                return await fn(conn)
        else:
            async with session_factory() as session:
                async with session.begin():
                    conn = await session.connection()
                    result = await fn(conn)
                    return result

    try:
        # Step 1: Update tsvector for all products
        async def update_tsvectors(conn):
            await conn.execute(
                text("""
                UPDATE catalog_products
                SET search_tsv = to_tsvector('russian', coalesce(search_document, ''))
                WHERE search_tsv IS NULL
                   OR search_tsv != to_tsvector('russian', coalesce(search_document, ''))
            """)
            )
            result = await conn.execute(
                text("SELECT count(*) FROM catalog_products WHERE is_active = true")
            )
            return result.scalar() or 0

        total_products = await _execute_in_transaction(update_tsvectors)
        logger.info("Total active products: %d", total_products)

        # Step 2: Fetch products that need embedding
        embedded_count = 0
        offset = 0

        while offset < total_products:

            async def embed_batch(conn):
                result = await conn.execute(
                    text("""
                    SELECT p.product_id, p.search_document
                    FROM catalog_products p
                    LEFT JOIN catalog_embeddings e ON p.product_id = e.product_id
                        AND e.embedding_model = :model
                        AND e.embedding_version = :version
                    WHERE p.is_active = true
                      AND e.product_id IS NULL
                    ORDER BY p.product_id
                    LIMIT :limit OFFSET :offset
                """),
                    {
                        "model": embedding_model,
                        "version": embedding_version,
                        "limit": batch_size,
                        "offset": 0,  # Always 0 since we filter out already-embedded
                    },
                )
                rows = result.fetchall()

                if not rows:
                    return rows, 0

                product_ids = [r[0] for r in rows]
                texts_to_embed = [r[1] or "" for r in rows]

                # Embed batch
                embeddings = await embed_texts(texts_to_embed, model=embedding_model)

                # Upsert embeddings
                for pid, emb in zip(product_ids, embeddings):
                    await conn.execute(
                        text("""
                        INSERT INTO catalog_embeddings
                            (product_id, embedding_model,
                             embedding_version, embedding_vector)
                        VALUES (:pid, :model, :version, :vector)
                        ON CONFLICT (product_id) DO UPDATE SET
                            embedding_model = EXCLUDED.embedding_model,
                            embedding_version = EXCLUDED.embedding_version,
                            embedding_vector = EXCLUDED.embedding_vector,
                            created_at = now()
                    """),
                        {
                            "pid": pid,
                            "model": embedding_model,
                            "version": embedding_version,
                            "vector": str(emb),
                        },
                    )

                return rows, len(rows)

            try:
                rows, count = await _execute_in_transaction(embed_batch)
            except Exception as e:
                logger.error("Embedding failed at offset %d: %s", offset, e)
                raise

            if not rows:
                break

            embedded_count += count
            logger.info("Embedded %d/%d products", embedded_count, total_products)
            offset += batch_size

        # Step 3: Create index version record
        version_id = f"idx_{uuid.uuid4().hex[:12]}"

        async def create_version(conn):
            # Deactivate old versions
            await conn.execute(
                text("""
                UPDATE index_versions SET is_active = false WHERE is_active = true
            """)
            )
            # Create new version
            await conn.execute(
                text("""
                INSERT INTO index_versions (
                    index_version_id, embedding_model, embedding_version,
                    lexical_version, rules_version, is_active, product_count
                ) VALUES (:id, :model, :version, 'v1', 'v1', true, :count)
            """),
                {
                    "id": version_id,
                    "model": embedding_model,
                    "version": embedding_version,
                    "count": total_products,
                },
            )

        await _execute_in_transaction(create_version)

        return {
            "index_version_id": version_id,
            "total_products": total_products,
            "embedded_count": embedded_count,
            "embedding_model": embedding_model,
            "embedding_version": embedding_version,
        }
    finally:
        if owns_engine and engine is not None:
            await engine.dispose()
