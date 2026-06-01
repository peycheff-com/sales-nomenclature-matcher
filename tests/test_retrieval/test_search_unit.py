from __future__ import annotations

from typing import Any

import pytest

from matcher.indexing import search

_ROW = (
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
    0.7,
    0.8,
    1,
    0.42,
    1,
)


class _Result:
    def __init__(self, *, scalar_value: int | None = None, rows: list[tuple] | None = None) -> None:
        self._scalar_value = scalar_value
        self._rows = rows or []

    def scalar(self) -> int | None:
        return self._scalar_value

    def fetchall(self) -> list[tuple]:
        return self._rows


class _Session:
    def __init__(self, results: list[_Result]) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    async def execute(self, statement, params: dict[str, Any] | None = None) -> _Result:
        self.calls.append((str(statement), params))
        return self.results.pop(0)


@pytest.fixture(autouse=True)
def reset_catalog_count():
    search.invalidate_catalog_count()
    yield
    search.invalidate_catalog_count()


@pytest.mark.asyncio
async def test_get_catalog_count_uses_cache_until_invalidated():
    session = _Session([_Result(scalar_value=7), _Result(scalar_value=9)])

    assert await search.get_catalog_count(session) == 7
    assert await search.get_catalog_count(session) == 7
    assert len(session.calls) == 1

    search.invalidate_catalog_count()

    assert await search.get_catalog_count(session) == 9
    assert len(session.calls) == 2


@pytest.mark.asyncio
async def test_full_catalog_search_maps_rows_and_uses_article_and_vector_params():
    session = _Session([_Result(rows=[_ROW])])

    candidates = await search._full_catalog_search(
        session=session,
        query_text="Pump",
        normalized_text="pump",
        query_embedding=[0.1, 0.2],
        rrf_k=60,
        top_n=5,
        article_hint="A-1",
    )

    assert candidates == [
        search.SearchCandidate(
            product_id="p1",
            name="Pump",
            normalized_name="pump",
            article="A-1",
            brand="Brand",
            normalized_brand="brand",
            manufacturer_code="M-1",
            category_id="cat",
            category_path="Root / Cat",
            unit="pcs",
            packaging="box",
            search_document="pump brand",
            lexical_score=0.7,
            semantic_score=0.8,
            exact_match=True,
            rrf_score=0.42,
            retrieval_rank=1,
        )
    ]
    _, params = session.calls[0]
    assert params["article_hint"] == "A-1"
    assert params["query_vector"] == "[0.1, 0.2]"


@pytest.mark.asyncio
async def test_hybrid_search_uses_full_catalog_path_for_small_catalog(
    monkeypatch: pytest.MonkeyPatch,
):
    session = _Session([_Result(scalar_value=1), _Result(rows=[_ROW])])
    monkeypatch.setattr(search.settings, "small_catalog_threshold", 10)

    async def fail_embed(*_args, **_kwargs):
        raise RuntimeError("no embeddings")

    monkeypatch.setattr(search, "embed_single", fail_embed)

    candidates = await search.hybrid_search("Pump", "pump", session, top_n=5)

    assert len(candidates) == 1
    assert candidates[0].product_id == "p1"
    assert "query_vector" not in session.calls[1][1]


@pytest.mark.asyncio
async def test_hybrid_search_large_catalog_applies_filters_and_precomputed_embedding(
    monkeypatch: pytest.MonkeyPatch,
):
    session = _Session([_Result(scalar_value=1000), _Result(rows=[_ROW])])
    monkeypatch.setattr(search.settings, "small_catalog_threshold", 10)

    candidates = await search.hybrid_search(
        "Pump",
        "pump",
        session,
        top_n=10,
        article_hint="A-1",
        category_id="cat",
        brand_hint="brand",
        query_embedding=[0.3],
    )

    assert candidates[0].semantic_score == 0.8
    sql, params = session.calls[1]
    assert "AND p.category_id = :category_id AND p.normalized_brand = :brand_hint" in sql
    assert params["article_hint"] == "A-1"
    assert params["category_id"] == "cat"
    assert params["brand_hint"] == "brand"
    assert params["query_vector"] == "[0.3]"


@pytest.mark.asyncio
async def test_hybrid_search_uses_relaxed_fallback_when_primary_has_no_rows(
    monkeypatch: pytest.MonkeyPatch,
):
    session = _Session([_Result(scalar_value=1000), _Result(rows=[]), _Result(rows=[_ROW])])
    monkeypatch.setattr(search.settings, "small_catalog_threshold", 10)

    candidates = await search.hybrid_search(
        "Pump",
        "pump alpha",
        session,
        top_n=20,
        category_id="cat",
        query_embedding=None,
    )

    assert candidates[0].product_id == "p1"
    _, fallback_params = session.calls[2]
    assert fallback_params["leading_word"] == "pump"
    assert fallback_params["top_n"] == 10
    assert fallback_params["category_id"] == "cat"
    assert "query_vector" not in fallback_params


@pytest.mark.asyncio
async def test_hybrid_search_large_catalog_falls_back_to_lexical_when_embedding_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    session = _Session([_Result(scalar_value=1000), _Result(rows=[_ROW])])
    monkeypatch.setattr(search.settings, "small_catalog_threshold", 10)

    async def fail_embed(*_args, **_kwargs):
        raise RuntimeError("embed down")

    monkeypatch.setattr(search, "embed_single", fail_embed)

    candidates = await search.hybrid_search("Pump", "pump", session, top_n=5)

    assert candidates[0].product_id == "p1"
    sql, params = session.calls[1]
    assert "WHERE false" in sql
    assert "query_vector" not in params


@pytest.mark.asyncio
async def test_relaxed_fallback_returns_empty_without_leading_word():
    session = _Session([])

    rows = await search._relaxed_fallback_search(
        session=session,
        normalized_text="123 ab",
        query_embedding=[0.1],
        top_n=5,
        rrf_k=60,
        filter_clause="",
    )

    assert rows == []
    assert session.calls == []


@pytest.mark.asyncio
async def test_relaxed_fallback_uses_semantic_cte_when_embedding_is_present():
    session = _Session([_Result(rows=[_ROW])])

    rows = await search._relaxed_fallback_search(
        session=session,
        normalized_text="pump alpha",
        query_embedding=[0.9],
        top_n=5,
        rrf_k=60,
        filter_clause="AND p.normalized_brand = :brand_hint",
        filter_params={"brand_hint": "brand"},
    )

    assert rows == [_ROW]
    sql, params = session.calls[0]
    assert "embedding_vector <=> :query_vector::vector" in sql
    assert params["query_vector"] == "[0.9]"
    assert params["brand_hint"] == "brand"
