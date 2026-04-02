from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from matcher.queueing import enqueue_request_job


class TestEnqueueRequestJob:
    @pytest.mark.asyncio
    async def test_success_promotes_request_to_queued(self, mock_db_session, mock_arq_pool):
        with patch("matcher.queueing.MatchRepo") as MockRepo:
            repo = MockRepo.return_value
            repo.update_request_status = AsyncMock()

            await enqueue_request_job(
                db=mock_db_session,
                arq_pool=mock_arq_pool,
                request_id="req_1",
                job_name="batch_match",
                queue_name="match",
            )

        repo.update_request_status.assert_awaited_once_with("req_1", "queued", error_message=None)
        mock_arq_pool.enqueue_job.assert_awaited_once()
        assert mock_db_session.commit.await_count == 1

    @pytest.mark.asyncio
    async def test_failure_marks_request_failed(self, mock_db_session, mock_arq_pool):
        mock_arq_pool.enqueue_job.side_effect = RuntimeError("redis down")

        with patch("matcher.queueing.MatchRepo") as MockRepo:
            repo = MockRepo.return_value
            repo.update_request_status = AsyncMock()

            with pytest.raises(HTTPException) as exc:
                await enqueue_request_job(
                    db=mock_db_session,
                    arq_pool=mock_arq_pool,
                    request_id="req_2",
                    job_name="batch_match",
                    queue_name="match",
                )

        assert exc.value.status_code == 503
        repo.update_request_status.assert_awaited_once()
        args, kwargs = repo.update_request_status.await_args
        assert args == ("req_2", "failed")
        assert "enqueue_failed" in kwargs["error_message"]
        assert mock_db_session.commit.await_count == 1
