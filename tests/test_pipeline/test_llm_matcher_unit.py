from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from matcher.indexing.search import SearchCandidate
from matcher.pipeline import llm_matcher


class _Result:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple]:
        return self._rows


class _Session:
    def __init__(self, rows: list[tuple]) -> None:
        self.rows = rows
        self.execute_count = 0

    async def execute(self, _statement) -> _Result:
        self.execute_count += 1
        return _Result(self.rows)


class _Usage:
    prompt_tokens = 11
    completion_tokens = 13


class _Message:
    def __init__(self, content: str) -> None:
        self.content = content


class _Choice:
    def __init__(self, content: str) -> None:
        self.message = _Message(content)


class _Response:
    def __init__(self, content: str) -> None:
        self.choices = [_Choice(content)]
        self.usage = _Usage()


class _Client:
    def __init__(self, *contents: str, side_effect: Exception | None = None) -> None:
        if side_effect:
            self.chat = type(
                "Chat",
                (),
                {
                    "completions": type(
                        "Completions",
                        (),
                        {"create": AsyncMock(side_effect=side_effect)},
                    )()
                },
            )()
        else:
            self.chat = type(
                "Chat",
                (),
                {
                    "completions": type(
                        "Completions",
                        (),
                        {"create": AsyncMock(side_effect=[_Response(c) for c in contents])},
                    )()
                },
            )()


class _Tracker:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def record(self, **kwargs) -> None:
        self.records.append(kwargs)


def _candidate(product_id: str = "p1") -> SearchCandidate:
    return SearchCandidate(
        product_id=product_id,
        name="Pump 25-40",
        normalized_name="pump 25-40",
        article="A-1",
        brand="Brand",
        unit="pcs",
        category_path="Root / Pumps",
    )


@pytest.fixture(autouse=True)
def reset_cache():
    llm_matcher.invalidate_catalog_cache()
    yield
    llm_matcher.invalidate_catalog_cache()


@pytest.mark.asyncio
async def test_get_cached_catalog_loads_once_and_maps_rows():
    row = (
        "p1",
        "Pump",
        "pump",
        "A-1",
        "Brand",
        "brand",
        "M-1",
        "cat",
        "Root / Cat",
        "pcs",
        "box",
        "pump brand",
    )
    session = _Session([row])

    catalog = await llm_matcher.get_cached_catalog(session)
    cached = await llm_matcher.get_cached_catalog(session)

    assert catalog is cached
    assert session.execute_count == 1
    assert catalog[0].product_id == "p1"
    assert catalog[0].packaging == "box"


def test_format_helpers_fill_missing_values():
    table = llm_matcher._format_catalog_table([SearchCandidate("p1", "Name", "name")])
    attrs = llm_matcher._format_attrs({"numbers": [25, 40]})

    assert table == "p1 | Name | — | — | — | —"
    assert attrs == {
        "brand": "—",
        "article": "—",
        "numbers": "25, 40",
        "unit": "—",
        "packaging": "—",
    }


@pytest.mark.asyncio
async def test_llm_match_parses_success_and_tracks_usage(monkeypatch: pytest.MonkeyPatch):
    client = _Client(
        '```json\n{"product_id":"p1","confidence":0.97,"reasoning":"same",'
        '"alternatives":[{"product_id":"p2"}]}\n```'
    )
    tracker = _Tracker()
    monkeypatch.setattr(
        llm_matcher,
        "make_llm_client",
        lambda model_override=None: (client, "m", {}),
    )

    result = await llm_matcher.llm_match(
        raw_text="raw",
        normalized_text="norm",
        extracted_attrs={"brand": "Brand"},
        candidates=[_candidate()],
        token_tracker=tracker,
    )

    assert result is not None
    assert result.product_id == "p1"
    assert result.confidence == 0.97
    assert result.alternatives == [{"product_id": "p2"}]
    assert tracker.records[0]["operation"] == "llm_match"
    assert tracker.records[0]["prompt_tokens"] == 11


@pytest.mark.asyncio
async def test_llm_match_returns_none_on_api_error_or_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
):
    bad_json_client = _Client("not-json")
    monkeypatch.setattr(
        llm_matcher,
        "make_llm_client",
        lambda model_override=None: (bad_json_client, "m", {}),
    )
    assert await llm_matcher.llm_match("raw", "norm", {}, [_candidate()]) is None

    failing_client = _Client(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(
        llm_matcher,
        "make_llm_client",
        lambda model_override=None: (failing_client, "m", {}),
    )
    assert await llm_matcher.llm_match("raw", "norm", {}, [_candidate()]) is None


@pytest.mark.asyncio
async def test_llm_match_batch_parses_entries_and_ignores_invalid_indices(
    monkeypatch: pytest.MonkeyPatch,
):
    client = _Client(
        '[{"item_index":0,"product_id":"p1","confidence":0.91,"reasoning":"ok"},'
        '{"item_index":99,"product_id":"ignored","confidence":1,"reasoning":"bad"}]'
    )
    tracker = _Tracker()
    monkeypatch.setattr(
        llm_matcher,
        "make_llm_client",
        lambda model_override=None: (client, "m", {}),
    )
    monkeypatch.setattr(llm_matcher.settings, "llm_matcher_batch_size", 10)

    results = await llm_matcher.llm_match_batch(
        [{"raw_text": "pump", "extracted_attrs": {"article": "A-1"}}, {"raw_text": "valve"}],
        [_candidate()],
        token_tracker=tracker,
    )

    assert results[0] is not None
    assert results[0].product_id == "p1"
    assert results[1] is None
    assert tracker.records[0]["completion_tokens"] == 13


@pytest.mark.asyncio
async def test_llm_match_batch_keeps_none_when_call_fails(monkeypatch: pytest.MonkeyPatch):
    client = _Client(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(
        llm_matcher,
        "make_llm_client",
        lambda model_override=None: (client, "m", {}),
    )
    monkeypatch.setattr(llm_matcher.settings, "llm_matcher_batch_size", 10)

    assert await llm_matcher.llm_match_batch([{"raw_text": "pump"}], [_candidate()]) == [None]
