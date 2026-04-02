from __future__ import annotations

import asyncio

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from matcher.config import settings
from matcher.db.models import CatalogEmbedding, CatalogProduct, IndexVersion


def _provider_ready(provider_id: str, role: str) -> bool:
    if provider_id == "local":
        return True
    if role == "rerank" and provider_id == "llm-fallback":
        return False
    if role == "embeddings" and provider_id == "none":
        return False
    api_key = settings.effective_provider_api_key(provider_id)
    return bool(api_key and api_key not in ("none", "your-key-here", "sk-your-key-here"))


async def readiness_checks(
    *,
    session_factory: async_sessionmaker,
    redis_pool,
) -> dict[str, str]:
    checks: dict[str, str] = {
        "db": "error",
        "redis": "error",
        "providers": "error",
        "catalog": "error",
        "index": "error",
    }

    try:
        async with session_factory() as session:
            await asyncio.wait_for(session.execute(text("SELECT 1")), timeout=5.0)
        checks["db"] = "ok"
    except Exception:
        checks["db"] = "error"

    try:
        await asyncio.wait_for(redis_pool.ping(), timeout=3.0)
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"

    llm_ok = _provider_ready(settings.llm_provider, "chat")
    emb_ok = _provider_ready(settings.embedding_provider, "embeddings")
    rerank_ok = _provider_ready(settings.rerank_provider, "rerank")
    checks["providers"] = "ok" if llm_ok and emb_ok and rerank_ok else "error"

    try:
        async with session_factory() as session:
            total_products = (
                await session.execute(
                    select(func.count()).select_from(CatalogProduct).where(CatalogProduct.is_active)
                )
            ).scalar() or 0
            checks["catalog"] = "ok" if total_products > 0 else "error"

            active_index = (
                await session.execute(
                    select(IndexVersion).where(IndexVersion.is_active == True)  # noqa: E712
                )
            ).scalar_one_or_none()
            embedded_products = (
                await session.execute(
                    select(func.count(func.distinct(CatalogEmbedding.product_id))).select_from(
                        CatalogEmbedding
                    )
                )
            ).scalar() or 0
            checks["index"] = (
                "ok" if active_index is not None and embedded_products > 0 else "error"
            )
    except Exception:
        checks["catalog"] = "error"
        checks["index"] = "error"

    return checks
