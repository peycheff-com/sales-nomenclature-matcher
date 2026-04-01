"""API integration tests for the match endpoint.

Requires PostgreSQL with sample catalog.
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from matcher.config import settings

_db_available = False
try:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    async def _check_db():
        engine = create_async_engine(settings.async_database_url)
        try:
            async with engine.connect() as conn:
                result = await conn.execute(text("SELECT count(*) FROM catalog_products"))
                return (result.scalar() or 0) > 0
        except Exception:
            return False
        finally:
            await engine.dispose()

    _db_available = asyncio.get_event_loop().run_until_complete(_check_db())
except Exception:
    pass

pytestmark = pytest.mark.skipif(not _db_available, reason="Database not available")


def _mock_embed(*args, **kwargs):
    raise Exception("No OpenAI key")


@pytest.fixture(scope="module")
def client():
    from starlette.testclient import TestClient
    from matcher.main import app
    with TestClient(app) as c:
        yield c


class TestHealthEndpoint:
    def test_health(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestMatchEndpoint:
    def test_match_single_item(self, client):
        with patch("matcher.indexing.search.embed_single", side_effect=_mock_embed):
            resp = client.post("/api/v1/match", json={
                "items": [
                    {"line_id": "1", "raw_text": "насос grundfoss 25-40"}
                ]
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "done"
        assert len(data["results"]) == 1

        result = data["results"][0]
        assert result["raw_text"] == "насос grundfoss 25-40"
        assert result["normalized_text"]
        assert result["status"] in ("auto_match", "review_needed", "no_match")
        assert result["confidence"] >= 0.0

    def test_match_multiple_items(self, client):
        with patch("matcher.indexing.search.embed_single", side_effect=_mock_embed):
            resp = client.post("/api/v1/match", json={
                "items": [
                    {"line_id": "1", "raw_text": "кабель ввг 3х2,5"},
                    {"line_id": "2", "raw_text": "насос grundfoss 25-40"},
                    {"line_id": "3", "raw_text": "пена монтажная зимняя 750 мл"},
                ]
            })

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 3

        for result in data["results"]:
            assert result["status"] in ("auto_match", "review_needed", "no_match")
            assert result["normalized_text"]

    def test_match_with_supplier(self, client):
        with patch("matcher.indexing.search.embed_single", side_effect=_mock_embed):
            resp = client.post("/api/v1/match", json={
                "supplier_id": "supplier_001",
                "items": [
                    {"raw_text": "штукатурка кнауф 30 кг"}
                ]
            })

        assert resp.status_code == 200

    def test_match_returns_reasons(self, client):
        with patch("matcher.indexing.search.embed_single", side_effect=_mock_embed):
            resp = client.post("/api/v1/match", json={
                "items": [
                    {"raw_text": "насос grundfoss 25-40"}
                ]
            })

        data = resp.json()
        result = data["results"][0]
        assert "reasons" in result
        if result["best_candidate"]:
            assert len(result["reasons"]) > 0

    def test_match_returns_alternatives(self, client):
        with patch("matcher.indexing.search.embed_single", side_effect=_mock_embed):
            resp = client.post("/api/v1/match", json={
                "items": [
                    {"raw_text": "насос grundfoss 25-40"}
                ]
            })

        data = resp.json()
        result = data["results"][0]
        assert "alternatives" in result
        if result["alternatives"]:
            alt = result["alternatives"][0]
            assert "product_id" in alt
            assert "final_score" in alt
