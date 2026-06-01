from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import DataError, IntegrityError

from matcher.api import deps
from matcher.api.error_handlers import register_error_handlers
from matcher.api.middleware import (
    RateLimitMiddleware,
    RequestIdMiddleware,
    RequestTimeoutMiddleware,
    SecurityHeadersMiddleware,
)


@pytest.mark.asyncio
async def test_get_db_yields_sessions_from_engine(monkeypatch: pytest.MonkeyPatch):
    session = object()

    async def fake_get_session():
        yield session

    monkeypatch.setattr(deps, "get_session", fake_get_session)

    yielded = []
    async for db in deps.get_db():
        yielded.append(db)

    assert yielded == [session]


def test_get_arq_pool_returns_application_pool():
    pool = object()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(arq_pool=pool)))

    assert asyncio.run(deps.get_arq_pool(request)) is pool


def test_error_handlers_format_database_and_unhandled_errors():
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/integrity")
    async def integrity():
        orig = SimpleNamespace(
            diag=SimpleNamespace(message_detail="Key (username)=(admin) already exists.")
        )
        raise IntegrityError("insert user", {}, orig)

    @app.get("/integrity-generic")
    async def integrity_generic():
        raise IntegrityError("insert user", {}, None)

    @app.get("/data")
    async def data():
        raise DataError("select", {}, ValueError("bad data"))

    @app.get("/boom")
    async def boom():
        raise RuntimeError("hidden")

    client = TestClient(app, raise_server_exceptions=False)

    assert client.get("/integrity").json() == {
        "error": "Conflict",
        "detail": "Key (username)=(admin) already exists.",
    }
    assert client.get("/integrity-generic").json() == {
        "error": "Conflict",
        "detail": "Data integrity conflict.",
    }
    assert client.get("/data").json() == {
        "error": "Unprocessable Entity",
        "detail": "Database cannot process the provided data type or format.",
    }
    assert client.get("/boom").json() == {
        "error": "Internal Server Error",
        "detail": "An unexpected error occurred.",
    }


def test_request_id_and_security_headers_are_added():
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIdMiddleware)

    @app.get("/ok")
    async def ok():
        return {"ok": True}

    response = TestClient(app).get("/ok", headers={"X-Request-ID": "req-test"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-test"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-XSS-Protection"] == "0"


def test_rate_limit_middleware_blocks_and_exempts_paths(monkeypatch: pytest.MonkeyPatch):
    from matcher.api import middleware

    allow_request = AsyncMock(return_value=False)
    monkeypatch.setattr(middleware.api_rate_limiter, "allow_request", allow_request)

    app = FastAPI()
    app.state.arq_pool = object()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/api/v1/items")
    async def items():
        return {"ok": True}

    @app.get("/metrics")
    async def metrics():
        return {"ok": True}

    client = TestClient(app)

    blocked = client.get("/api/v1/items")
    assert blocked.status_code == 429
    assert blocked.json() == {
        "error": "Too Many Requests",
        "detail": "Rate limit exceeded. Try again later.",
    }

    exempt = client.get("/metrics")
    assert exempt.status_code == 200
    assert exempt.json() == {"ok": True}
    allow_request.assert_awaited_once()


def test_rate_limit_middleware_allows_when_redis_is_missing_or_unavailable(
    monkeypatch: pytest.MonkeyPatch,
):
    from matcher.api import middleware

    allow_request = AsyncMock(side_effect=RuntimeError("redis down"))
    monkeypatch.setattr(middleware.api_rate_limiter, "allow_request", allow_request)

    app = FastAPI()
    app.state.arq_pool = object()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/api/v1/items")
    async def items():
        return {"ok": True}

    assert TestClient(app).get("/api/v1/items").json() == {"ok": True}
    allow_request.assert_awaited_once()

    no_redis_app = FastAPI()
    no_redis_app.add_middleware(RateLimitMiddleware)

    @no_redis_app.get("/api/v1/items")
    async def no_redis_items():
        return {"ok": True}

    assert TestClient(no_redis_app).get("/api/v1/items").json() == {"ok": True}


def test_request_timeout_middleware_times_out_and_exempts_health(
    monkeypatch: pytest.MonkeyPatch,
):
    from matcher.api import middleware

    monkeypatch.setattr(middleware.settings, "request_timeout_seconds", 0.001)

    app = FastAPI()
    app.add_middleware(RequestTimeoutMiddleware)

    @app.get("/slow")
    async def slow():
        await asyncio.sleep(0.05)
        return {"ok": True}

    @app.get("/api/v1/health")
    async def health():
        return {"ok": True}

    client = TestClient(app, raise_server_exceptions=False)

    timed_out = client.get("/slow")
    assert timed_out.status_code == 504
    assert timed_out.json() == {
        "error": "Gateway Timeout",
        "detail": "Request processing timed out.",
    }
    assert client.get("/api/v1/health").json() == {"ok": True}
