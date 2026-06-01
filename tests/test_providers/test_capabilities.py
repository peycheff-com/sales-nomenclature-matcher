"""Tests for the Provider Capability Registry."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from matcher.config import PROVIDER_CAPABILITIES, Settings

# ── Registry internal consistency ──────────────────────────────────────────


class TestRegistryConsistency:
    """Every entry in PROVIDER_CAPABILITIES must be internally consistent."""

    def test_all_registry_providers_have_capabilities(self):
        """Every provider in the default providers_registry has a capabilities entry."""
        s = Settings(
            jwt_secret_key="x" * 32,
            log_level="DEBUG",
        )
        for pid in s.providers_registry:
            assert pid in PROVIDER_CAPABILITIES, (
                f"Provider '{pid}' is in providers_registry but missing from PROVIDER_CAPABILITIES"
            )

    def test_all_capabilities_have_registry_entry(self):
        """Every provider in PROVIDER_CAPABILITIES has a providers_registry entry."""
        s = Settings(
            jwt_secret_key="x" * 32,
            log_level="DEBUG",
        )
        for pid in PROVIDER_CAPABILITIES:
            assert pid in s.providers_registry, (
                f"Provider '{pid}' is in PROVIDER_CAPABILITIES but missing from providers_registry"
            )

    @pytest.mark.parametrize("pid", list(PROVIDER_CAPABILITIES.keys()))
    def test_rerank_mode_consistency(self, pid: str):
        """supports_rerank=True iff rerank_mode is not None."""
        caps = PROVIDER_CAPABILITIES[pid]
        if caps.supports_rerank:
            assert caps.rerank_mode is not None, (
                f"Provider '{pid}' supports_rerank=True but rerank_mode is None"
            )
        else:
            assert caps.rerank_mode is None, (
                f"Provider '{pid}' supports_rerank=False but rerank_mode='{caps.rerank_mode}'"
            )

    @pytest.mark.parametrize("pid", list(PROVIDER_CAPABILITIES.keys()))
    def test_api_style_valid(self, pid: str):
        """api_style is one of the allowed values."""
        allowed = {"openai-compatible", "google-native", "cohere-v2", "dashscope"}
        caps = PROVIDER_CAPABILITIES[pid]
        assert caps.api_style in allowed, (
            f"Provider '{pid}' has invalid api_style='{caps.api_style}'"
        )


# ── Code-referenced providers exist ───────────────────────────────────────


class TestCodeReferencedProviders:
    """Provider IDs hardcoded in pipeline code must exist in the registry."""

    # Provider IDs referenced in reranker.py _http_rerank dispatch
    @pytest.mark.parametrize("pid", ["cohere", "together", "jina", "dashscope"])
    def test_reranker_http_providers(self, pid: str):
        assert pid in PROVIDER_CAPABILITIES
        assert PROVIDER_CAPABILITIES[pid].supports_rerank

    def test_reranker_local_provider(self):
        assert "local" in PROVIDER_CAPABILITIES
        assert PROVIDER_CAPABILITIES["local"].supports_rerank
        assert PROVIDER_CAPABILITIES["local"].rerank_mode == "local"

    # Provider IDs referenced in embedder.py
    def test_embedder_google_provider(self):
        assert "google" in PROVIDER_CAPABILITIES
        assert PROVIDER_CAPABILITIES["google"].supports_embeddings
        assert PROVIDER_CAPABILITIES["google"].api_style == "google-native"

    # Provider IDs referenced in agent.py for web search
    @pytest.mark.parametrize("pid", ["openrouter", "dashscope"])
    def test_agent_web_search_providers(self, pid: str):
        assert pid in PROVIDER_CAPABILITIES
        assert PROVIDER_CAPABILITIES[pid].supports_web_search


# ── provider_supports() correctness ──────────────────────────────────────


class TestProviderSupports:
    """The provider_supports() helper returns correct results."""

    @pytest.fixture()
    def s(self) -> Settings:
        return Settings(
            jwt_secret_key="x" * 32,
            log_level="DEBUG",
        )

    # Known true cases
    def test_openai_supports_chat(self, s: Settings):
        assert s.provider_supports("openai", "chat") is True

    def test_openai_supports_embeddings(self, s: Settings):
        assert s.provider_supports("openai", "embeddings") is True

    def test_cohere_supports_rerank(self, s: Settings):
        assert s.provider_supports("cohere", "rerank") is True

    def test_jina_supports_embeddings(self, s: Settings):
        assert s.provider_supports("jina", "embeddings") is True

    def test_together_supports_rerank(self, s: Settings):
        assert s.provider_supports("together", "rerank") is True

    # Known false cases
    def test_jina_no_chat(self, s: Settings):
        assert s.provider_supports("jina", "chat") is False

    def test_openai_no_rerank(self, s: Settings):
        assert s.provider_supports("openai", "rerank") is False

    def test_google_no_rerank(self, s: Settings):
        assert s.provider_supports("google", "rerank") is False

    def test_moonshot_no_embeddings(self, s: Settings):
        assert s.provider_supports("moonshot", "embeddings") is False

    # Edge cases
    def test_nonexistent_provider(self, s: Settings):
        assert s.provider_supports("nonexistent", "chat") is False

    def test_unknown_role(self, s: Settings):
        assert s.provider_supports("openai", "unknown_role") is False


# ── Regional providers are beta ───────────────────────────────────────────


class TestRegionalProviders:
    """Regional provider stubs are marked beta and have correct regions."""

    @pytest.mark.parametrize(
        ("pid", "region"),
        [("yandex", "ru"), ("gigachat", "ru"), ("moonshot", "cn")],
    )
    def test_regional_is_beta(self, pid: str, region: str):
        caps = PROVIDER_CAPABILITIES[pid]
        assert caps.is_beta is True
        assert caps.region == region


class TestSettingsDefaultsAndSecrets:
    """Settings should default to free local mode and keep production guardrails."""

    def test_defaults_are_free_local_first(self):
        s = Settings(_env_file=None, jwt_secret_key="x" * 32, log_level="DEBUG")

        assert s.embedding_provider == "local"
        assert s.llm_provider == "local"
        assert s.rerank_provider == "local"
        assert s.embedding_dimensions == 384
        assert s.embedding_model == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        assert s.llm_model == "qwen2.5:7b-instruct"
        assert s.active_embedding_base_url == "http://localhost:11434/v1"

    def test_insecure_jwt_secret_rejected_outside_debug(self):
        with pytest.raises(ValidationError, match="JWT_SECRET_KEY is insecure"):
            Settings(
                _env_file=None,
                jwt_secret_key="change-me-in-production",
                log_level="INFO",
                cors_origins=["https://example.com"],
            )

    def test_wildcard_cors_rejected_outside_debug(self):
        with pytest.raises(ValidationError, match="CORS_ORIGINS contains"):
            Settings(_env_file=None, jwt_secret_key="x" * 32, log_level="INFO", cors_origins=["*"])

    def test_debug_allows_local_insecure_defaults(self):
        s = Settings(
            _env_file=None,
            jwt_secret_key="change-me-in-production",
            log_level="DEBUG",
            cors_origins=["*"],
        )

        assert s.cors_origins == ["*"]

    def test_env_provider_secrets_override_registry_values(self):
        s = Settings(
            _env_file=None,
            jwt_secret_key="x" * 32,
            log_level="DEBUG",
            openai_api_key="env-openai",
            providers_registry={
                "openai": {
                    "id": "openai",
                    "name": "OpenAI",
                    "api_key": "stored-openai",
                    "base_url": "https://api.openai.com/v1",
                },
            },
        )

        assert s.env_provider_api_key("openai") == "env-openai"
        assert s.effective_provider_api_key("openai") == "env-openai"
        assert s.effective_provider_api_key("missing") == ""
        assert s.effective_provider_base_url("missing") == ""

        s.apply_env_provider_secrets()
        assert s.providers_registry["openai"]["api_key"] == "env-openai"

    def test_env_provider_secrets_ignore_missing_registry_entries(self):
        s = Settings(
            _env_file=None,
            jwt_secret_key="x" * 32,
            log_level="DEBUG",
            openai_api_key="env-openai",
            embedding_provider="missing",
            llm_provider="missing",
            providers_registry={},
        )

        s.apply_env_provider_secrets()

        assert s.active_embedding_api_key == ""
        assert s.active_embedding_base_url == ""
        assert s.active_llm_api_key == ""
        assert s.active_llm_base_url == ""
        assert s.active_rerank_api_key == ""
        assert s.active_rerank_base_url == ""
        assert str(s.catalog_upload_path) == s.catalog_upload_dir

    def test_rerank_llm_fallback_reuses_active_llm_provider(self):
        s = Settings(
            _env_file=None,
            jwt_secret_key="x" * 32,
            log_level="DEBUG",
            llm_provider="openrouter",
            rerank_provider="llm-fallback",
            openrouter_api_key="router-key",
        )

        assert s.active_llm_api_key == "router-key"
        assert s.active_rerank_api_key == "router-key"
        assert s.active_rerank_base_url == "https://openrouter.ai/api/v1"

    @pytest.mark.parametrize(
        ("database_url", "async_url", "sync_url"),
        [
            (
                "postgresql://user:pass@localhost/db",
                "postgresql+asyncpg://user:pass@localhost/db",
                "postgresql://user:pass@localhost/db",
            ),
            (
                "postgresql+psycopg://user:pass@localhost/db",
                "postgresql+asyncpg://user:pass@localhost/db",
                "postgresql://user:pass@localhost/db",
            ),
            (
                "postgresql+asyncpg://user:pass@localhost/db",
                "postgresql+asyncpg://user:pass@localhost/db",
                "postgresql://user:pass@localhost/db",
            ),
        ],
    )
    def test_database_url_driver_conversions(
        self,
        database_url: str,
        async_url: str,
        sync_url: str,
    ):
        s = Settings(
            _env_file=None,
            jwt_secret_key="x" * 32,
            log_level="DEBUG",
            database_url=database_url,
        )

        assert s.async_database_url == async_url
        assert s.sync_database_url == sync_url
