from __future__ import annotations

from arq import func
from arq.connections import RedisSettings

from matcher.config import settings
from matcher.db.engine import async_session_factory, engine
from matcher.worker.tasks import batch_match, catalog_import, catalog_reindex, smart_upload


async def startup(ctx: dict) -> None:
    ctx["db_factory"] = async_session_factory

    # Recover orphaned "running" requests left by a previous worker crash/deploy.
    # Reset them to "queued" so ARQ picks them up again.
    import logging

    from sqlalchemy import update

    from matcher.db.models import MatchRequest

    logger = logging.getLogger(__name__)
    try:
        async with async_session_factory() as session:
            result = await session.execute(
                update(MatchRequest)
                .where(MatchRequest.status == "running")
                .values(status="queued")
                .returning(MatchRequest.request_id)
            )
            orphaned = [row[0] for row in result.all()]
            if orphaned:
                await session.commit()
                # Re-enqueue each orphaned request
                redis = ctx.get("redis")
                if redis:
                    for rid in orphaned:
                        await redis.enqueue_job("batch_match", rid)
                logger.warning("Recovered %d orphaned requests: %s", len(orphaned), orphaned)
            else:
                logger.info("No orphaned requests found on startup")
    except Exception:
        logger.exception("Failed to recover orphaned requests")


async def shutdown(ctx: dict) -> None:
    await engine.dispose()


class WorkerSettings:
    functions = [
        func(batch_match, timeout=1800),  # 30 min
        func(catalog_import, timeout=1800),  # 30 min
        func(catalog_reindex, timeout=3600),  # 60 min
        func(smart_upload, timeout=3600),  # 60 min (catalog + reindex + match)
    ]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 10
    job_timeout = 1800  # 30 min default
    on_startup = startup
    on_shutdown = shutdown
