"""Tests for settings persistence via SettingsRepo."""

from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import ValidationError

import matcher.api.v1.settings as settings_module
from matcher.db.models import User
from matcher.db.repos.settings import SettingsRepo
from matcher.security.url_validator import SSRFError


def _admin_user() -> User:
    return User(
        user_id="u1",
        username="test_admin",
        hashed_password="x",
        role="admin",
        is_active=True,
    )


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

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch.object(SettingsRepo, "get_all", new_callable=AsyncMock, return_value={}),
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=mock_user)
            resp = await async_client.put(
                "/api/v1/settings",
                json={"auto_match_threshold": 0.9},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        persisted_keys = [call.args[1]["key"] for call in mock_db_session.execute.await_args_list]
        assert "auto_match_threshold" in persisted_keys
        assert "review_threshold" in persisted_keys
        assert "onec" in persisted_keys
        assert mock_db_session.commit.await_count >= 1

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


class _FakeModelsClient:
    response: object | None = None
    error: Exception | None = None
    calls: list[dict] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url: str, headers: dict | None = None, params: dict | None = None):
        self.calls.append({"url": url, "headers": headers or {}, "params": params or {}})
        if self.error:
            raise self.error
        return self.response


def _models_response(payload: dict):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = payload
    return response


class TestSettingsApiBranches:
    @pytest.fixture(autouse=True)
    def restore_runtime_settings(self):
        original_values = {
            key: deepcopy(getattr(settings_module.settings, key))
            for key in (
                "llm_provider",
                "embedding_provider",
                "rerank_provider",
                "providers_registry",
                "llm_model",
                "llm_rerank_model",
                "embedding_model",
                "embedding_dimensions",
                "auto_match_threshold",
                "review_threshold",
                "retrieval_top_n",
                "rerank_top_n",
                "agentic_resolution_enabled",
                "small_catalog_threshold",
                "llm_matcher_enabled",
                "llm_matcher_model",
                "llm_matcher_batch_size",
            )
        }
        original_onec = settings_module._onec_settings.model_copy(deep=True)
        original_loaded = settings_module._db_loaded

        yield

        for key, value in original_values.items():
            setattr(settings_module.settings, key, value)
        settings_module._onec_settings = original_onec
        settings_module._db_loaded = original_loaded
        settings_module.settings.apply_env_provider_secrets()

    @pytest.mark.parametrize(
        ("payload", "message"),
        [
            ({"auto_match_threshold": 1.1}, "auto_match_threshold"),
            ({"review_threshold": -0.1}, "review_threshold"),
            ({"retrieval_top_n": 0}, "retrieval_top_n"),
            ({"rerank_top_n": 101}, "rerank_top_n"),
            ({"embedding_dimensions": 768}, "embedding_dimensions"),
        ],
    )
    def test_settings_update_input_validates_bounds(self, payload, message):
        with pytest.raises(ValidationError, match=message):
            settings_module.SettingsUpdateInput(**payload)

    @pytest.mark.asyncio
    async def test_load_persisted_settings_applies_all_supported_keys(self, mock_db_session):
        settings_module._db_loaded = False
        stored = {
            "auto_match_threshold": "0.91",
            "review_threshold": "0.61",
            "retrieval_top_n": "77",
            "rerank_top_n": "11",
            "agentic_resolution_enabled": "false",
            "embedding_dimensions": "999",
            "small_catalog_threshold": "321",
            "llm_matcher_enabled": "true",
            "llm_matcher_model": "local-reranker",
            "llm_matcher_batch_size": "9",
            "llm_provider": "openai",
            "embedding_provider": "local",
            "rerank_provider": "local",
            "llm_model": "gpt-4o-mini",
            "llm_rerank_model": "gpt-4o-mini",
            "embedding_model": "local-embed",
            "providers_registry": json.dumps(
                {
                    "openai": {"base_url": "https://api.openai.test/v1", "api_key": "stored"},
                    "custom": {"id": "custom", "name": "Custom", "base_url": "https://custom"},
                }
            ),
            "onec": json.dumps(
                {
                    "base_url": "http://onec.example",
                    "username": "onec",
                    "password": "secret",
                    "catalog_endpoint": "/odata",
                    "enabled": True,
                }
            ),
        }

        with patch.object(SettingsRepo, "get_all", new_callable=AsyncMock, return_value=stored):
            await settings_module.load_persisted_settings(mock_db_session, force=True)

        assert settings_module.settings.auto_match_threshold == 0.91
        assert settings_module.settings.review_threshold == 0.61
        assert settings_module.settings.retrieval_top_n == 77
        assert settings_module.settings.rerank_top_n == 11
        assert settings_module.settings.agentic_resolution_enabled is False
        assert settings_module.settings.embedding_dimensions == 1024
        assert settings_module.settings.small_catalog_threshold == 321
        assert settings_module.settings.llm_matcher_enabled is True
        assert settings_module.settings.llm_matcher_model == "local-reranker"
        assert settings_module.settings.llm_matcher_batch_size == 9
        assert settings_module.settings.llm_provider == "openai"
        assert settings_module.settings.providers_registry["custom"]["name"] == "Custom"
        assert settings_module._onec_settings.password == "secret"
        assert settings_module._db_loaded is True

    @pytest.mark.asyncio
    async def test_load_persisted_settings_handles_unavailable_or_bad_rows(self, mock_db_session):
        settings_module._db_loaded = False
        with patch.object(SettingsRepo, "get_all", new_callable=AsyncMock) as get_all:
            get_all.side_effect = RuntimeError("missing table")
            await settings_module.load_persisted_settings(mock_db_session)

        assert settings_module._db_loaded is False

        stored = {"providers_registry": "{bad", "onec": "{bad"}
        with patch.object(SettingsRepo, "get_all", new_callable=AsyncMock, return_value=stored):
            await settings_module.load_persisted_settings(mock_db_session, force=True)

        assert settings_module._db_loaded is True

    @pytest.mark.asyncio
    async def test_update_settings_rejects_incompatible_provider_roles(self, mock_db_session):
        user = _admin_user()
        with patch.object(SettingsRepo, "get_all", new_callable=AsyncMock, return_value={}):
            with pytest.raises(settings_module.HTTPException) as exc_info:
                await settings_module.update_settings(
                    settings_module.SettingsUpdateInput(llm_provider="jina"),
                    current_user=user,
                    db=mock_db_session,
                )
        assert exc_info.value.status_code == 422

        with patch.object(SettingsRepo, "get_all", new_callable=AsyncMock, return_value={}):
            with pytest.raises(settings_module.HTTPException) as exc_info:
                await settings_module.update_settings(
                    settings_module.SettingsUpdateInput(embedding_provider="moonshot"),
                    current_user=user,
                    db=mock_db_session,
                )
        assert exc_info.value.status_code == 422

        with patch.object(SettingsRepo, "get_all", new_callable=AsyncMock, return_value={}):
            with pytest.raises(settings_module.HTTPException) as exc_info:
                await settings_module.update_settings(
                    settings_module.SettingsUpdateInput(rerank_provider="openai"),
                    current_user=user,
                    db=mock_db_session,
                )
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_update_settings_applies_all_fields_and_masks_onec_password(
        self, mock_db_session
    ):
        user = _admin_user()
        settings_module._onec_settings = settings_module.OneCConnectionSettings(
            base_url="http://old.example",
            username="old",
            password="keep-me",
            enabled=True,
        )
        body = settings_module.SettingsUpdateInput(
            llm_provider="local",
            embedding_provider="local",
            rerank_provider="llm-fallback",
            providers_registry=[
                settings_module.ProviderConfigInput(
                    id="local", api_key="new-key", base_url="http://localhost:11434/v1"
                )
            ],
            llm_model="qwen2.5:14b",
            llm_rerank_model="qwen2.5:14b",
            embedding_model="local-embedding",
            embedding_dimensions=1024,
            auto_match_threshold=0.94,
            review_threshold=0.74,
            retrieval_top_n=88,
            rerank_top_n=12,
            agentic_resolution_enabled=False,
            small_catalog_threshold=123,
            llm_matcher_enabled=True,
            llm_matcher_model="qwen2.5:14b",
            llm_matcher_batch_size=7,
            onec=settings_module.OneCConnectionSettings(
                base_url="http://new.example",
                username="new",
                password="********",
                enabled=True,
            ),
        )

        with (
            patch.object(SettingsRepo, "get_all", new_callable=AsyncMock, return_value={}),
            patch.object(SettingsRepo, "upsert", new_callable=AsyncMock),
            patch("matcher.indexing.embedder.reset_client") as reset_client,
            patch("matcher.api.v1.settings.AuditRepo") as MockAuditRepo,
        ):
            MockAuditRepo.return_value.log = AsyncMock()
            result = await settings_module.update_settings(
                body, current_user=user, db=mock_db_session
            )

        assert result.llm_model == "qwen2.5:14b"
        assert result.rerank_provider == "llm-fallback"
        assert result.onec.password == "********"
        assert settings_module._onec_settings.password == "keep-me"
        assert settings_module.settings.retrieval_top_n == 88
        reset_client.assert_called_once()
        MockAuditRepo.return_value.log.assert_awaited_once()
        assert mock_db_session.commit.await_count >= 2

    @pytest.mark.asyncio
    async def test_update_settings_rolls_back_runtime_on_persist_failure(self, mock_db_session):
        user = _admin_user()
        original_threshold = settings_module.settings.auto_match_threshold

        with (
            patch.object(SettingsRepo, "get_all", new_callable=AsyncMock, return_value={}),
            patch("matcher.api.v1.settings._persist_settings", new_callable=AsyncMock) as persist,
        ):
            persist.side_effect = RuntimeError("db down")
            with pytest.raises(settings_module.HTTPException) as exc_info:
                await settings_module.update_settings(
                    settings_module.SettingsUpdateInput(auto_match_threshold=0.99),
                    current_user=user,
                    db=mock_db_session,
                )

        assert exc_info.value.status_code == 500
        assert settings_module.settings.auto_match_threshold == original_threshold
        mock_db_session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_models_parses_provider_responses_and_fallbacks(self):
        user = _admin_user()
        _FakeModelsClient.calls = []
        _FakeModelsClient.error = None
        _FakeModelsClient.response = _models_response(
            {
                "models": [
                    {"name": "cohere-rerank", "endpoints": ["rerank"], "context_window": 4096},
                    {"id": "cohere-embed", "endpoints": ["embed"], "context_length": 512},
                    {"id": "cohere-chat", "endpoints": ["chat"], "context_length": 128000},
                    {"id": "skip-empty"},
                ]
            }
        )

        with patch("matcher.api.v1.settings.httpx.AsyncClient", _FakeModelsClient):
            result = await settings_module.list_models(provider_id="cohere", current_user=user)

        model_types = {m.id: m.type for m in result.models}
        assert model_types["cohere-rerank"] == "rerank"
        assert model_types["cohere-embed"] == "embedding"
        assert model_types["cohere-chat"] == "chat"

        _FakeModelsClient.calls = []
        _FakeModelsClient.response = _models_response(
            {
                "data": [
                    {"id": "lang-model", "name": "Language", "type": "language"},
                    {"id": "visual-model", "architecture": {"modality": "image"}},
                    {"id": "custom-embed-model"},
                    {"id": "bge-ranker"},
                    {},
                ]
            }
        )

        with patch("matcher.api.v1.settings.httpx.AsyncClient", _FakeModelsClient):
            result = await settings_module.list_models(provider_id="google", current_user=user)

        assert _FakeModelsClient.calls[0]["headers"] == {}
        assert "visual-model" not in {m.id for m in result.models}
        assert {m.id: m.type for m in result.models}["lang-model"] == "chat"
        assert {m.id: m.type for m in result.models}["custom-embed-model"] == "embedding"
        assert {m.id: m.type for m in result.models}["bge-ranker"] == "rerank"

        _FakeModelsClient.error = httpx.RequestError("network")
        with patch("matcher.api.v1.settings.httpx.AsyncClient", _FakeModelsClient):
            result = await settings_module.list_models(provider_id="openai", current_user=user)
        assert any(m.id == "gpt-4o" for m in result.models)

        result = await settings_module.list_models(
            provider_id="unknown-provider", current_user=user
        )
        assert result.models == []

    @pytest.mark.asyncio
    async def test_test_onec_connection_branches(self):
        user = _admin_user()
        settings_module._onec_settings = settings_module.OneCConnectionSettings()
        with pytest.raises(settings_module.HTTPException) as exc_info:
            await settings_module.test_onec_connection(current_user=user)
        assert exc_info.value.status_code == 400

        settings_module._onec_settings = settings_module.OneCConnectionSettings(
            base_url="http://blocked.example",
            enabled=True,
        )
        with patch("matcher.api.v1.settings.validate_url_safe") as validate:
            validate.side_effect = SSRFError("blocked")
            result = await settings_module.test_onec_connection(current_user=user)
        assert result == {"status": "error", "detail": "URL validation failed: blocked"}

        client = SimpleNamespace(
            health_check=AsyncMock(return_value={"status": "ok"}),
            get_total_count=AsyncMock(return_value=42),
            get_metadata_fields=AsyncMock(return_value=[f"field_{i}" for i in range(35)]),
        )
        settings_module._onec_settings = settings_module.OneCConnectionSettings(
            base_url="http://onec.example",
            username="u",
            password="p",
            enabled=True,
        )
        with (
            patch("matcher.api.v1.settings.validate_url_safe"),
            patch("matcher.ingestion.onec_adapter.OneCODataClient", return_value=client),
        ):
            result = await settings_module.test_onec_connection(current_user=user)

        assert result["status"] == "ok"
        assert result["total_items"] == 42
        assert len(result["available_fields"]) == 30

        client = SimpleNamespace(
            health_check=AsyncMock(return_value={"status": "ok"}),
            get_total_count=AsyncMock(side_effect=RuntimeError("count failed")),
            get_metadata_fields=AsyncMock(side_effect=RuntimeError("metadata failed")),
        )
        with (
            patch("matcher.api.v1.settings.validate_url_safe"),
            patch("matcher.ingestion.onec_adapter.OneCODataClient", return_value=client),
        ):
            result = await settings_module.test_onec_connection(current_user=user)
        assert result == {"status": "ok"}

        client = SimpleNamespace(
            health_check=AsyncMock(return_value={"status": "error", "detail": "bad auth"}),
            get_total_count=AsyncMock(),
            get_metadata_fields=AsyncMock(),
        )
        with (
            patch("matcher.api.v1.settings.validate_url_safe"),
            patch("matcher.ingestion.onec_adapter.OneCODataClient", return_value=client),
        ):
            result = await settings_module.test_onec_connection(current_user=user)
        assert result == {"status": "error", "detail": "bad auth"}
        client.get_total_count.assert_not_awaited()
