"""Tests for review API endpoints."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from matcher.db.models import User


class TestReviewEndpoints:
    @pytest.mark.asyncio
    async def test_review_requires_auth(self, async_client):
        resp = await async_client.post(
            "/api/v1/review/items/item_123",
            json={"final_decision": "accepted"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_review_item_not_found(self, async_client, auth_headers):
        mock_user = User(
            user_id="u1",
            username="test_admin",
            hashed_password="x",
            role="admin",
            is_active=True,
        )
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.review.MatchRepo") as MockRepo,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
            MockRepo.return_value.get_item_with_request = AsyncMock(return_value=(None, None))
            resp = await async_client.post(
                "/api/v1/review/items/nonexistent",
                json={"final_decision": "accepted"},
                headers=auth_headers,
            )
            assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_review_invalid_decision(self, async_client, auth_headers):
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
                "/api/v1/review/items/item_123",
                json={"final_decision": "invalid_value"},
                headers=auth_headers,
            )
            # Pydantic validation should reject invalid literal
            assert resp.status_code == 422
