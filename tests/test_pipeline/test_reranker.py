"""Tests for reranker fallback paths."""

from unittest.mock import AsyncMock, patch

from matcher.indexing.search import SearchCandidate
from matcher.pipeline.reranker import RerankResult, _fallback_rerank, rerank_candidates


def _make_candidate(pid="prod_1", name="Product 1", rrf=0.5):
    return SearchCandidate(product_id=pid, name=name, normalized_name=name.lower(), rrf_score=rrf)


class TestReranker:
    async def test_empty_candidates_returns_empty(self):
        result = await rerank_candidates("query", [])
        assert result == []

    @patch("matcher.pipeline.reranker.settings")
    async def test_rerank_disabled_returns_fallback(self, mock_settings):
        mock_settings.rerank_enabled = False
        candidates = [_make_candidate(rrf=0.8), _make_candidate(pid="p2", rrf=0.3)]
        result = await rerank_candidates("query", candidates)
        assert len(result) > 0
        assert isinstance(result[0], RerankResult)
        # Sorted by rrf descending
        assert result[0].rerank_score >= result[-1].rerank_score

    @patch("matcher.pipeline.reranker.provider_circuit")
    @patch("matcher.pipeline.reranker.settings")
    async def test_provider_not_found_returns_fallback(self, mock_settings, mock_circuit):
        mock_settings.rerank_enabled = True
        mock_settings.rerank_provider = "nonexistent"
        mock_settings.providers_registry = {}
        mock_settings.rerank_top_n = 10
        candidates = [_make_candidate()]
        result = await rerank_candidates("query", candidates)
        assert len(result) == 1

    @patch("matcher.pipeline.reranker.provider_circuit")
    @patch("matcher.pipeline.reranker.settings")
    async def test_circuit_breaker_open_returns_fallback(self, mock_settings, mock_circuit):
        mock_settings.rerank_enabled = True
        mock_settings.rerank_provider = "cohere"
        mock_settings.providers_registry = {"cohere": {"api_key": "key"}}
        mock_settings.rerank_top_n = 10
        mock_circuit.is_available.return_value = False
        candidates = [_make_candidate()]
        result = await rerank_candidates("query", candidates)
        assert len(result) == 1

    def test_fallback_sorts_by_rrf_descending(self):
        candidates = [
            _make_candidate(pid=f"p{i}", rrf=score)
            for i, score in enumerate([0.1, 0.5, 0.3, 0.9, 0.7])
        ]
        result = _fallback_rerank(candidates, top_n=5)
        scores = [r.rerank_score for r in result]
        assert scores == sorted(scores, reverse=True)
        assert scores[0] == 0.9

    def test_fallback_respects_top_n(self):
        candidates = [_make_candidate(pid=f"p{i}", rrf=i * 0.1) for i in range(10)]
        result = _fallback_rerank(candidates, top_n=3)
        assert len(result) == 3

    @patch("matcher.pipeline.reranker.PROVIDER_CAPABILITIES")
    @patch("matcher.pipeline.reranker.provider_circuit")
    @patch("matcher.pipeline.reranker.settings")
    async def test_provider_lacks_capability_returns_fallback(
        self, mock_settings, mock_circuit, mock_caps
    ):
        mock_settings.rerank_enabled = True
        mock_settings.rerank_provider = "openai"
        mock_settings.providers_registry = {"openai": {"api_key": "key"}}
        mock_settings.rerank_top_n = 10
        mock_circuit.is_available.return_value = True
        # Provider exists but does not support reranking
        cap = type("Cap", (), {"supports_rerank": False})()
        mock_caps.get.return_value = cap
        candidates = [_make_candidate()]
        result = await rerank_candidates("query", candidates)
        assert len(result) == 1
        assert result[0].rerank_score == 0.5  # fallback uses rrf_score

    @patch("matcher.pipeline.reranker._http_rerank", new_callable=AsyncMock)
    @patch("matcher.pipeline.reranker.PROVIDER_CAPABILITIES")
    @patch("matcher.pipeline.reranker.provider_circuit")
    @patch("matcher.pipeline.reranker.settings")
    async def test_provider_exception_records_failure_and_falls_back(
        self, mock_settings, mock_circuit, mock_caps, mock_http_rerank
    ):
        mock_settings.rerank_enabled = True
        mock_settings.rerank_provider = "cohere"
        mock_settings.providers_registry = {"cohere": {"api_key": "key"}}
        mock_settings.rerank_top_n = 10
        mock_circuit.is_available.return_value = True
        mock_caps.get.return_value = None  # no capability entry = allowed
        mock_http_rerank.side_effect = RuntimeError("API down")
        candidates = [_make_candidate(rrf=0.7)]
        result = await rerank_candidates("query", candidates)
        # Should record failure on the circuit breaker
        mock_circuit.record_failure.assert_called_once_with("cohere")
        # Should fall back gracefully
        assert len(result) == 1
        assert result[0].rerank_score == 0.7  # fallback uses rrf_score

    @patch("matcher.pipeline.reranker._http_rerank", new_callable=AsyncMock)
    @patch("matcher.pipeline.reranker.PROVIDER_CAPABILITIES")
    @patch("matcher.pipeline.reranker.provider_circuit")
    @patch("matcher.pipeline.reranker.settings")
    async def test_successful_rerank_records_success(
        self, mock_settings, mock_circuit, mock_caps, mock_http_rerank
    ):
        mock_settings.rerank_enabled = True
        mock_settings.rerank_provider = "cohere"
        mock_settings.providers_registry = {"cohere": {"api_key": "key"}}
        mock_settings.rerank_top_n = 10
        mock_circuit.is_available.return_value = True
        mock_caps.get.return_value = None
        candidate = _make_candidate(rrf=0.5)
        mock_http_rerank.return_value = [RerankResult(candidate=candidate, rerank_score=0.95)]
        result = await rerank_candidates("query", [candidate])
        mock_circuit.record_success.assert_called_once_with("cohere")
        assert result[0].rerank_score == 0.95
