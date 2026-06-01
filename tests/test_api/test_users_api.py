from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from matcher.db.models import User


class TestUsersEndpoints:
    def _user(
        self,
        *,
        user_id: str = "u1",
        username: str = "test_admin",
        role: str = "admin",
        is_active: bool = True,
        must_change_password: bool = False,
        full_name: str | None = "Admin User",
    ) -> User:
        return User(
            user_id=user_id,
            username=username,
            hashed_password="hash",
            full_name=full_name,
            role=role,
            is_active=is_active,
            must_change_password=must_change_password,
            created_at=datetime(2026, 5, 31, 12, 0, tzinfo=UTC),
            updated_at=datetime(2026, 5, 31, 12, 30, tzinfo=UTC),
        )

    @pytest.mark.asyncio
    async def test_users_require_admin(self, async_client, viewer_headers):
        with patch("matcher.auth.deps.UserRepo") as MockUserRepo:
            MockUserRepo.return_value.get_by_username = AsyncMock(
                return_value=self._user(role="viewer", username="test_viewer")
            )

            resp = await async_client.get("/api/v1/users", headers=viewer_headers)

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Insufficient permissions"

    @pytest.mark.asyncio
    async def test_list_and_get_users(self, async_client, auth_headers):
        user = self._user()
        with (
            patch("matcher.auth.deps.UserRepo") as MockAuthRepo,
            patch("matcher.api.v1.users.UserRepo") as MockRepo,
        ):
            MockAuthRepo.return_value.get_by_username = AsyncMock(return_value=user)
            MockRepo.return_value.list_users = AsyncMock(return_value=[user])
            MockRepo.return_value.get_by_id = AsyncMock(return_value=user)

            listed = await async_client.get("/api/v1/users", headers=auth_headers)
            fetched = await async_client.get("/api/v1/users/u1", headers=auth_headers)

        assert listed.status_code == 200
        assert listed.json()["items"][0]["username"] == "test_admin"
        assert fetched.status_code == 200
        assert fetched.json()["user_id"] == "u1"

    @pytest.mark.asyncio
    async def test_get_user_not_found(self, async_client, auth_headers):
        with (
            patch("matcher.auth.deps.UserRepo") as MockAuthRepo,
            patch("matcher.api.v1.users.UserRepo") as MockRepo,
        ):
            MockAuthRepo.return_value.get_by_username = AsyncMock(return_value=self._user())
            MockRepo.return_value.get_by_id = AsyncMock(return_value=None)

            resp = await async_client.get("/api/v1/users/missing", headers=auth_headers)

        assert resp.status_code == 404
        assert resp.json()["detail"] == "User not found"

    @pytest.mark.asyncio
    async def test_create_user_conflict_and_success(
        self, async_client, auth_headers, mock_db_session
    ):
        with (
            patch("matcher.auth.deps.UserRepo") as MockAuthRepo,
            patch("matcher.api.v1.users.UserRepo") as MockRepo,
        ):
            MockAuthRepo.return_value.get_by_username = AsyncMock(return_value=self._user())
            MockRepo.return_value.get_by_username = AsyncMock(
                return_value=self._user(username="bob")
            )

            conflict = await async_client.post(
                "/api/v1/users",
                json={"username": "bob", "password": "secret1", "role": "operator"},
                headers=auth_headers,
            )

        assert conflict.status_code == 409
        assert conflict.json()["detail"] == "Username already exists"

        created_user = self._user(
            user_id="u2",
            username="bob",
            role="operator",
            must_change_password=True,
            full_name="Bob",
        )
        with (
            patch("matcher.auth.deps.UserRepo") as MockAuthRepo,
            patch("matcher.api.v1.users.UserRepo") as MockRepo,
            patch("matcher.api.v1.users.AuditRepo") as MockAuditRepo,
        ):
            MockAuthRepo.return_value.get_by_username = AsyncMock(return_value=self._user())
            repo = MockRepo.return_value
            repo.get_by_username = AsyncMock(return_value=None)
            repo.create_user = AsyncMock(return_value=created_user)
            MockAuditRepo.return_value.log = AsyncMock()

            created = await async_client.post(
                "/api/v1/users",
                json={
                    "username": "bob",
                    "password": "secret1",
                    "role": "operator",
                    "full_name": "Bob",
                },
                headers=auth_headers,
            )

        assert created.status_code == 201
        assert created.json()["username"] == "bob"
        repo.create_user.assert_awaited_once()
        create_kwargs = repo.create_user.await_args.kwargs
        assert create_kwargs["username"] == "bob"
        assert create_kwargs["full_name"] == "Bob"
        assert create_kwargs["role"] == "operator"
        assert create_kwargs["must_change_password"] is True
        assert create_kwargs["hashed_password"] != "secret1"
        MockAuditRepo.return_value.log.assert_awaited_once()
        mock_db_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_user_self_protection_and_no_fields(self, async_client, auth_headers):
        with patch("matcher.auth.deps.UserRepo") as MockAuthRepo:
            MockAuthRepo.return_value.get_by_username = AsyncMock(return_value=self._user())

            deactivate = await async_client.put(
                "/api/v1/users/u1",
                json={"is_active": False},
                headers=auth_headers,
            )
            demote = await async_client.put(
                "/api/v1/users/u1",
                json={"role": "operator"},
                headers=auth_headers,
            )
            empty = await async_client.put(
                "/api/v1/users/u2",
                json={},
                headers=auth_headers,
            )

        assert deactivate.status_code == 400
        assert deactivate.json()["detail"] == "Cannot deactivate your own account"
        assert demote.status_code == 400
        assert demote.json()["detail"] == "Cannot change your own role"
        assert empty.status_code == 400
        assert empty.json()["detail"] == "No fields to update"

    @pytest.mark.asyncio
    async def test_update_user_not_found_and_success(
        self, async_client, auth_headers, mock_db_session
    ):
        with (
            patch("matcher.auth.deps.UserRepo") as MockAuthRepo,
            patch("matcher.api.v1.users.UserRepo") as MockRepo,
        ):
            MockAuthRepo.return_value.get_by_username = AsyncMock(return_value=self._user())
            MockRepo.return_value.update_user = AsyncMock(return_value=None)

            missing = await async_client.put(
                "/api/v1/users/missing",
                json={"full_name": "Missing"},
                headers=auth_headers,
            )

        assert missing.status_code == 404

        updated_user = self._user(user_id="u2", username="operator", role="operator")
        updated_user.full_name = "Updated"
        with (
            patch("matcher.auth.deps.UserRepo") as MockAuthRepo,
            patch("matcher.api.v1.users.UserRepo") as MockRepo,
        ):
            MockAuthRepo.return_value.get_by_username = AsyncMock(return_value=self._user())
            MockRepo.return_value.update_user = AsyncMock(return_value=updated_user)

            updated = await async_client.put(
                "/api/v1/users/u2",
                json={"full_name": "Updated", "role": "operator"},
                headers=auth_headers,
            )

        assert updated.status_code == 200
        assert updated.json()["full_name"] == "Updated"
        MockRepo.return_value.update_user.assert_awaited_once_with(
            "u2",
            full_name="Updated",
            role="operator",
        )
        mock_db_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reset_password_not_found_and_success(
        self, async_client, auth_headers, mock_db_session
    ):
        with (
            patch("matcher.auth.deps.UserRepo") as MockAuthRepo,
            patch("matcher.api.v1.users.UserRepo") as MockRepo,
        ):
            MockAuthRepo.return_value.get_by_username = AsyncMock(return_value=self._user())
            MockRepo.return_value.get_by_id = AsyncMock(return_value=None)

            missing = await async_client.post(
                "/api/v1/users/missing/reset-password",
                json={"new_password": "secret2"},
                headers=auth_headers,
            )

        assert missing.status_code == 404

        user = self._user(user_id="u2", username="operator", role="operator")
        old_hash = user.hashed_password
        with (
            patch("matcher.auth.deps.UserRepo") as MockAuthRepo,
            patch("matcher.api.v1.users.UserRepo") as MockRepo,
        ):
            MockAuthRepo.return_value.get_by_username = AsyncMock(return_value=self._user())
            MockRepo.return_value.get_by_id = AsyncMock(return_value=user)

            reset = await async_client.post(
                "/api/v1/users/u2/reset-password",
                json={"new_password": "secret2"},
                headers=auth_headers,
            )

        assert reset.status_code == 200
        assert reset.json() == {"ok": True}
        assert user.hashed_password != old_hash
        assert user.must_change_password is True
        mock_db_session.commit.assert_awaited_once()
