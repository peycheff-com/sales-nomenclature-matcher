from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock

import pytest

from matcher.indexing import indexer


class _Result:
    def __init__(self, *, scalar_value: int | None = None, rows: list[tuple] | None = None) -> None:
        self._scalar_value = scalar_value
        self._rows = rows or []

    def scalar(self) -> int | None:
        return self._scalar_value

    def fetchall(self) -> list[tuple]:
        return self._rows


class _FakeConn:
    def __init__(self, batches: list[list[tuple]], total_products: int = 2) -> None:
        self.batches = list(batches)
        self.total_products = total_products
        self.statements: list[tuple[str, dict[str, Any] | None]] = []

    async def execute(self, statement, params: dict[str, Any] | None = None) -> _Result:
        sql = str(statement)
        self.statements.append((sql, params))
        if "SELECT count(*) FROM catalog_products" in sql:
            return _Result(scalar_value=self.total_products)
        if "SELECT p.product_id, p.search_document" in sql:
            return _Result(rows=self.batches.pop(0) if self.batches else [])
        return _Result()


class _FakeSession:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc_info) -> None:
        return None

    @asynccontextmanager
    async def begin(self):
        yield

    async def connection(self) -> _FakeConn:
        return self._conn


def _session_factory(conn: _FakeConn):
    def factory() -> _FakeSession:
        return _FakeSession(conn)

    return factory


class _FakeEngine:
    def __init__(self, conn: _FakeConn) -> None:
        self.conn = conn
        self.disposed = False

    @asynccontextmanager
    async def begin(self):
        yield self.conn

    async def dispose(self) -> None:
        self.disposed = True


@pytest.mark.asyncio
async def test_reindex_catalog_embeds_missing_products(monkeypatch: pytest.MonkeyPatch):
    conn = _FakeConn(batches=[[(1, "pump"), (2, None)]], total_products=2)
    embed = AsyncMock(return_value=[[0.1, 0.2], [0.3, 0.4]])
    monkeypatch.setattr(indexer, "embed_texts", embed)
    monkeypatch.setattr(indexer.settings, "embedding_provider", "openai")
    monkeypatch.setattr(
        indexer.uuid,
        "uuid4",
        lambda: type("UUID", (), {"hex": "abcdef1234567890"})(),
    )

    result = await indexer.reindex_catalog(
        embedding_model="model-a",
        embedding_version="v2",
        batch_size=10,
        session_factory=_session_factory(conn),
    )

    assert result == {
        "index_version_id": "idx_abcdef123456",
        "total_products": 2,
        "embedded_count": 2,
        "embedding_model": "model-a",
        "embedding_version": "v2",
    }
    embed.assert_awaited_once_with(["pump", ""], model="model-a")
    upsert_params = [
        params for sql, params in conn.statements if "INSERT INTO catalog_embeddings" in sql
    ]
    assert [params["vector"] for params in upsert_params] == ["[0.1, 0.2]", "[0.3, 0.4]"]
    assert any("UPDATE index_versions SET is_active = false" in sql for sql, _ in conn.statements)


@pytest.mark.asyncio
async def test_reindex_catalog_skips_embeddings_when_provider_disabled(
    monkeypatch: pytest.MonkeyPatch,
):
    conn = _FakeConn(batches=[], total_products=3)
    embed = AsyncMock()
    monkeypatch.setattr(indexer, "embed_texts", embed)
    monkeypatch.setattr(indexer.settings, "embedding_provider", "none")

    result = await indexer.reindex_catalog(session_factory=_session_factory(conn))

    assert result["total_products"] == 3
    assert result["embedded_count"] == 0
    embed.assert_not_called()
    assert not any("SELECT p.product_id, p.search_document" in sql for sql, _ in conn.statements)


@pytest.mark.asyncio
async def test_reindex_catalog_stops_when_no_missing_embeddings(monkeypatch: pytest.MonkeyPatch):
    conn = _FakeConn(batches=[[]], total_products=2)
    embed = AsyncMock()
    monkeypatch.setattr(indexer, "embed_texts", embed)
    monkeypatch.setattr(indexer.settings, "embedding_provider", "openai")

    result = await indexer.reindex_catalog(session_factory=_session_factory(conn))

    assert result["total_products"] == 2
    assert result["embedded_count"] == 0
    embed.assert_not_awaited()


@pytest.mark.asyncio
async def test_reindex_catalog_propagates_embedding_failures(monkeypatch: pytest.MonkeyPatch):
    conn = _FakeConn(batches=[[(1, "pump")]], total_products=1)
    monkeypatch.setattr(indexer.settings, "embedding_provider", "openai")
    monkeypatch.setattr(indexer, "embed_texts", AsyncMock(side_effect=RuntimeError("boom")))

    with pytest.raises(RuntimeError, match="boom"):
        await indexer.reindex_catalog(session_factory=_session_factory(conn))


@pytest.mark.asyncio
async def test_reindex_catalog_owns_and_disposes_engine(monkeypatch: pytest.MonkeyPatch):
    conn = _FakeConn(batches=[], total_products=0)
    engine = _FakeEngine(conn)
    monkeypatch.setattr(indexer, "create_async_engine", lambda _url: engine)
    monkeypatch.setattr(indexer.settings, "embedding_provider", "openai")

    result = await indexer.reindex_catalog(embedding_model="model")

    assert result["total_products"] == 0
    assert result["embedding_version"] == "v1"
    assert engine.disposed is True
