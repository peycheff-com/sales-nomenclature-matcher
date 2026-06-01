from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from matcher import main
from matcher.db import engine as db_engine


class _AsyncSessionContext:
    def __init__(self, session) -> None:
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_lifespan_initializes_settings_and_closes_resources(monkeypatch: pytest.MonkeyPatch):
    pool = SimpleNamespace(close=MagicMock(), wait_closed=AsyncMock())
    session = object()
    dispose = AsyncMock()
    load_persisted_settings = AsyncMock()

    monkeypatch.setattr(main, "setup_logging", MagicMock())
    monkeypatch.setattr(main.RedisSettings, "from_dsn", MagicMock(return_value="redis-settings"))
    monkeypatch.setattr(main, "create_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(main, "async_session_factory", lambda: _AsyncSessionContext(session))
    monkeypatch.setattr(main, "load_persisted_settings", load_persisted_settings)
    monkeypatch.setattr(main, "engine", SimpleNamespace(dispose=dispose))

    app = FastAPI()
    async with main.lifespan(app):
        assert app.state.arq_pool is pool
        load_persisted_settings.assert_awaited_once_with(session, force=True)

    pool.close.assert_called_once_with()
    pool.wait_closed.assert_awaited_once_with()
    dispose.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_lifespan_continues_when_persisted_settings_or_pool_close_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    pool = SimpleNamespace(close=MagicMock(side_effect=RuntimeError("close failed")))
    pool.wait_closed = AsyncMock()
    dispose = AsyncMock()

    monkeypatch.setattr(main, "setup_logging", MagicMock())
    monkeypatch.setattr(main.RedisSettings, "from_dsn", MagicMock(return_value="redis-settings"))
    monkeypatch.setattr(main, "create_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(main, "async_session_factory", lambda: _AsyncSessionContext(object()))
    monkeypatch.setattr(
        main,
        "load_persisted_settings",
        AsyncMock(side_effect=RuntimeError("settings failed")),
    )
    monkeypatch.setattr(main, "engine", SimpleNamespace(dispose=dispose))

    async with main.lifespan(FastAPI()):
        pass

    dispose.assert_awaited_once_with()


def test_create_app_docs_visibility_and_health_routes(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(main.settings, "log_level", "DEBUG")
    debug_app = main.create_app()
    assert debug_app.docs_url == "/docs"
    assert debug_app.redoc_url == "/redoc"

    monkeypatch.setattr(main.settings, "log_level", "INFO")
    app = main.create_app()
    app.state.arq_pool = object()
    assert app.docs_url is None
    assert app.redoc_url is None

    readiness_checks = AsyncMock(return_value={"db": "ok", "redis": "failed"})
    monkeypatch.setattr(main, "readiness_checks", readiness_checks)

    client = TestClient(app)
    live = client.get("/api/v1/health/live")
    assert live.status_code == 200
    assert live.json() == {"status": "ok", "version": "0.1.0"}

    health = client.get("/api/v1/health")
    assert health.status_code == 503
    assert health.json() == {
        "status": "degraded",
        "version": "0.1.0",
        "checks": {"db": "ok", "redis": "failed"},
    }


@pytest.mark.asyncio
async def test_get_session_yields_and_rolls_back_on_errors(monkeypatch: pytest.MonkeyPatch):
    session = SimpleNamespace(rollback=AsyncMock())
    monkeypatch.setattr(db_engine, "async_session_factory", lambda: _AsyncSessionContext(session))

    yielded = []
    async for db in db_engine.get_session():
        yielded.append(db)
    assert yielded == [session]
    session.rollback.assert_not_awaited()

    failing_session = SimpleNamespace(rollback=AsyncMock())
    monkeypatch.setattr(
        db_engine, "async_session_factory", lambda: _AsyncSessionContext(failing_session)
    )
    agen = db_engine.get_session()
    assert await anext(agen) is failing_session

    with pytest.raises(RuntimeError, match="boom"):
        await agen.athrow(RuntimeError("boom"))

    failing_session.rollback.assert_awaited_once_with()
