"""Tests for settings persistence via SettingsRepo."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from matcher.db.models import User
from matcher.db.repos.settings import SettingsRepo


class TestSettingsRepo:
    """Unit tests for SettingsRepo with mock session."""

    @pytest.mark.asyncio
    async def test_upsert_executes_query(self, mock_db_session):
        repo = SettingsRepo(mock_db_session)
        await repo.upsert("auto_match_threshold", "0.85")

        mock_db_session.execute.assert_called_once()
        call_args = mock_db_session.execute.call_args
        params = call_args[0][1]
        assert params["key"] == "auto_match_threshold"
        assert params["value"] == "0.85"
        mock_db_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_returns_value(self, mock_db_session):
        mock_row = ("0.85",)
        mock_result = MagicMock()
        mock_result.first.return_value = mock_row
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        repo = SettingsRepo(mock_db_session)
        value = await repo.get("auto_match_threshold")

        assert value == "0.85"

    @pytest.mark.asyncio
    async def test_get_returns_default_when_missing(self, mock_db_session):
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        repo = SettingsRepo(mock_db_session)
        value = await repo.get("missing_key", default="fallback")

        assert value == "fallback"

    @pytest.mark.asyncio
    async def test_get_all_returns_dict(self, mock_db_session):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("auto_match_threshold", "0.85"),
            ("review_threshold", "0.5"),
        ]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        repo = SettingsRepo(mock_db_session)
        result = await repo.get_all()

        assert result == {
            "auto_match_threshold": "0.85",
            "review_threshold": "0.5",
        }


class TestSettingsPersistenceEndpoints:
    """Test that PUT /settings persists and GET /settings loads from DB."""

    @pytest.mark.asyncio
    async def test_update_settings_persists_to_db(
        self, async_client, auth_headers, mock_db_session
    ):
        mock_user = User(
            user_id="u1",
            username="test_admin",
            hashed_password="x",
            role="admin",
            is_active=True,
        )

        # Mock SettingsRepo.upsert to track calls
        upsert_calls = []

        async def mock_upsert(self, key, value, commit=True):
            upsert_calls.append((key, value, commit))

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch.object(SettingsRepo, "upsert", mock_upsert),
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)

            # Also mock get_all for the _load_persisted_settings call inside get_settings
            with patch.object(SettingsRepo, "get_all", new_callable=AsyncMock, return_value={}):
                resp = await async_client.put(
                    "/api/v1/settings",
                    json={"auto_match_threshold": 0.9},
                    headers=auth_headers,
                )

        assert resp.status_code == 200
        persisted_keys = [k for k, _v, _commit in upsert_calls]
        assert "auto_match_threshold" in persisted_keys
        assert "review_threshold" in persisted_keys
        assert "onec" in persisted_keys

    @pytest.mark.asyncio
    async def test_get_settings_loads_from_db(self, async_client, auth_headers, mock_db_session):
        """On first call, persisted settings should be loaded from DB."""
        import matcher.api.v1.settings as settings_module

        # Reset the _db_loaded flag so the load logic runs
        settings_module._db_loaded = False

        mock_user = User(
            user_id="u1",
            username="test_admin",
            hashed_password="x",
            role="admin",
            is_active=True,
        )

        stored = {
            "auto_match_threshold": "0.92",
            "review_threshold": "0.55",
            "retrieval_top_n": "30",
            "rerank_top_n": "8",
            "onec": json.dumps(
                {
                    "base_url": "http://1c.local",
                    "username": "admin",
                    "password": "secret",
                    "catalog_endpoint": "/hs/catalog/v1/nomenclature",
                    "enabled": True,
                }
            ),
        }

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch.object(SettingsRepo, "get_all", new_callable=AsyncMock, return_value=stored),
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
            resp = await async_client.get("/api/v1/settings", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["auto_match_threshold"] == 0.92
        assert data["review_threshold"] == 0.55
        assert data["retrieval_top_n"] == 30
        assert data["rerank_top_n"] == 8
        assert data["onec"]["base_url"] == "http://1c.local"
        assert data["onec"]["enabled"] is True
        # Password must be masked
        assert data["onec"]["password"] == "********"

        # Clean up: reset flag for other tests
        settings_module._db_loaded = False

    @pytest.mark.asyncio
    async def test_update_settings_rejects_non_1024_embedding_dimensions(
        self, async_client, auth_headers
    ):
        mock_user = User(
            user_id="u1",
            username="test_admin",
            hashed_password="x",
            role="admin",
            is_active=True,
        )

        with patch("matcher.auth.deps.UserRepo") as MockUserRepo:
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
            resp = await async_client.put(
                "/api/v1/settings",
                json={"embedding_dimensions": 3072},
                headers=auth_headers,
            )

        assert resp.status_code == 422
        assert "1024" in resp.text

    @pytest.mark.asyncio
    async def test_env_provider_secret_wins_over_db_value(self, mock_db_session):
        import matcher.api.v1.settings as settings_module
        from matcher.config import settings

        settings_module._db_loaded = False
        original_key = settings.google_api_key
        original_registry = json.loads(json.dumps(settings.providers_registry))

        try:
            settings.google_api_key = "env-google-key"
            settings.apply_env_provider_secrets()

            stored = {
                "providers_registry": json.dumps(
                    {"google": {"id": "google", "api_key": "db-google-key"}}
                )
            }

            with patch.object(SettingsRepo, "get_all", new_callable=AsyncMock, return_value=stored):
                await settings_module.load_persisted_settings(mock_db_session, force=True)

            assert settings.providers_registry["google"]["api_key"] == "env-google-key"
        finally:
            settings.google_api_key = original_key
            settings.providers_registry = original_registry
            settings.apply_env_provider_secrets()
            settings_module._db_loaded = False
