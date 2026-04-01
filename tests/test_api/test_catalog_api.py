"""Tests for catalog API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from matcher.db.models import User


class TestCatalogEndpoints:
    @pytest.mark.asyncio
    async def test_import_requires_auth(self, async_client):
        resp = await async_client.post(
            "/api/v1/catalog/import",
            json={"source_type": "csv"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_import_requires_operator_role(self, async_client, viewer_headers):
        mock_user = User(
            user_id="u1",
            username="test_viewer",
            hashed_password="x",
            role="viewer",
            is_active=True,
        )
        with patch("matcher.auth.deps.UserRepo") as MockUserRepo:
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
            resp = await async_client.post(
                "/api/v1/catalog/import",
                json={"source_type": "csv", "file_url": "http://example.com/file.csv"},
                headers=viewer_headers,
            )
            assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_import_accepted(self, async_client, auth_headers):
        mock_user = User(
            user_id="u1",
            username="test_admin",
            hashed_password="x",
            role="admin",
            is_active=True,
        )
        with patch("matcher.auth.deps.UserRepo") as MockUserRepo:
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
            resp = await async_client.post(
                "/api/v1/catalog/import",
                json={"source_type": "csv", "file_url": "http://example.com/file.csv"},
                headers=auth_headers,
            )
            assert resp.status_code == 202
            data = resp.json()
            assert data["status"] == "queued"
            assert "job_id" in data

    @pytest.mark.asyncio
    async def test_reindex_requires_admin(self, async_client, operator_headers):
        mock_user = User(
            user_id="u1",
            username="test_operator",
            hashed_password="x",
            role="operator",
            is_active=True,
        )
        with patch("matcher.auth.deps.UserRepo") as MockUserRepo:
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
            resp = await async_client.post(
                "/api/v1/catalog/reindex",
                json={},
                headers=operator_headers,
            )
            assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_reindex_returns_202(self, async_client, auth_headers):
        mock_user = User(
            user_id="u1",
            username="test_admin",
            hashed_password="x",
            role="admin",
            is_active=True,
        )
        with patch("matcher.auth.deps.UserRepo") as MockUserRepo:
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
            resp = await async_client.post(
                "/api/v1/catalog/reindex",
                json={},
                headers=auth_headers,
            )
            assert resp.status_code == 202
