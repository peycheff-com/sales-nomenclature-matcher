from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from matcher.worker import settings as worker_settings


class _FakeSession:
    def __init__(self) -> None:
        self.commit = AsyncMock()


class _FakeRepo:
    recoverable: list[SimpleNamespace] = []
    instances: list[_FakeRepo] = []

    def __init__(self, session) -> None:
        self.session = session
        self.list_recoverable_requests = AsyncMock(return_value=self.recoverable)
        self.clear_item_results = AsyncMock()
        self.update_request_status = AsyncMock()
        self.instances.append(self)


def _factory(session: _FakeSession):
    @asynccontextmanager
    async def factory():
        yield session

    return factory


@pytest.fixture(autouse=True)
def reset_fake_repo():
    _FakeRepo.recoverable = []
    _FakeRepo.instances = []


@pytest.mark.asyncio
async def test_base_startup_injects_db_factory(monkeypatch: pytest.MonkeyPatch):
    factory = object()
    monkeypatch.setattr(worker_settings, "async_session_factory", factory)
    ctx: dict = {}

    await worker_settings._base_startup(ctx)

    assert ctx["db_factory"] is factory


@pytest.mark.asyncio
async def test_catalog_startup_uses_base_startup(monkeypatch: pytest.MonkeyPatch):
    factory = object()
    monkeypatch.setattr(worker_settings, "async_session_factory", factory)
    ctx: dict = {}

    await worker_settings.catalog_startup(ctx)

    assert ctx["db_factory"] is factory


@pytest.mark.asyncio
async def test_match_startup_recovers_orphaned_requests(monkeypatch: pytest.MonkeyPatch):
    session = _FakeSession()
    redis = SimpleNamespace(enqueue_job=AsyncMock())
    recoverable = [
        SimpleNamespace(
            request_id="req-1",
            job_name=None,
            job_payload_json={"supplier_id": "supplier-1"},
        ),
        SimpleNamespace(
            request_id="req-2",
            job_name="smart_upload",
            job_payload_json=None,
        ),
    ]
    _FakeRepo.recoverable = recoverable
    monkeypatch.setattr(worker_settings, "async_session_factory", _factory(session))
    monkeypatch.setattr("matcher.db.repos.match.MatchRepo", _FakeRepo)

    await worker_settings.match_startup({"redis": redis})

    repo = _FakeRepo.instances[0]
    assert repo.clear_item_results.await_count == 2
    assert repo.update_request_status.await_count == 2
    repo.update_request_status.assert_any_await(
        "req-1",
        "queued",
        processed_items=0,
        auto_matched_items=0,
        review_needed_items=0,
        no_match_items=0,
        error_message=None,
    )
    assert session.commit.await_count == 1
    redis.enqueue_job.assert_any_await(
        "batch_match",
        "req-1",
        _queue_name="match",
        _job_id="req-1",
        supplier_id="supplier-1",
    )
    redis.enqueue_job.assert_any_await(
        "smart_upload",
        "req-2",
        _queue_name="match",
        _job_id="req-2",
    )


@pytest.mark.asyncio
async def test_match_startup_handles_no_recoverable_requests(monkeypatch: pytest.MonkeyPatch):
    session = _FakeSession()
    redis = SimpleNamespace(enqueue_job=AsyncMock())
    monkeypatch.setattr(worker_settings, "async_session_factory", _factory(session))
    monkeypatch.setattr("matcher.db.repos.match.MatchRepo", _FakeRepo)

    await worker_settings.match_startup({"redis": redis})

    repo = _FakeRepo.instances[0]
    repo.clear_item_results.assert_not_awaited()
    repo.update_request_status.assert_not_awaited()
    session.commit.assert_not_awaited()
    redis.enqueue_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_match_startup_swallows_recovery_errors(monkeypatch: pytest.MonkeyPatch):
    @asynccontextmanager
    async def failing_factory():
        raise RuntimeError("db down")
        yield

    monkeypatch.setattr(worker_settings, "async_session_factory", failing_factory)

    await worker_settings.match_startup({})


@pytest.mark.asyncio
async def test_shutdown_disposes_engine(monkeypatch: pytest.MonkeyPatch):
    engine = SimpleNamespace(dispose=AsyncMock())
    monkeypatch.setattr(worker_settings, "engine", engine)

    await worker_settings.shutdown({})

    engine.dispose.assert_awaited_once()


def test_worker_settings_are_split_by_queue():
    assert worker_settings.WorkerSettings is worker_settings.MatchWorkerSettings
    assert worker_settings.MatchWorkerSettings.queue_name == "match"
    assert worker_settings.CatalogWorkerSettings.queue_name == "catalog"
    assert (
        worker_settings.MatchWorkerSettings.max_jobs
        > worker_settings.CatalogWorkerSettings.max_jobs
    )
    assert worker_settings.MatchWorkerSettings.on_startup is worker_settings.match_startup
    assert worker_settings.CatalogWorkerSettings.on_startup is worker_settings.catalog_startup
