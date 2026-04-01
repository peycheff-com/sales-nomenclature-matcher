"""Integration tests for the full matching pipeline.

Requires PostgreSQL with sample catalog imported.
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from matcher.config import settings

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


def _mock_embed(*args, **kwargs):
    raise Exception("No OpenAI key")


class TestOrchestrator:
    @pytest.mark.asyncio
    async def test_match_pump_grundfos(self, db_session):
        from matcher.pipeline.orchestrator import match_single

        with patch("matcher.indexing.search.embed_single", side_effect=_mock_embed):
            result = await match_single(
                raw_text="насос grundfoss 25-40",
                session=db_session,
            )

        assert result.normalized_text
        assert result.status in ("auto_match", "review_needed", "no_match")
        assert result.confidence >= 0.0
        assert result.best_candidate is not None
        assert "grundfos" in result.best_candidate.get("name", "").lower() or result.best_candidate.get("product_id")
        assert len(result.reasons) > 0
        assert len(result.alternatives) > 0

    @pytest.mark.asyncio
    async def test_match_cable_vvg(self, db_session):
        from matcher.pipeline.orchestrator import match_single

        with patch("matcher.indexing.search.embed_single", side_effect=_mock_embed):
            result = await match_single(
                raw_text="Кабель ВВГнг 3х2,5",
                session=db_session,
            )

        assert result.status in ("auto_match", "review_needed", "no_match")
        assert result.best_candidate is not None
        assert result.normalized_text  # Should be normalized

    @pytest.mark.asyncio
    async def test_match_foam_750ml(self, db_session):
        from matcher.pipeline.orchestrator import match_single

        with patch("matcher.indexing.search.embed_single", side_effect=_mock_embed):
            result = await match_single(
                raw_text="пена монтажная зимняя 750 мл",
                session=db_session,
            )

        assert result.status in ("auto_match", "review_needed", "no_match")
        assert result.extracted_attributes.get("unit") == "ml" or "ml" in result.normalized_text

    @pytest.mark.asyncio
    async def test_match_returns_alternatives(self, db_session):
        from matcher.pipeline.orchestrator import match_single

        with patch("matcher.indexing.search.embed_single", side_effect=_mock_embed):
            result = await match_single(
                raw_text="насос 25-40",
                session=db_session,
            )

        # Should have at least the best candidate in alternatives
        if result.best_candidate:
            assert len(result.alternatives) >= 1

    @pytest.mark.asyncio
    async def test_match_nonsense_returns_no_match(self, db_session):
        from matcher.pipeline.orchestrator import match_single

        with patch("matcher.indexing.search.embed_single", side_effect=_mock_embed):
            result = await match_single(
                raw_text="абракадабра xyz123 несуществующий товар",
                session=db_session,
            )

        assert result.status == "no_match" or result.confidence < 0.5

    @pytest.mark.asyncio
    async def test_match_with_supplier_id(self, db_session):
        from matcher.pipeline.orchestrator import match_single

        with patch("matcher.indexing.search.embed_single", side_effect=_mock_embed):
            result = await match_single(
                raw_text="насос grundfos",
                session=db_session,
                supplier_id="supplier_001",  # No overrides exist, should proceed normally
            )

        assert result.status in ("auto_match", "review_needed", "no_match")

    @pytest.mark.asyncio
    async def test_extracted_attributes_populated(self, db_session):
        from matcher.pipeline.orchestrator import match_single

        with patch("matcher.indexing.search.embed_single", side_effect=_mock_embed):
            result = await match_single(
                raw_text="штукатурка Кнауф 30 кг",
                session=db_session,
            )

        attrs = result.extracted_attributes
        assert attrs.get("brand") == "knauf"
        assert 30.0 in attrs.get("numbers", [])
