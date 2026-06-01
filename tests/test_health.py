from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from matcher import health


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    def __init__(self, results: list[_ScalarResult] | None = None, fail: bool = False):
        self.results = list(results or [])
        self.fail = fail

    async def execute(self, _statement):
        if self.fail:
            raise RuntimeError("db unavailable")
        if self.results:
            return self.results.pop(0)
        return _ScalarResult(1)


def _session_factory(session: _FakeSession):
    @asynccontextmanager
    async def factory():
        yield session

    return factory


def test_provider_ready_accepts_local(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        health,
        "settings",
        SimpleNamespace(effective_provider_api_key=lambda provider_id: ""),
    )

    assert health._provider_ready("local", "chat") is True


@pytest.mark.parametrize(
    ("provider_id", "role"),
    [("llm-fallback", "rerank"), ("none", "embeddings")],
)
def test_provider_ready_rejects_virtual_unavailable_providers(provider_id: str, role: str):
    assert health._provider_ready(provider_id, role) is False


@pytest.mark.parametrize("api_key", ["", "none", "your-key-here", "sk-your-key-here"])
def test_provider_ready_rejects_missing_or_placeholder_keys(
    monkeypatch: pytest.MonkeyPatch,
    api_key: str,
):
    monkeypatch.setattr(
        health,
        "settings",
        SimpleNamespace(effective_provider_api_key=lambda provider_id: api_key),
    )

    assert health._provider_ready("openai", "chat") is False


def test_provider_ready_accepts_real_api_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        health,
        "settings",
        SimpleNamespace(effective_provider_api_key=lambda provider_id: "real-key"),
    )

    assert health._provider_ready("openai", "chat") is True


@pytest.mark.asyncio
async def test_readiness_checks_all_ok(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        health,
        "settings",
        SimpleNamespace(
            llm_provider="local",
            embedding_provider="local",
            rerank_provider="local",
            effective_provider_api_key=lambda provider_id: "",
        ),
    )

    session = _FakeSession(
        [
            _ScalarResult(1),
            _ScalarResult(3),
            _ScalarResult(SimpleNamespace(id="active-index")),
            _ScalarResult(3),
        ]
    )
    redis_pool = SimpleNamespace(ping=AsyncMock(return_value=True))

    checks = await health.readiness_checks(
        session_factory=_session_factory(session),
        redis_pool=redis_pool,
    )

    assert checks == {
        "db": "ok",
        "redis": "ok",
        "providers": "ok",
        "catalog": "ok",
        "index": "ok",
    }


@pytest.mark.asyncio
async def test_readiness_checks_reports_db_redis_catalog_and_index_failures(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        health,
        "settings",
        SimpleNamespace(
            llm_provider="openai",
            embedding_provider="none",
            rerank_provider="llm-fallback",
            effective_provider_api_key=lambda provider_id: "",
        ),
    )

    session = _FakeSession(fail=True)
    redis_pool = SimpleNamespace(ping=AsyncMock(side_effect=RuntimeError("redis down")))

    checks = await health.readiness_checks(
        session_factory=_session_factory(session),
        redis_pool=redis_pool,
    )

    assert checks == {
        "db": "error",
        "redis": "error",
        "providers": "error",
        "catalog": "error",
        "index": "error",
    }


@pytest.mark.asyncio
async def test_readiness_checks_requires_catalog_rows_and_active_index(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        health,
        "settings",
        SimpleNamespace(
            llm_provider="local",
            embedding_provider="local",
            rerank_provider="local",
            effective_provider_api_key=lambda provider_id: "",
        ),
    )

    session = _FakeSession(
        [
            _ScalarResult(1),
            _ScalarResult(0),
            _ScalarResult(None),
            _ScalarResult(0),
        ]
    )
    redis_pool = SimpleNamespace(ping=AsyncMock(return_value=True))

    checks = await health.readiness_checks(
        session_factory=_session_factory(session),
        redis_pool=redis_pool,
    )

    assert checks["db"] == "ok"
    assert checks["redis"] == "ok"
    assert checks["providers"] == "ok"
    assert checks["catalog"] == "error"
    assert checks["index"] == "error"
