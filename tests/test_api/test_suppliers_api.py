"""Tests for suppliers API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from matcher.db.models import User


class TestSuppliersEndpoints:
    @pytest.mark.asyncio
    async def test_list_suppliers_requires_auth(self, async_client):
        resp = await async_client.get("/api/v1/suppliers")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_suppliers(self, async_client, auth_headers):
        mock_user = User(
            user_id="u1",
            username="test_admin",
            hashed_password="x",
            role="admin",
            is_active=True,
        )
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.suppliers.SupplierRepo") as MockRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
            MockRepo.return_value.list_suppliers = AsyncMock(return_value=[])
            resp = await async_client.get("/api/v1/suppliers", headers=auth_headers)
            assert resp.status_code == 200
            assert "items" in resp.json()

    @pytest.mark.asyncio
    async def test_create_mapping_requires_operator(self, async_client, viewer_headers):
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
                "/api/v1/suppliers/s1/mappings",
                json={"product_id": "p1", "mapping_type": "approved"},
                headers=viewer_headers,
            )
            assert resp.status_code == 403
