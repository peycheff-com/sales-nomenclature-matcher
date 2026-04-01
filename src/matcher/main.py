from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from matcher.api.middleware import RequestIdMiddleware, SecurityHeadersMiddleware
from matcher.api.v1 import auth, catalog, match, metrics, review, suppliers
from matcher.api.v1.settings import router as settings_router
from matcher.config import settings
from matcher.db.engine import async_session_factory
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

    yield

    # Cleanup
    app.state.arq_pool.close()
    await app.state.arq_pool.wait_closed()
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

    # Request ID middleware
    app.add_middleware(RequestIdMiddleware)

    # Routers
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(match.router, prefix="/api/v1")
    app.include_router(review.router, prefix="/api/v1")
    app.include_router(catalog.router, prefix="/api/v1")
    app.include_router(suppliers.router, prefix="/api/v1")
    app.include_router(metrics.router, prefix="/api/v1")
    app.include_router(settings_router, prefix="/api/v1")

    @app.get("/api/v1/health", tags=["Health"])
    async def health():
        checks = {}

        # Check DB
        try:
            async with async_session_factory() as session:
                await session.execute(text("SELECT 1"))
            checks["db"] = "ok"
        except Exception as e:
            logger.warning("Health check DB failed: %s", e)
            checks["db"] = "error"

        # Check Redis
        try:
            pool = app.state.arq_pool
            await pool.ping()
            checks["redis"] = "ok"
        except Exception as e:
            logger.warning("Health check Redis failed: %s", e)
            checks["redis"] = "error"

        all_ok = all(v == "ok" for v in checks.values())
        status = "ok" if all_ok else "degraded"

        # Only return detailed checks in debug mode; otherwise just status
        if settings.log_level.upper() == "DEBUG":
            return {"status": status, "checks": checks}
        return {"status": status}

    return app


app = create_app()
