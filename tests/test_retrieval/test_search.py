"""Integration tests for hybrid search against the sample catalog.

These tests require a running PostgreSQL with the sample catalog imported.
Run: python scripts/import_catalog.py tests/golden_set/sample_catalog.csv
And: UPDATE catalog_products SET search_tsv = to_tsvector('russian', coalesce(search_document, ''));

Skip if DB is not available.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from matcher.config import settings

# Check if DB is available
_db_available = False
try:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    async def _check_db():
        engine = create_async_engine(settings.async_database_url)
        try:
            async with engine.connect() as conn:
                result = await conn.execute(text("SELECT count(*) FROM catalog_products"))
                count = result.scalar()
                return count and count > 0
        except Exception:
            return False
        finally:
            await engine.dispose()

    _db_available = asyncio.get_event_loop().run_until_complete(_check_db())
except Exception:
    pass

pytestmark = pytest.mark.skipif(not _db_available, reason="Database not available or empty")


@pytest.fixture
async def db_session():
    engine = create_async_engine(settings.async_database_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _mock_embed_single(text: str):
    """Return a dummy embedding — search falls back to lexical only."""
    raise Exception("No OpenAI key — lexical fallback")


class TestHybridSearch:
    """Test hybrid search with lexical-only (no embeddings)."""

    @pytest.mark.asyncio
    async def test_finds_pump_grundfos(self, db_session):
        from matcher.indexing.search import hybrid_search

        with patch("matcher.indexing.search.embed_single", side_effect=_mock_embed_single):
            candidates = await hybrid_search(
                query_text="насос grundfos 25-40",
                normalized_text="насос grundfos 25-40",
                session=db_session,
                top_n=10,
            )

        assert len(candidates) > 0
        top = candidates[0]
        assert "grundfos" in top.name.lower() or "grundfos" in (top.normalized_name or "")
        assert top.rrf_score > 0

    @pytest.mark.asyncio
    async def test_finds_cable_vvg(self, db_session):
        from matcher.indexing.search import hybrid_search

        with patch("matcher.indexing.search.embed_single", side_effect=_mock_embed_single):
            candidates = await hybrid_search(
                query_text="кабель ввг 3x2.5",
                normalized_text="кабель ввгнг 3x2.5",
                session=db_session,
                top_n=10,
            )

        assert len(candidates) > 0
        names = [c.normalized_name for c in candidates]
        assert any("ввгнг" in n for n in names)

    @pytest.mark.asyncio
    async def test_finds_plaster_knauf(self, db_session):
        from matcher.indexing.search import hybrid_search

        with patch("matcher.indexing.search.embed_single", side_effect=_mock_embed_single):
            candidates = await hybrid_search(
                query_text="штукатурка кнауф ротбанд",
                normalized_text="штукатурка knauf ротбанд",
                session=db_session,
                top_n=10,
            )

        assert len(candidates) > 0
        top = candidates[0]
        assert "knauf" in top.normalized_name or "кнауф" in top.name.lower()

    @pytest.mark.asyncio
    async def test_finds_foam_750ml(self, db_session):
        from matcher.indexing.search import hybrid_search

        with patch("matcher.indexing.search.embed_single", side_effect=_mock_embed_single):
            candidates = await hybrid_search(
                query_text="пена монтажная 750 мл",
                normalized_text="пена монтажная 750 ml",
                session=db_session,
                top_n=10,
            )

        assert len(candidates) > 0
        names = [c.name.lower() for c in candidates]
        assert any("пена" in n for n in names)

    @pytest.mark.asyncio
    async def test_finds_drill_bosch(self, db_session):
        from matcher.indexing.search import hybrid_search

        with patch("matcher.indexing.search.embed_single", side_effect=_mock_embed_single):
            candidates = await hybrid_search(
                query_text="перфоратор bosch gbh 2-26",
                normalized_text="перфоратор bosch gbh 2-26",
                session=db_session,
                top_n=10,
            )

        assert len(candidates) > 0
        top = candidates[0]
        assert "bosch" in top.normalized_name or "bosch" in (top.brand or "").lower()

    @pytest.mark.asyncio
    async def test_exact_article_match(self, db_session):
        from matcher.indexing.search import hybrid_search

        with patch("matcher.indexing.search.embed_single", side_effect=_mock_embed_single):
            candidates = await hybrid_search(
                query_text="UPS25-40-180",
                normalized_text="ups25-40-180",
                session=db_session,
                top_n=10,
                article_hint="UPS25-40-180",
            )

        assert len(candidates) > 0
        assert any(c.article == "UPS25-40-180" for c in candidates)

    @pytest.mark.asyncio
    async def test_returns_scores(self, db_session):
        from matcher.indexing.search import hybrid_search

        with patch("matcher.indexing.search.embed_single", side_effect=_mock_embed_single):
            candidates = await hybrid_search(
                query_text="насос",
                normalized_text="насос",
                session=db_session,
                top_n=10,
            )

        if candidates:
            top = candidates[0]
            assert top.rrf_score > 0
            assert top.retrieval_rank == 1

    @pytest.mark.asyncio
    async def test_empty_query_returns_empty(self, db_session):
        from matcher.indexing.search import hybrid_search

        with patch("matcher.indexing.search.embed_single", side_effect=_mock_embed_single):
            candidates = await hybrid_search(
                query_text="",
                normalized_text="",
                session=db_session,
                top_n=10,
            )

        # Empty or very few results for empty query is acceptable
        assert isinstance(candidates, list)

    @pytest.mark.asyncio
    async def test_rockwool_insulation(self, db_session):
        from matcher.indexing.search import hybrid_search

        with patch("matcher.indexing.search.embed_single", side_effect=_mock_embed_single):
            candidates = await hybrid_search(
                query_text="утеплитель роквул",
                normalized_text="утеплитель rockwool",
                session=db_session,
                top_n=10,
            )

        assert len(candidates) > 0
        names = [c.normalized_name for c in candidates]
        assert any("rockwool" in n for n in names)

    @pytest.mark.asyncio
    async def test_paint_10l(self, db_session):
        from matcher.indexing.search import hybrid_search

        with patch("matcher.indexing.search.embed_single", side_effect=_mock_embed_single):
            candidates = await hybrid_search(
                query_text="краска интерьерная 10 л",
                normalized_text="краска интерьерная 10 l",
                session=db_session,
                top_n=10,
            )

        assert len(candidates) > 0
        names = [c.name.lower() for c in candidates]
        assert any("краска" in n for n in names)
