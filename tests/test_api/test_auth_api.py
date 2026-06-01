"""Tests for auth API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.responses import JSONResponse

from matcher.api.v1 import auth
from matcher.auth.security import hash_password
from matcher.db.models import User
from matcher.main import app


class TestAuthEndpoints:
    def test_auth_cookie_helpers_set_and_clear_expected_cookies(self, monkeypatch):
        monkeypatch.setattr(auth.settings, "cookie_domain", "example.com")
        monkeypatch.setattr(auth.settings, "cookie_secure", True)
        monkeypatch.setattr(auth.settings, "cookie_samesite", "lax")
        monkeypatch.setattr(auth.settings, "jwt_expire_minutes", 15)
        monkeypatch.setattr(auth.secrets, "token_hex", lambda size: "csrf-token")

        response = JSONResponse(content={})
        auth._set_auth_cookies(response, "jwt-token")
        set_cookie_headers = response.headers.getlist("set-cookie")

        assert any("access_token=jwt-token" in value for value in set_cookie_headers)
        assert any("Domain=example.com" in value for value in set_cookie_headers)
        assert any("csrf_token=csrf-token" in value for value in set_cookie_headers)
        assert any("Max-Age=900" in value for value in set_cookie_headers)

        clear_response = JSONResponse(content={})
        auth._clear_auth_cookies(clear_response)
        clear_cookie_headers = clear_response.headers.getlist("set-cookie")

        assert any("access_token=\"\"" in value for value in clear_cookie_headers)
        assert any("csrf_token=\"\"" in value for value in clear_cookie_headers)

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
            assert "access_token=" in resp.headers["set-cookie"]

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
    async def test_login_rate_limiter_blocked_and_fail_open_paths(
        self, async_client, monkeypatch
    ):
        monkeypatch.setattr(app.state, "arq_pool", object(), raising=False)
        with patch("matcher.api.v1.auth.login_rate_limiter") as limiter:
            limiter.is_blocked = AsyncMock(return_value=True)

            blocked = await async_client.post(
                "/api/v1/auth/login",
                data={"username": "test_admin", "password": "correct_password"},
            )

        assert blocked.status_code == 429

        hashed = hash_password("correct_password")
        mock_user = User(
            user_id="u1",
            username="test_admin",
            hashed_password=hashed,
            role="admin",
            is_active=True,
            must_change_password=True,
        )
        with (
            patch("matcher.api.v1.auth.UserRepo") as MockRepo,
            patch("matcher.api.v1.auth.login_rate_limiter") as limiter,
        ):
            MockRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
            limiter.is_blocked = AsyncMock(side_effect=RuntimeError("redis down"))
            limiter.reset = AsyncMock(side_effect=RuntimeError("reset failed"))

            allowed = await async_client.post(
                "/api/v1/auth/login",
                data={"username": "test_admin", "password": "correct_password"},
            )

        assert allowed.status_code == 200
        assert allowed.json() == {"logged_in": True, "must_change_password": True}

    @pytest.mark.asyncio
    async def test_login_records_failed_attempt_and_ignores_limiter_record_errors(
        self, async_client, monkeypatch
    ):
        monkeypatch.setattr(app.state, "arq_pool", object(), raising=False)
        with (
            patch("matcher.api.v1.auth.UserRepo") as MockRepo,
            patch("matcher.api.v1.auth.login_rate_limiter") as limiter,
        ):
            MockRepo.return_value.get_by_username = AsyncMock(return_value=None)
            limiter.is_blocked = AsyncMock(return_value=False)
            limiter.record_attempt = AsyncMock(side_effect=RuntimeError("record failed"))

            resp = await async_client.post(
                "/api/v1/auth/login",
                data={"username": "bad", "password": "bad"},
            )

        assert resp.status_code == 401
        limiter.record_attempt.assert_awaited_once()

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

    @pytest.mark.asyncio
    async def test_must_change_password_blocks_other_endpoints(self, async_client, auth_headers):
        """A user with must_change_password=True should get 403 on normal endpoints."""
        mock_user = User(
            user_id="u1",
            username="test_admin",
            hashed_password="x",
            role="admin",
            is_active=True,
            must_change_password=True,
        )
        with patch("matcher.auth.deps.UserRepo") as MockRepo:
            MockRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
            resp = await async_client.get(
                "/api/v1/catalog/products",
                headers=auth_headers,
            )
            assert resp.status_code == 403
            assert "Password change required" in resp.json().get("detail", "")

    @pytest.mark.asyncio
    async def test_must_change_password_allows_force_change(self, async_client, auth_headers):
        """A user with must_change_password=True should still access force-change-password."""
        mock_user = User(
            user_id="u1",
            username="test_admin",
            hashed_password="x",
            role="admin",
            is_active=True,
            must_change_password=True,
        )
        with patch("matcher.auth.deps.UserRepo") as MockRepo:
            MockRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
            resp = await async_client.post(
                "/api/v1/auth/force-change-password",
                json={"new_password": "new_secure_password_123"},
                headers=auth_headers,
            )
            # Should NOT be 403 "Password change required"
            # It will either succeed (200) or fail with a different status,
            # but crucially it must not be blocked by the must_change_password guard
            detail = resp.json().get("detail", "")
            assert resp.status_code != 403 or "Password change required" not in detail

    @pytest.mark.asyncio
    async def test_logout_clears_auth_cookies(self, async_client):
        resp = await async_client.post("/api/v1/auth/logout")

        assert resp.status_code == 200
        assert resp.json() == {"logged_out": True}
        assert "access_token" in resp.headers["set-cookie"]
        assert "csrf_token" in resp.headers["set-cookie"]

    @pytest.mark.asyncio
    async def test_update_profile(self, async_client, auth_headers, mock_db_session):
        mock_user = User(
            user_id="u1",
            username="test_admin",
            hashed_password="x",
            full_name="Old",
            role="admin",
            is_active=True,
            must_change_password=False,
        )
        with patch("matcher.auth.deps.UserRepo") as MockRepo:
            MockRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)

            resp = await async_client.put(
                "/api/v1/auth/profile",
                json={"full_name": "New Name"},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        assert resp.json()["full_name"] == "New Name"
        assert mock_user.full_name == "New Name"
        mock_db_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_change_password_rejects_wrong_current_password(
        self, async_client, auth_headers, mock_db_session
    ):
        mock_user = User(
            user_id="u1",
            username="test_admin",
            hashed_password=hash_password("old-password"),
            role="admin",
            is_active=True,
            must_change_password=False,
        )
        with patch("matcher.auth.deps.UserRepo") as MockRepo:
            MockRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)

            resp = await async_client.post(
                "/api/v1/auth/change-password",
                json={"current_password": "wrong", "new_password": "new-password"},
                headers=auth_headers,
            )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Current password is incorrect"
        mock_db_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_change_password_success(self, async_client, auth_headers, mock_db_session):
        mock_user = User(
            user_id="u1",
            username="test_admin",
            hashed_password=hash_password("old-password"),
            role="admin",
            is_active=True,
            must_change_password=False,
        )
        with patch("matcher.auth.deps.UserRepo") as MockRepo:
            MockRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)

            resp = await async_client.post(
                "/api/v1/auth/change-password",
                json={"current_password": "old-password", "new_password": "new-password"},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        mock_db_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_force_change_password_rejects_when_not_required(
        self, async_client, auth_headers
    ):
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

            resp = await async_client.post(
                "/api/v1/auth/force-change-password",
                json={"new_password": "new_secure_password_123"},
                headers=auth_headers,
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Password change is not required"

    @pytest.mark.asyncio
    async def test_force_change_password_success_sets_new_cookie(
        self, async_client, auth_headers, mock_db_session
    ):
        mock_user = User(
            user_id="u1",
            username="test_admin",
            hashed_password="x",
            role="admin",
            is_active=True,
            must_change_password=True,
        )
        with patch("matcher.auth.deps.UserRepo") as MockRepo:
            MockRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)

            resp = await async_client.post(
                "/api/v1/auth/force-change-password",
                json={"new_password": "new_secure_password_123"},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert mock_user.must_change_password is False
        assert "access_token=" in resp.headers["set-cookie"]
        mock_db_session.commit.assert_awaited_once()
