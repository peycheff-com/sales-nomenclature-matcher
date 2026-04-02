from __future__ import annotations

from arq import func
from arq.connections import RedisSettings

from matcher.config import settings
from matcher.db.engine import async_session_factory, engine
from matcher.worker.tasks import batch_match, catalog_import, catalog_reindex, smart_upload


async def _base_startup(ctx: dict) -> None:
    """Common startup: inject DB factory into ARQ context."""
    ctx["db_factory"] = async_session_factory


async def match_startup(ctx: dict) -> None:
    """Match worker startup: inject DB + recover orphaned match requests."""
    import logging

    from matcher.db.repos.match import MatchRepo

    await _base_startup(ctx)

    logger = logging.getLogger(__name__)
    try:
        async with async_session_factory() as session:
            repo = MatchRepo(session)
            recoverable = await repo.list_recoverable_requests()
            orphaned = [req.request_id for req in recoverable]
            if orphaned:
                for req in recoverable:
                    await repo.clear_item_results(req.request_id)
                    await repo.update_request_status(
                        req.request_id,
                        "queued",
                        processed_items=0,
                        auto_matched_items=0,
                        review_needed_items=0,
                        no_match_items=0,
                        error_message=None,
                    )
                await session.commit()
                redis = ctx.get("redis")
                if redis:
                    for req in recoverable:
                        await redis.enqueue_job(
                            req.job_name or "batch_match",
                            req.request_id,
                            _queue_name="match",
                            _job_id=req.request_id,
                            **(req.job_payload_json or {}),
                        )
                logger.warning("Recovered %d orphaned requests: %s", len(orphaned), orphaned)
            else:
                logger.info("No orphaned requests found on startup")
    except Exception:
        logger.exception("Failed to recover orphaned requests")


async def catalog_startup(ctx: dict) -> None:
    """Catalog worker startup: inject DB only (no orphan recovery)."""
    await _base_startup(ctx)


async def shutdown(ctx: dict) -> None:
    await engine.dispose()


class MatchWorkerSettings:
    """Worker for matching tasks (batch_match, smart_upload)."""

    functions = [
        func(batch_match, timeout=1800, max_tries=3),
        func(smart_upload, timeout=3600, max_tries=2),
    ]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    queue_name = "match"
    max_jobs = 8
    job_timeout = 1800
    on_startup = match_startup
    on_shutdown = shutdown
    health_check_interval = 60  # seconds between health pings


class CatalogWorkerSettings:
    """Worker for catalog tasks (catalog_import, catalog_reindex)."""

    functions = [
        func(catalog_import, timeout=1800, max_tries=2),
        func(catalog_reindex, timeout=3600, max_tries=2),
    ]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    queue_name = "catalog"
    max_jobs = 2
    job_timeout = 3600
    on_startup = catalog_startup
    on_shutdown = shutdown
    health_check_interval = 60


# Backward-compatible alias
WorkerSettings = MatchWorkerSettings
