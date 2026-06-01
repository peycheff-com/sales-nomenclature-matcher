"""Tests for token usage tracker."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from matcher.pipeline import token_tracker
from matcher.pipeline.token_tracker import COST_PER_1M, DEFAULT_COST, TokenTracker


class TestTokenTracker:
    def test_record_and_total_tokens(self):
        """Recording operations should accumulate total_tokens correctly."""
        tracker = TokenTracker(request_id="req_001")

        tracker.record("embed", "openai", "text-embedding-3-large", prompt_tokens=500)
        tracker.record(
            "llm_rerank",
            "openrouter",
            "gpt-4o-mini",
            prompt_tokens=1200,
            completion_tokens=300,
        )

        assert tracker.total_tokens == 500 + 1200 + 300

    def test_cost_known_model(self):
        """Cost for a known model should match the pricing table calculation."""
        tracker = TokenTracker(request_id="req_002")

        prompt_tokens = 1000
        completion_tokens = 500
        tracker.record(
            "llm_rerank",
            "openrouter",
            "gpt-4o-mini",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

        pricing = COST_PER_1M["gpt-4o-mini"]
        raw = (
            prompt_tokens * pricing["prompt"] + completion_tokens * pricing["completion"]
        ) / 1_000_000
        expected_cost = Decimal(str(round(raw, 6)))

        assert tracker.total_cost == expected_cost

    def test_cost_unknown_model(self):
        """Unknown model should fall back to DEFAULT_COST pricing."""
        tracker = TokenTracker(request_id="req_003")

        prompt_tokens = 2000
        completion_tokens = 1000
        tracker.record(
            "llm",
            "custom_provider",
            "totally-unknown-model-v9",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

        raw = (
            prompt_tokens * DEFAULT_COST["prompt"] + completion_tokens * DEFAULT_COST["completion"]
        ) / 1_000_000
        expected_cost = Decimal(str(round(raw, 6)))

        assert tracker.total_cost == expected_cost

    @pytest.mark.asyncio
    async def test_flush_writes_to_db(self):
        """flush() should execute an INSERT into the token_usage_log table."""
        tracker = TokenTracker(request_id="req_004")
        tracker.record("embed", "openai", "text-embedding-3-small", prompt_tokens=100)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.flush = AsyncMock()

        await tracker.flush(mock_session)

        mock_session.execute.assert_awaited_once()
        mock_session.flush.assert_awaited_once()

        # After flush, internal records should be cleared
        assert tracker.total_tokens == 0

    @pytest.mark.asyncio
    async def test_empty_flush(self):
        """flush() with no recorded operations should be a no-op."""
        tracker = TokenTracker(request_id="req_005")

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.flush = AsyncMock()

        await tracker.flush(mock_session)

        mock_session.execute.assert_not_awaited()
        mock_session.flush.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_flush_clears_records_when_db_write_fails(self):
        """flush() logs and clears accumulated records even when persistence fails."""
        tracker = TokenTracker(request_id="req_error")
        tracker.record("embed", "openai", "text-embedding-3-small", prompt_tokens=100)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=RuntimeError("db down"))
        mock_session.flush = AsyncMock()

        await tracker.flush(mock_session)

        mock_session.execute.assert_awaited_once()
        mock_session.flush.assert_not_awaited()
        assert tracker.total_tokens == 0

    def test_total_tokens_with_explicit_total(self):
        """When total_tokens is provided explicitly, it should be used instead of sum."""
        tracker = TokenTracker(request_id="req_006")
        tracker.record(
            "rerank",
            "cohere",
            "rerank-multilingual-v3.0",
            prompt_tokens=100,
            completion_tokens=0,
            total_tokens=42,
        )
        assert tracker.total_tokens == 42

    def test_multiple_records_cost_accumulates(self):
        """Costs from multiple records should be summed in total_cost."""
        tracker = TokenTracker(request_id="req_007")

        tracker.record(
            "embed",
            "openai",
            "text-embedding-3-large",
            prompt_tokens=1000,
        )
        tracker.record(
            "llm_rerank",
            "openai",
            "gpt-4o-mini",
            prompt_tokens=500,
            completion_tokens=200,
        )

        # Calculate expected costs individually
        embed_pricing = COST_PER_1M["text-embedding-3-large"]
        embed_cost = Decimal(
            str(
                round(
                    (1000 * embed_pricing["prompt"]) / 1_000_000,
                    6,
                )
            )
        )

        llm_pricing = COST_PER_1M["gpt-4o-mini"]
        llm_cost = Decimal(
            str(
                round(
                    (500 * llm_pricing["prompt"] + 200 * llm_pricing["completion"]) / 1_000_000,
                    6,
                )
            )
        )

        assert tracker.total_cost == embed_cost + llm_cost

    def test_estimate_cost_matches_pricing_by_prefix(self, monkeypatch: pytest.MonkeyPatch):
        """Versioned model names should match configured base model pricing."""
        monkeypatch.setitem(
            token_tracker.COST_PER_1M,
            "vendor/model",
            {"prompt": 1.0, "completion": 2.0},
        )

        assert token_tracker._estimate_cost("vendor/model:latest", 1000, 500) == Decimal(
            "0.002"
        )

    def test_load_pricing_falls_back_for_missing_or_invalid_config(self):
        """Pricing loading should tolerate missing or invalid YAML config files."""
        with patch("builtins.open", side_effect=FileNotFoundError):
            models, default = token_tracker._load_pricing()

        assert models == {}
        assert default == token_tracker._FALLBACK_DEFAULT_COST

        with patch("builtins.open", side_effect=RuntimeError("bad file")):
            models, default = token_tracker._load_pricing()

        assert models == {}
        assert default == token_tracker._FALLBACK_DEFAULT_COST
