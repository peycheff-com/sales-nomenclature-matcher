"""Tests that MatchRepo produces timezone-aware datetimes (B1)."""

from __future__ import annotations

from datetime import UTC
from unittest.mock import AsyncMock, MagicMock

import pytest

from matcher.db.repos.match import MatchRepo


def _capture_execute(calls: list):
    """Return an async mock that records every statement passed to session.execute()."""

    async def _execute(stmt, *args, **kwargs):
        calls.append(stmt)
        return MagicMock(rowcount=1)

    return _execute


@pytest.mark.asyncio
async def test_update_request_status_running_uses_aware_datetime():
    """started_at must carry tzinfo when status is 'running'."""
    calls: list = []
    session = AsyncMock()
    session.execute = _capture_execute(calls)

    repo = MatchRepo(session)
    await repo.update_request_status("req_123", "running")

    assert len(calls) == 1
    stmt = calls[0]
    # Compile the UPDATE statement and inspect bound parameters.
    compiled = stmt.compile(compile_kwargs={"literal_binds": False})
    params = compiled.params
    assert "started_at" in params, "started_at should be in the UPDATE params"
    started_at = params["started_at"]
    assert started_at.tzinfo is not None, "started_at must be timezone-aware"
    assert started_at.tzinfo == UTC


@pytest.mark.asyncio
async def test_update_request_status_done_uses_aware_datetime():
    """finished_at must carry tzinfo when status is 'done'."""
    calls: list = []
    session = AsyncMock()
    session.execute = _capture_execute(calls)

    repo = MatchRepo(session)
    await repo.update_request_status("req_456", "done")

    assert len(calls) == 1
    stmt = calls[0]
    compiled = stmt.compile(compile_kwargs={"literal_binds": False})
    params = compiled.params
    assert "finished_at" in params, "finished_at should be in the UPDATE params"
    finished_at = params["finished_at"]
    assert finished_at.tzinfo is not None, "finished_at must be timezone-aware"
    assert finished_at.tzinfo == UTC


@pytest.mark.asyncio
async def test_update_item_review_uses_aware_datetime():
    """reviewed_at must carry tzinfo."""
    calls: list = []
    session = AsyncMock()
    session.execute = _capture_execute(calls)

    repo = MatchRepo(session)
    await repo.update_item_review("item_abc", "approved", "prod_1", "user@test.com")

    assert len(calls) == 1
    stmt = calls[0]
    compiled = stmt.compile(compile_kwargs={"literal_binds": False})
    params = compiled.params
    assert "reviewed_at" in params, "reviewed_at should be in the UPDATE params"
    reviewed_at = params["reviewed_at"]
    assert reviewed_at.tzinfo is not None, "reviewed_at must be timezone-aware"
    assert reviewed_at.tzinfo == UTC
