"""Tests for auth API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from matcher.auth.security import hash_password
from matcher.db.models import User


class TestAuthEndpoints:
    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, async_client):
        with patch("matcher.api.v1.auth.UserRepo") as MockRepo:
            MockRepo.return_value.get_by_username = AsyncMock(return_value=None)
            resp = await async_client.post(
                "/api/v1/auth/login",
                data={"username": "bad", "password": "bad"},
            )
            assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_me_requires_auth(self, async_client):
        resp = await async_client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_me_with_valid_token(self, async_client, auth_headers):
        mock_user = User(
            user_id="u1",
            username="test_admin",
            hashed_password="x",
            role="admin",
            is_active=True,
            must_change_password=False,
        )
        with patch("matcher.auth.deps.UserRepo") as MockRepo:
            MockRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
            resp = await async_client.get("/api/v1/auth/me", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["username"] == "test_admin"
            assert data["role"] == "admin"

    @pytest.mark.asyncio
    async def test_me_with_invalid_token(self, async_client):
        headers = {"Authorization": "Bearer invalid-token"}
        resp = await async_client.get("/api/v1/auth/me", headers=headers)
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_success(self, async_client):
        hashed = hash_password("correct_password")
        mock_user = User(
            user_id="u1",
            username="test_admin",
            hashed_password=hashed,
            role="admin",
            is_active=True,
            must_change_password=False,
        )
        with patch("matcher.api.v1.auth.UserRepo") as MockRepo:
            MockRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
            resp = await async_client.post(
                "/api/v1/auth/login",
                data={"username": "test_admin", "password": "correct_password"},
            )
            assert resp.status_code == 200
            data = resp.json()
            # Login returns either {"access_token": ...} or {"logged_in": true} (cookie-based)
            assert "access_token" in data or data.get("logged_in") is True

    @pytest.mark.asyncio
    async def test_login_inactive_user(self, async_client):
        hashed = hash_password("correct_password")
        mock_user = User(
            user_id="u1",
            username="disabled_user",
            hashed_password=hashed,
            role="admin",
            is_active=False,
            must_change_password=False,
        )
        with patch("matcher.api.v1.auth.UserRepo") as MockRepo:
            MockRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
            resp = await async_client.post(
                "/api/v1/auth/login",
                data={"username": "disabled_user", "password": "correct_password"},
            )
            assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_me_with_inactive_user_token(self, async_client, auth_headers):
        mock_user = User(
            user_id="u1",
            username="test_admin",
            hashed_password="x",
            role="admin",
            is_active=False,
            must_change_password=False,
        )
        with patch("matcher.auth.deps.UserRepo") as MockRepo:
            MockRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
            resp = await async_client.get("/api/v1/auth/me", headers=auth_headers)
            assert resp.status_code == 401
