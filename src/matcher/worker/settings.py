from __future__ import annotations

from arq import func
from arq.connections import RedisSettings

from matcher.config import settings
from matcher.db.engine import async_session_factory, engine
from matcher.worker.tasks import batch_match, catalog_import, catalog_reindex


async def startup(ctx: dict) -> None:
    ctx["db_factory"] = async_session_factory


async def shutdown(ctx: dict) -> None:
    await engine.dispose()


class WorkerSettings:
    functions = [
        func(batch_match, timeout=1800),       # 30 min
        func(catalog_import, timeout=1800),     # 30 min
        func(catalog_reindex, timeout=3600),    # 60 min
    ]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 10
    job_timeout = 1800  # 30 min default
    on_startup = startup
    on_shutdown = shutdown
