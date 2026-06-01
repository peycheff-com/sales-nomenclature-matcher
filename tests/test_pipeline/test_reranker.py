"""Tests for reranker fallback paths."""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, patch

import pytest

from matcher.indexing.search import SearchCandidate
from matcher.pipeline import reranker
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

    @patch("matcher.pipeline.reranker._local_rerank", new_callable=AsyncMock)
    @patch("matcher.pipeline.reranker.provider_circuit")
    @patch("matcher.pipeline.reranker.settings")
    async def test_local_provider_path_records_success(
        self, mock_settings, mock_circuit, mock_local_rerank
    ):
        mock_settings.rerank_enabled = True
        mock_settings.rerank_provider = "local"
        mock_settings.providers_registry = {"local": {"enabled": True}}
        mock_settings.rerank_top_n = 10
        mock_circuit.is_available.return_value = True
        candidate = _make_candidate(rrf=0.5)
        mock_local_rerank.return_value = [RerankResult(candidate=candidate, rerank_score=0.8)]

        result = await rerank_candidates("query", [candidate])

        mock_circuit.record_success.assert_called_once_with("local")
        assert result[0].rerank_score == 0.8

    @patch("matcher.pipeline.reranker._llm_rerank", new_callable=AsyncMock)
    @patch("matcher.pipeline.reranker.provider_circuit")
    @patch("matcher.pipeline.reranker.settings")
    async def test_llm_fallback_provider_requires_api_key_and_can_succeed(
        self, mock_settings, mock_circuit, mock_llm_rerank
    ):
        mock_settings.rerank_enabled = True
        mock_settings.rerank_provider = "llm-fallback"
        mock_settings.providers_registry = {"llm-fallback": {"enabled": True}}
        mock_settings.rerank_top_n = 10
        mock_settings.active_llm_api_key = "none"
        mock_circuit.is_available.return_value = True
        candidate = _make_candidate(rrf=0.4)

        fallback = await rerank_candidates("query", [candidate])
        assert fallback[0].rerank_score == 0.4

        mock_settings.active_llm_api_key = "key"
        mock_llm_rerank.return_value = [RerankResult(candidate=candidate, rerank_score=0.9)]

        result = await rerank_candidates("query", [candidate])

        mock_circuit.record_success.assert_called_once_with("llm-fallback")
        assert result[0].rerank_score == 0.9

    @patch("matcher.pipeline.reranker.provider_circuit")
    @patch("matcher.pipeline.reranker.settings")
    async def test_unimplemented_rerank_provider_falls_back(self, mock_settings, mock_circuit):
        mock_settings.rerank_enabled = True
        mock_settings.rerank_provider = "custom"
        mock_settings.providers_registry = {"custom": {"enabled": True}}
        mock_settings.rerank_top_n = 10
        mock_circuit.is_available.return_value = True
        candidate = _make_candidate(rrf=0.3)

        result = await rerank_candidates("query", [candidate])

        assert result[0].rerank_score == 0.3


def test_candidate_to_document_omits_missing_parts():
    candidate = SearchCandidate(
        product_id="p1",
        name="Pump",
        normalized_name="pump",
        brand="Brand",
        article="A-1",
        category_path="Root / Pumps",
    )

    assert reranker._candidate_to_document(candidate) == "Brand | Pump | A-1 | Root / Pumps"
    assert reranker._candidate_to_document(_make_candidate(name="Only name")) == "Only name"


@pytest.mark.asyncio
async def test_local_rerank_scores_with_cross_encoder(monkeypatch: pytest.MonkeyPatch):
    class CrossEncoder:
        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

        def predict(self, pairs: list[list[str]]) -> list[float]:
            assert pairs[0][0] == "query"
            return [0.2, 0.9]

    module = types.ModuleType("sentence_transformers")
    module.CrossEncoder = CrossEncoder
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    monkeypatch.setattr(reranker, "_local_scorer", None, raising=False)
    monkeypatch.setattr(reranker.settings, "llm_rerank_model", "local-model")

    result = await reranker._local_rerank(
        "query",
        [_make_candidate(pid="low"), _make_candidate(pid="high")],
        top_n=2,
    )

    assert [r.candidate.product_id for r in result] == ["high", "low"]
    assert result[0].rerank_score == 0.9


@pytest.mark.asyncio
async def test_local_rerank_falls_back_without_optional_dependency(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)

    result = await reranker._local_rerank("query", [_make_candidate(rrf=0.4)], top_n=1)

    assert result[0].rerank_score == 0.4


@pytest.mark.asyncio
async def test_http_rerank_parses_and_normalizes_provider_scores(
    monkeypatch: pytest.MonkeyPatch,
):
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "results": [
                    {"index": 0, "relevance_score": 2.0},
                    {"index": 1, "relevance_score": 6.0},
                ],
                "meta": {"billed_units": {"search_units": 3}},
            }

    class Client:
        def __init__(self) -> None:
            self.posts = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info) -> None:
            return None

        async def post(self, endpoint: str, json: dict, headers: dict, timeout: float) -> Response:
            self.posts.append((endpoint, json, headers, timeout))
            return Response()

    class Tracker:
        def __init__(self) -> None:
            self.records = []

        def record(self, **kwargs) -> None:
            self.records.append(kwargs)

    client = Client()
    tracker = Tracker()
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", lambda: client)
    monkeypatch.setattr(reranker.settings, "llm_rerank_model", "")

    result = await reranker._http_rerank(
        "query",
        [_make_candidate(pid="p1"), _make_candidate(pid="p2")],
        top_n=2,
        provider_id="cohere",
        provider_config={"base_url": "https://api.example", "api_key": "key"},
        token_tracker=tracker,
    )

    assert [r.rerank_score for r in result] == [0.0, 1.0]
    assert client.posts[0][0] == "https://api.example/rerank"
    assert tracker.records[0]["prompt_tokens"] == 3


@pytest.mark.asyncio
async def test_http_rerank_parses_dashscope_equal_scores(monkeypatch: pytest.MonkeyPatch):
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "output": {
                    "results": [
                        {"index": 0, "relevance_score": 5.0},
                        {"index": 1, "relevance_score": 5.0},
                    ]
                }
            }

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info) -> None:
            return None

        async def post(self, *_args, **_kwargs) -> Response:
            return Response()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", lambda: Client())
    monkeypatch.setattr(reranker.settings, "llm_rerank_model", "")

    result = await reranker._http_rerank(
        "query",
        [_make_candidate(pid="p1"), _make_candidate(pid="p2")],
        top_n=2,
        provider_id="dashscope",
        provider_config={"base_url": "https://dash", "api_key": "key"},
    )

    assert [r.rerank_score for r in result] == [1.0, 1.0]


@pytest.mark.asyncio
async def test_http_rerank_equal_zero_scores_stay_zero(monkeypatch: pytest.MonkeyPatch):
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "results": [
                    {"index": 0, "relevance_score": 0.0},
                    {"index": 1, "relevance_score": 0.0},
                ]
            }

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info) -> None:
            return None

        async def post(self, *_args, **_kwargs) -> Response:
            return Response()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", lambda: Client())

    result = await reranker._http_rerank(
        "query",
        [_make_candidate(pid="p1"), _make_candidate(pid="p2")],
        top_n=2,
        provider_id="cohere",
        provider_config={"base_url": "https://cohere", "api_key": "key"},
    )

    assert [r.rerank_score for r in result] == [0.0, 0.0]


@pytest.mark.asyncio
async def test_llm_rerank_parses_code_fenced_json_and_tracks_usage(
    monkeypatch: pytest.MonkeyPatch,
):
    class Usage:
        prompt_tokens = 5
        completion_tokens = 7

    class Message:
        content = '```json\n[{"index":1,"score":0.7},{"index":0,"score":0.2}]\n```'

    class Choice:
        message = Message()

    class Response:
        choices = [Choice()]
        usage = Usage()

    class Client:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.chat = type(
                "Chat",
                (),
                {
                    "completions": type(
                        "Completions",
                        (),
                        {"create": AsyncMock(return_value=Response())},
                    )()
                },
            )()

    class Tracker:
        def __init__(self) -> None:
            self.records = []

        def record(self, **kwargs) -> None:
            self.records.append(kwargs)

    tracker = Tracker()
    monkeypatch.setattr(reranker, "AsyncOpenAI", Client)
    monkeypatch.setattr(reranker.settings, "llm_provider", "openrouter")
    monkeypatch.setattr(reranker.settings, "llm_rerank_model", "qwen-rerank")
    monkeypatch.setattr(type(reranker.settings), "active_llm_api_key", property(lambda _s: "key"))
    monkeypatch.setattr(type(reranker.settings), "active_llm_base_url", property(lambda _s: "url"))

    result = await reranker._llm_rerank(
        "query",
        [_make_candidate(pid="p1"), _make_candidate(pid="p2")],
        top_n=2,
        token_tracker=tracker,
    )

    assert [r.candidate.product_id for r in result] == ["p2", "p1"]
    assert [r.rerank_score for r in result] == [1.0, 0.0]
    assert tracker.records[0]["operation"] == "llm_rerank"


@pytest.mark.asyncio
async def test_llm_rerank_invalid_json_returns_fallback(monkeypatch: pytest.MonkeyPatch):
    class Message:
        content = "not-json"

    class Choice:
        message = Message()

    class Response:
        choices = [Choice()]
        usage = None

    class Client:
        def __init__(self, **_kwargs) -> None:
            self.chat = type(
                "Chat",
                (),
                {
                    "completions": type(
                        "Completions",
                        (),
                        {"create": AsyncMock(return_value=Response())},
                    )()
                },
            )()

    monkeypatch.setattr(reranker, "AsyncOpenAI", Client)
    monkeypatch.setattr(type(reranker.settings), "active_llm_api_key", property(lambda _s: "key"))
    monkeypatch.setattr(type(reranker.settings), "active_llm_base_url", property(lambda _s: "url"))

    result = await reranker._llm_rerank("query", [_make_candidate(rrf=0.6)], top_n=1)

    assert result[0].rerank_score == 0.6


@pytest.mark.asyncio
async def test_llm_rerank_equal_positive_scores_normalize_to_one(
    monkeypatch: pytest.MonkeyPatch,
):
    class Message:
        content = '[{"index":0,"score":5},{"index":1,"score":5}]'

    class Choice:
        message = Message()

    class Response:
        choices = [Choice()]
        usage = None

    class Client:
        def __init__(self, **_kwargs) -> None:
            self.chat = type(
                "Chat",
                (),
                {
                    "completions": type(
                        "Completions",
                        (),
                        {"create": AsyncMock(return_value=Response())},
                    )()
                },
            )()

    monkeypatch.setattr(reranker, "AsyncOpenAI", Client)
    monkeypatch.setattr(type(reranker.settings), "active_llm_api_key", property(lambda _s: "key"))
    monkeypatch.setattr(type(reranker.settings), "active_llm_base_url", property(lambda _s: "url"))

    result = await reranker._llm_rerank(
        "query",
        [_make_candidate(pid="p1"), _make_candidate(pid="p2")],
        top_n=2,
    )

    assert [r.rerank_score for r in result] == [1.0, 1.0]
