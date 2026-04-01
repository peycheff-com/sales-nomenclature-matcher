from __future__ import annotations

from arq.connections import RedisSettings

from matcher.config import settings
from matcher.db.engine import async_session_factory, engine
from matcher.worker.tasks import batch_match, catalog_import, catalog_reindex


async def startup(ctx: dict) -> None:
    ctx["db_factory"] = async_session_factory


async def shutdown(ctx: dict) -> None:
    await engine.dispose()


class WorkerSettings:
    functions = [batch_match, catalog_import, catalog_reindex]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 10
    job_timeout = 600
    on_startup = startup
    on_shutdown = shutdown
