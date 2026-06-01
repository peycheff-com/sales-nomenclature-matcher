from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from matcher.db.models import User


class TestAuditEndpoints:
    @pytest.mark.asyncio
    async def test_audit_requires_auth(self, async_client):
        resp = await async_client.get("/api/v1/audit")

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_audit_requires_admin_role(self, async_client, viewer_headers):
        mock_user = User(
            user_id="u1",
            username="test_viewer",
            hashed_password="x",
            role="viewer",
            is_active=True,
            must_change_password=False,
        )
        with patch("matcher.auth.deps.UserRepo") as MockUserRepo:
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)

            resp = await async_client.get("/api/v1/audit", headers=viewer_headers)

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Insufficient permissions"

    @pytest.mark.asyncio
    async def test_audit_lists_logs_with_filters(self, async_client, auth_headers):
        mock_user = User(
            user_id="u1",
            username="test_admin",
            hashed_password="x",
            role="admin",
            is_active=True,
            must_change_password=False,
        )
        created_at = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)
        log_entry = SimpleNamespace(
            log_id="audit_1",
            action="approve",
            entity_type="match",
            entity_id="item_1",
            user_id="u1",
            username="test_admin",
            details={"decision": "accepted"},
            ip_address="127.0.0.1",
            created_at=created_at,
        )

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.audit.AuditRepo") as MockAuditRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
            MockAuditRepo.return_value.list_logs = AsyncMock(return_value=([log_entry], 1))

            resp = await async_client.get(
                "/api/v1/audit",
                params={
                    "entity_type": "match",
                    "entity_id": "item_1",
                    "user_id": "u1",
                    "action": "approve",
                    "limit": 25,
                    "offset": 5,
                },
                headers=auth_headers,
            )

        assert resp.status_code == 200
        assert resp.json() == {
            "items": [
                {
                    "log_id": "audit_1",
                    "action": "approve",
                    "entity_type": "match",
                    "entity_id": "item_1",
                    "user_id": "u1",
                    "username": "test_admin",
                    "details": {"decision": "accepted"},
                    "ip_address": "127.0.0.1",
                    "created_at": "2026-05-31T12:00:00+00:00",
                }
            ],
            "total": 1,
        }
        MockAuditRepo.return_value.list_logs.assert_awaited_once_with(
            entity_type="match",
            entity_id="item_1",
            user_id="u1",
            action="approve",
            limit=25,
            offset=5,
        )

    @pytest.mark.asyncio
    async def test_audit_serializes_missing_created_at(self, async_client, auth_headers):
        mock_user = User(
            user_id="u1",
            username="test_admin",
            hashed_password="x",
            role="admin",
            is_active=True,
            must_change_password=False,
        )
        log_entry = SimpleNamespace(
            log_id="audit_2",
            action="login",
            entity_type="auth",
            entity_id=None,
            user_id=None,
            username=None,
            details={},
            ip_address=None,
            created_at=None,
        )

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.audit.AuditRepo") as MockAuditRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
            MockAuditRepo.return_value.list_logs = AsyncMock(return_value=([log_entry], 1))

            resp = await async_client.get("/api/v1/audit", headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json()["items"][0]["created_at"] is None
