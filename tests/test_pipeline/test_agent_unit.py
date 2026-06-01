from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from matcher.indexing.search import SearchCandidate
from matcher.pipeline import agent


class _ToolFunction:
    def __init__(self, name: str, arguments: str) -> None:
        self.name = name
        self.arguments = arguments


class _ToolCall:
    def __init__(self, name: str, arguments: str, call_id: str = "call-1") -> None:
        self.id = call_id
        self.function = _ToolFunction(name, arguments)


class _Message:
    def __init__(
        self,
        content: str | None = None,
        tool_calls: list[_ToolCall] | None = None,
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls


class _Choice:
    def __init__(self, message: _Message) -> None:
        self.message = message


class _Usage:
    prompt_tokens = 3
    completion_tokens = 5


class _Response:
    def __init__(self, message: _Message) -> None:
        self.choices = [_Choice(message)]
        self.usage = _Usage()


class _Client:
    def __init__(
        self,
        responses: list[_Response] | None = None,
        side_effect: Exception | None = None,
    ) -> None:
        create = AsyncMock(side_effect=side_effect or responses)
        self.chat = type(
            "Chat",
            (),
            {"completions": type("Completions", (), {"create": create})()},
        )()


class _Tracker:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def record(self, **kwargs) -> None:
        self.records.append(kwargs)


def _candidate() -> SearchCandidate:
    return SearchCandidate(
        product_id="p1",
        name="Pump",
        normalized_name="pump",
        article="A-1",
        brand="Brand",
        category_path="Root / Pumps",
        unit="pcs",
    )


def test_web_search_formats_results_and_handles_errors(monkeypatch: pytest.MonkeyPatch):
    class Searcher:
        def __init__(self, timeout: int) -> None:
            assert timeout == 10

        def text(self, query: str, max_results: int):
            assert query == "pump"
            assert max_results == 2
            return [{"title": "Title", "body": "Body"}]

    monkeypatch.setattr(agent, "DDGS", Searcher)
    assert agent._web_search("pump", max_results=2) == "Title: Title\nSnippet: Body"

    class EmptySearcher:
        def __init__(self, timeout: int) -> None:
            pass

        def text(self, query: str, max_results: int):
            return []

    monkeypatch.setattr(agent, "DDGS", EmptySearcher)
    assert agent._web_search("pump") == "No web results found."

    class FailingSearcher:
        def __init__(self, timeout: int) -> None:
            pass

        def text(self, query: str, max_results: int):
            raise RuntimeError("offline")

    monkeypatch.setattr(agent, "DDGS", FailingSearcher)
    assert "Web search failed: offline" in agent._web_search("pump")


@pytest.mark.asyncio
async def test_catalog_search_formats_candidates_and_empty(monkeypatch: pytest.MonkeyPatch):
    async def fake_search(**_kwargs):
        return [_candidate()]

    monkeypatch.setattr(agent, "hybrid_search", fake_search)
    result = await agent._catalog_search("pump", session=object())
    assert "ID: p1 | Name: Pump | Article: A-1 | Brand: Brand" in result

    async def empty_search(**_kwargs):
        return []

    monkeypatch.setattr(agent, "hybrid_search", empty_search)
    assert (
        await agent._catalog_search("pump", session=object())
        == "No catalog matches found for that query."
    )


def test_decompose_query_and_system_prompt_variants():
    decomposed = agent._decompose_query("Насос Brand A-1 25 мм")
    assert "normalized_text" in decomposed
    assert "tokens" in decomposed

    no_candidates = agent._build_system_prompt("raw", [], {"brand": "Brand", "empty": []})
    with_candidates = agent._build_system_prompt("raw", ["ID: p1"], None)

    assert "No candidates were found" in no_candidates
    assert "Some candidates were found" in with_candidates
    assert "brand: Brand" in no_candidates


@pytest.mark.asyncio
async def test_resolve_agentically_returns_none_without_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(type(agent.settings), "active_llm_api_key", property(lambda _s: "none"))

    assert await agent.resolve_agentically("raw", [], session=object()) is None


@pytest.mark.asyncio
async def test_resolve_agentically_maps_no_match_final_decision(
    monkeypatch: pytest.MonkeyPatch,
):
    final_call = _ToolCall(
        "final_decision",
        '{"decision_type":"no_match","product_id":"p1","reasoning":"not same"}',
    )
    client = _Client([_Response(_Message(tool_calls=[final_call]))])
    monkeypatch.setattr(type(agent.settings), "active_llm_api_key", property(lambda _s: "key"))
    monkeypatch.setattr(agent, "make_llm_client", lambda: (client, "model", {}))

    result = await agent.resolve_agentically("raw", [], session=object())

    assert result == {"status": "no_match", "product_id": None, "reasoning": "not same"}


@pytest.mark.asyncio
async def test_resolve_agentically_maps_final_decisions_and_tracks_tokens(
    monkeypatch: pytest.MonkeyPatch,
):
    final_call = _ToolCall(
        "final_decision",
        '{"decision_type":"likely_match","product_id":"p1","reasoning":"close"}',
    )
    client = _Client([_Response(_Message(tool_calls=[final_call]))])
    tracker = _Tracker()
    monkeypatch.setattr(type(agent.settings), "active_llm_api_key", property(lambda _s: "key"))
    monkeypatch.setattr(agent.settings, "llm_provider", "openai")
    monkeypatch.setattr(agent, "make_llm_client", lambda: (client, "model", {}))

    result = await agent.resolve_agentically(
        "raw",
        [{"candidate": _candidate()}],
        session=object(),
        extracted_attrs={"brand": "Brand"},
        token_tracker=tracker,
    )

    assert result == {"status": "review_needed", "product_id": "p1", "reasoning": "close"}
    assert tracker.records[0]["operation"] == "agent"


@pytest.mark.asyncio
async def test_resolve_agentically_runs_tools_then_final_decision(
    monkeypatch: pytest.MonkeyPatch,
):
    tool_calls = [
        _ToolCall("decompose_query", '{"query":"pump"}', "decompose"),
        _ToolCall("search_catalog", '{"query":"pump"}', "catalog"),
        _ToolCall("web_search", '{"query":"pump"}', "web"),
        _ToolCall("unknown", "not-json", "unknown"),
    ]
    final_call = _ToolCall(
        "final_decision",
        '{"decision_type":"exact_match","product_id":"p1","reasoning":"same"}',
    )
    client = _Client(
        [
            _Response(_Message(tool_calls=tool_calls)),
            _Response(_Message(content="thinking only")),
            _Response(_Message(tool_calls=[final_call])),
        ]
    )
    monkeypatch.setattr(type(agent.settings), "active_llm_api_key", property(lambda _s: "key"))
    monkeypatch.setattr(agent, "make_llm_client", lambda: (client, "model", {}))
    monkeypatch.setattr(agent, "_web_search", lambda query: f"web {query}")
    monkeypatch.setattr(agent, "_decompose_query", lambda query: f"decomposed {query}")
    monkeypatch.setattr(agent, "_catalog_search", AsyncMock(return_value="catalog result"))

    result = await agent.resolve_agentically("raw", [], session=object())

    assert result == {"status": "auto_match", "product_id": "p1", "reasoning": "same"}
    messages = client.chat.completions.create.await_args_list[-1].kwargs["messages"]
    assert any(m.get("content") == "Unknown tool." for m in messages)
    assert any("Please call `final_decision`" in m.get("content", "") for m in messages)


@pytest.mark.asyncio
async def test_resolve_agentically_handles_api_error_and_loop_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(type(agent.settings), "active_llm_api_key", property(lambda _s: "key"))

    failing_client = _Client(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(agent, "make_llm_client", lambda: (failing_client, "model", {}))
    assert await agent.resolve_agentically("raw", [], session=object()) is None

    looping_client = _Client([_Response(_Message(content="still thinking")) for _ in range(6)])
    monkeypatch.setattr(agent, "make_llm_client", lambda: (looping_client, "model", {}))
    assert await agent.resolve_agentically("raw", [], session=object()) is None
