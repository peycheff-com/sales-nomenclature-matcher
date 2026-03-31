"""Tests that per-item errors in batch_match are recorded in the database."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from matcher.worker.tasks import batch_match


class TestBatchItemErrorTracking:
    """When match_single raises, the error must be persisted via update_item_result."""

    @pytest.mark.asyncio
    async def test_item_error_recorded_in_decision_trace(self):
        # -- arrange ----------------------------------------------------------
        mock_session = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_ctx)

        fake_request = MagicMock()
        fake_request.supplier_id = "sup_1"

        fake_item = MagicMock()
        fake_item.request_item_id = "item_42"
        fake_item.raw_text = "broken item"
        fake_item.line_id = "line_1"

        mock_repo = MagicMock()
        mock_repo.get_request = AsyncMock(return_value=fake_request)
        mock_repo.update_request_status = AsyncMock()
        mock_repo.get_request_items = AsyncMock(return_value=([fake_item], 1))
        mock_repo.update_item_result = AsyncMock()

        error_message = "something went wrong in pipeline"

        # MatchRepo and match_single are imported locally inside batch_match,
        # so we patch them at their source modules.
        with (
            patch(
                "matcher.db.repos.match.MatchRepo",
                return_value=mock_repo,
            ),
            patch(
                "matcher.pipeline.orchestrator.match_single",
                side_effect=RuntimeError(error_message),
            ),
        ):
            # -- act ----------------------------------------------------------
            result = await batch_match({"db_factory": mock_factory}, "req_1")

        # -- assert -----------------------------------------------------------
        mock_repo.update_item_result.assert_called_once()
        kw = mock_repo.update_item_result.call_args.kwargs

        assert kw["status"] == "no_match"
        assert kw["confidence"] == 0.0

        trace = kw["decision_trace_json"]
        assert error_message in trace["error"]
        assert trace["stage"] == "pipeline"

        # The overall batch should still complete successfully
        assert result["status"] == "done"
        assert result["processed"] == 1
