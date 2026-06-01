from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, status

from matcher import queueing


@pytest.mark.asyncio
async def test_enqueue_unique_job_passes_queue_and_job_id():
    pool = SimpleNamespace(enqueue_job=AsyncMock(return_value="job"))

    result = await queueing.enqueue_unique_job(
        pool,
        "batch_match",
        "req-1",
        "match",
        supplier_id="supplier-1",
    )

    assert result == "job"
    pool.enqueue_job.assert_awaited_once_with(
        "batch_match",
        "req-1",
        _queue_name="match",
        _job_id="req-1",
        supplier_id="supplier-1",
    )


@pytest.mark.asyncio
async def test_enqueue_request_job_marks_request_queued(monkeypatch: pytest.MonkeyPatch):
    db = SimpleNamespace(commit=AsyncMock())
    pool = SimpleNamespace(enqueue_job=AsyncMock())
    repo = SimpleNamespace(update_request_status=AsyncMock())

    monkeypatch.setattr(queueing, "MatchRepo", lambda session: repo)

    await queueing.enqueue_request_job(
        db=db,
        arq_pool=pool,
        request_id="req-1",
        job_name="batch_match",
        queue_name="match",
        job_payload={"supplier_id": "supplier-1"},
    )

    repo.update_request_status.assert_awaited_once_with(
        "req-1",
        "queued",
        error_message=None,
    )
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_enqueue_request_job_marks_request_failed_on_enqueue_error(
    monkeypatch: pytest.MonkeyPatch,
):
    db = SimpleNamespace(commit=AsyncMock())
    pool = SimpleNamespace(enqueue_job=AsyncMock(side_effect=RuntimeError("redis down")))
    repo = SimpleNamespace(update_request_status=AsyncMock())

    monkeypatch.setattr(queueing, "MatchRepo", lambda session: repo)

    with pytest.raises(HTTPException) as exc_info:
        await queueing.enqueue_request_job(
            db=db,
            arq_pool=pool,
            request_id="req-1",
            job_name="batch_match",
            queue_name="match",
        )

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert exc_info.value.detail == "Failed to enqueue background job"
    repo.update_request_status.assert_awaited_once_with(
        "req-1",
        "failed",
        error_message="enqueue_failed: redis down",
    )
    db.commit.assert_awaited_once()
