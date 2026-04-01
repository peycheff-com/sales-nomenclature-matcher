from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text, update

from matcher.api.error_handlers import register_error_handlers
from matcher.api.middleware import (
    RateLimitMiddleware,
    RequestIdMiddleware,
    RequestTimeoutMiddleware,
    SecurityHeadersMiddleware,
)
from matcher.api.v1 import auth, catalog, match, metrics, review, suppliers, upload, users
from matcher.api.v1.settings import router as settings_router
from matcher.config import settings
from matcher.db.engine import async_session_factory, engine
from matcher.db.models import MatchRequest
from matcher.logging_config import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.log_level)
    logger.info("Starting Sales Nomenclature Matcher")

    # Initialize ARQ Redis pool
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    app.state.arq_pool = await create_pool(redis_settings)
    logger.info("ARQ Redis pool initialized")

    # Reset stale "running" requests left over from a previous crash
    try:
        async with async_session_factory() as session:
            result = await session.execute(
                update(MatchRequest)
                .where(MatchRequest.status == "running")
                .values(
                    status="failed",
                    error_message="Server restarted during processing",
                )
            )
            if result.rowcount:
                logger.warning("Reset %d stale running requests to failed", result.rowcount)
            await session.commit()
    except Exception:
        logger.exception("Failed to reset stale requests on startup")

    yield

    # Cleanup
    app.state.arq_pool.close()
    await app.state.arq_pool.wait_closed()
    await engine.dispose()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    is_debug = settings.log_level.upper() == "DEBUG"
    app = FastAPI(
        title="Sales Nomenclature Matcher",
        version="0.1.0",
        lifespan=lifespan,
        # Disable interactive API docs in production (defense-in-depth)
        docs_url="/docs" if is_debug else None,
        redoc_url="/redoc" if is_debug else None,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Security headers middleware (outermost — runs last on response)
    app.add_middleware(SecurityHeadersMiddleware)

    # Rate limiting middleware
    app.add_middleware(RateLimitMiddleware)

    # Request timeout middleware
    app.add_middleware(RequestTimeoutMiddleware)

    # Request ID middleware
    app.add_middleware(RequestIdMiddleware)

    # Register custom error handlers
    register_error_handlers(app)

    # Prometheus metrics (exposed at /metrics)
    Instrumentator(
        excluded_handlers=["/metrics", "/api/v1/health"],
    ).instrument(app).expose(app, include_in_schema=False)

    # Routers
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(match.router, prefix="/api/v1")
    app.include_router(review.router, prefix="/api/v1")
    app.include_router(catalog.router, prefix="/api/v1")
    app.include_router(suppliers.router, prefix="/api/v1")
    app.include_router(metrics.router, prefix="/api/v1")
    app.include_router(settings_router, prefix="/api/v1")
    app.include_router(upload.router, prefix="/api/v1")
    app.include_router(users.router, prefix="/api/v1")

    @app.get("/api/v1/health", tags=["Health"])
    async def health(response: Response):
        checks = {}

        # Check DB (with timeout)
        try:

            async def _check_db():
                async with async_session_factory() as session:
                    await session.execute(text("SELECT 1"))

            await asyncio.wait_for(_check_db(), timeout=5.0)
            checks["db"] = "ok"
        except Exception as e:
            logger.warning("Health check DB failed: %s", e)
            checks["db"] = "error"

        # Check Redis (with timeout)
        try:
            pool = app.state.arq_pool
            await asyncio.wait_for(pool.ping(), timeout=3.0)
            checks["redis"] = "ok"
        except Exception as e:
            logger.warning("Health check Redis failed: %s", e)
            checks["redis"] = "error"

        all_ok = all(v == "ok" for v in checks.values())
        if not all_ok:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        status_text = "ok" if all_ok else "degraded"

        result = {"status": status_text, "version": "0.1.0"}
        if settings.log_level.upper() == "DEBUG":
            result["checks"] = checks
        return result

    return app


app = create_app()
