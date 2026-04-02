from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProviderCapabilities(BaseModel):
    """Declarative capability metadata for a provider. Code-only, never persisted."""

    supports_embeddings: bool = False
    supports_chat: bool = False
    supports_rerank: bool = False
    rerank_mode: Literal["direct", "llm-fallback", "local"] | None = None
    supports_tool_calling: bool = False
    supports_structured_outputs: bool = False
    supports_web_search: bool = False
    api_style: Literal["openai-compatible", "google-native", "cohere-v2", "dashscope"] = (
        "openai-compatible"
    )
    region: str | None = None
    is_beta: bool = False
    notes: str | None = None


# Authoritative capability registry — maps provider IDs to their capabilities.
# This is code-only metadata: never serialized to DB, never user-modifiable.
PROVIDER_CAPABILITIES: dict[str, ProviderCapabilities] = {
    "openai": ProviderCapabilities(
        supports_chat=True,
        supports_embeddings=True,
        supports_tool_calling=True,
        supports_structured_outputs=True,
    ),
    "openrouter": ProviderCapabilities(
        supports_chat=True,
        supports_embeddings=True,
        supports_tool_calling=True,
        supports_structured_outputs=True,
        supports_web_search=True,
    ),
    "together": ProviderCapabilities(
        supports_chat=True,
        supports_embeddings=True,
        supports_rerank=True,
        rerank_mode="direct",
        supports_tool_calling=True,
        notes="Rerank requires dedicated endpoint on Together",
    ),
    "dashscope": ProviderCapabilities(
        supports_chat=True,
        supports_embeddings=True,
        supports_rerank=True,
        rerank_mode="direct",
        supports_tool_calling=True,
        supports_structured_outputs=True,
        supports_web_search=True,
        api_style="dashscope",
        region="cn",
    ),
    "jina": ProviderCapabilities(
        supports_embeddings=True,
        supports_rerank=True,
        rerank_mode="direct",
    ),
    "cohere": ProviderCapabilities(
        supports_chat=True,
        supports_embeddings=True,
        supports_rerank=True,
        rerank_mode="direct",
        api_style="cohere-v2",
    ),
    "google": ProviderCapabilities(
        supports_chat=True,
        supports_embeddings=True,
        supports_tool_calling=True,
        supports_structured_outputs=True,
        api_style="google-native",
    ),
    "local": ProviderCapabilities(
        supports_chat=True,
        supports_embeddings=True,
        supports_rerank=True,
        rerank_mode="local",
    ),
    # Regional providers (beta stubs — OpenAI-compatible, no custom API code yet)
    "yandex": ProviderCapabilities(
        supports_chat=True,
        supports_embeddings=True,
        supports_tool_calling=True,
        supports_web_search=True,
        region="ru",
        is_beta=True,
        notes="Yandex AI Studio — Russian/CIS regional lane",
    ),
    "gigachat": ProviderCapabilities(
        supports_chat=True,
        supports_embeddings=True,
        region="ru",
        is_beta=True,
        notes="GigaChat (Sber) — Russian enterprise lane",
    ),
    "moonshot": ProviderCapabilities(
        supports_chat=True,
        supports_tool_calling=True,
        supports_web_search=True,
        region="cn",
        is_beta=True,
        notes="Moonshot / Kimi — Chinese regional lane",
    ),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    _INSECURE_JWT_SECRETS: frozenset[str] = frozenset(
        {
            "change-me-in-production",
            "dev-only-not-for-production",
            "secret",
            "changeme",
            "CHANGE_ME",
            "CHANGE_ME_USE_openssl_rand_hex_32",
        }
    )

    @model_validator(mode="after")
    def _check_jwt_secret(self) -> Settings:
        is_debug = self.log_level.upper() == "DEBUG"
        secret = self.jwt_secret_key
        if secret in self._INSECURE_JWT_SECRETS or len(secret) < 32:
            if not is_debug:
                raise ValueError(
                    "JWT_SECRET_KEY is insecure (known default or shorter than 32 chars). "
                    "Generate a proper secret: "
                    'python -c "import secrets; print(secrets.token_hex(32))" '
                    "and set it via the JWT_SECRET_KEY env var. "
                    "Set LOG_LEVEL=DEBUG to bypass this check for local development only."
                )
        return self

    @model_validator(mode="after")
    def _check_cors_credentials(self) -> Settings:
        """Prevent wildcard CORS with credentials outside of debug mode."""
        if "*" in self.cors_origins and self.log_level.upper() != "DEBUG":
            raise ValueError(
                "CORS_ORIGINS contains '*' which is unsafe with allow_credentials=True. "
                "Set explicit origins in CORS_ORIGINS for production, "
                "e.g. CORS_ORIGINS='[\"https://your-domain.com\"]'. "
                "Set LOG_LEVEL=DEBUG to bypass this check for local development."
            )
        return self

    database_url: str = "postgresql+asyncpg://matcher:matcher@localhost:5432/matcher"
    redis_url: str = "redis://localhost:6379"
    catalog_upload_dir: str = "/var/lib/matcher/uploads"

    # Provider: "openai" | "openrouter" | "google"
    embedding_provider: str = "jina"
    llm_provider: str = "google"
    rerank_provider: str = "jina"

    # Dynamic Provider Registry
    providers_registry: dict[str, dict[str, str]] = {
        "local": {
            "id": "local",
            "name": "Local Pipeline (OSS)",
            "api_key": "none",
            "base_url": "http://localhost:11434/v1",
        },
        "openai": {
            "id": "openai",
            "name": "OpenAI",
            "api_key": "",
            "base_url": "https://api.openai.com/v1",
        },
        "openrouter": {
            "id": "openrouter",
            "name": "OpenRouter",
            "api_key": "",
            "base_url": "https://openrouter.ai/api/v1",
        },
        "together": {
            "id": "together",
            "name": "Together AI",
            "api_key": "",
            "base_url": "https://api.together.xyz/v1",
        },
        "dashscope": {
            "id": "dashscope",
            "name": "Alibaba DashScope",
            "api_key": "",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        },
        "jina": {
            "id": "jina",
            "name": "Jina AI",
            "api_key": "",
            "base_url": "https://api.jina.ai/v1",
        },
        "google": {
            "id": "google",
            "name": "Google Gemini",
            "api_key": "",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        },
        "cohere": {
            "id": "cohere",
            "name": "Cohere",
            "api_key": "",
            "base_url": "https://api.cohere.com/v1",
        },
        "yandex": {
            "id": "yandex",
            "name": "Yandex AI Studio",
            "api_key": "",
            "base_url": "https://llm.api.cloud.yandex.net/foundationModels/v1",
        },
        "gigachat": {
            "id": "gigachat",
            "name": "GigaChat (Sber)",
            "api_key": "",
            "base_url": "https://gigachat.devices.sberbank.ru/api/v1",
        },
        "moonshot": {
            "id": "moonshot",
            "name": "Moonshot / Kimi",
            "api_key": "",
            "base_url": "https://api.moonshot.cn/v1",
        },
    }

    # JWT auth
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480

    # Cookie settings (for httpOnly JWT transport)
    cookie_secure: bool = False  # Set True in production (HTTPS only)
    cookie_samesite: str = "lax"  # "lax" | "strict" | "none"
    cookie_domain: str = ""  # Empty = browser auto-detects

    # CORS
    cors_origins: list[str] = ["*"]

    # Logging
    log_level: str = "INFO"

    # Request timeout (seconds)
    request_timeout_seconds: int = 120

    # Matching thresholds
    auto_match_threshold: float = 0.93
    review_threshold: float = 0.75
    batch_concurrency: int = 5  # Max concurrent items in batch processing
    retrieval_top_n: int = 50
    rerank_top_n: int = 5
    rerank_enabled: bool = True
    agentic_resolution_enabled: bool = False

    # Adaptive retrieval
    small_catalog_threshold: int = 500  # Below this, retrieval returns all products

    # LLM Matcher mode
    llm_matcher_enabled: bool = True
    llm_matcher_model: str = ""  # if empty, uses llm_model
    llm_matcher_batch_size: int = 5  # items per LLM call in small-catalog batch mode

    # Embedding config
    embedding_model: str = "jina-embeddings-v3"
    embedding_dimensions: int = 1024

    # LLM config (for reranking fallback / explanation generation)
    llm_model: str = "gemini-2.5-flash"
    llm_rerank_model: str = ""  # if empty, uses llm_model

    # Provider secrets are env-first in production. Persisted DB settings are
    # still allowed for local/dev and as a fallback when env vars are absent.
    openai_api_key: str = ""
    openrouter_api_key: str = ""
    together_api_key: str = ""
    dashscope_api_key: str = ""
    jina_api_key: str = ""
    google_api_key: str = ""
    cohere_api_key: str = ""
    yandex_api_key: str = ""
    gigachat_api_key: str = ""
    moonshot_api_key: str = ""

    def provider_supports(self, provider_id: str, role: str) -> bool:
        """Check if a provider supports a given role ('chat', 'embeddings', 'rerank')."""
        caps = PROVIDER_CAPABILITIES.get(provider_id)
        if not caps:
            return False
        if role == "chat":
            return caps.supports_chat
        if role == "embeddings":
            return caps.supports_embeddings
        if role == "rerank":
            return caps.supports_rerank
        return False

    def env_provider_api_keys(self) -> dict[str, str]:
        return {
            "openai": self.openai_api_key,
            "openrouter": self.openrouter_api_key,
            "together": self.together_api_key,
            "dashscope": self.dashscope_api_key,
            "jina": self.jina_api_key,
            "google": self.google_api_key,
            "cohere": self.cohere_api_key,
            "yandex": self.yandex_api_key,
            "gigachat": self.gigachat_api_key,
            "moonshot": self.moonshot_api_key,
        }

    def env_provider_api_key(self, provider_id: str) -> str:
        return self.env_provider_api_keys().get(provider_id, "")

    def apply_env_provider_secrets(self) -> None:
        for provider_id, api_key in self.env_provider_api_keys().items():
            if not api_key:
                continue
            provider = self.providers_registry.get(provider_id)
            if provider is None:
                continue
            provider["api_key"] = api_key

    def effective_provider_api_key(self, provider_id: str) -> str:
        env_api_key = self.env_provider_api_key(provider_id)
        if env_api_key:
            return env_api_key
        provider = self.providers_registry.get(provider_id)
        return provider.get("api_key", "") if provider else ""

    def effective_provider_base_url(self, provider_id: str) -> str:
        provider = self.providers_registry.get(provider_id)
        return provider.get("base_url", "") if provider else ""

    @property
    def active_embedding_api_key(self) -> str:
        return self.effective_provider_api_key(self.embedding_provider)

    @property
    def active_embedding_base_url(self) -> str:
        return self.effective_provider_base_url(self.embedding_provider)

    @property
    def active_llm_api_key(self) -> str:
        return self.effective_provider_api_key(self.llm_provider)

    @property
    def active_llm_base_url(self) -> str:
        return self.effective_provider_base_url(self.llm_provider)

    @property
    def active_rerank_api_key(self) -> str:
        if self.rerank_provider == "llm-fallback":
            return self.active_llm_api_key
        return self.effective_provider_api_key(self.rerank_provider)

    @property
    def active_rerank_base_url(self) -> str:
        if self.rerank_provider == "llm-fallback":
            return self.active_llm_base_url
        return self.effective_provider_base_url(self.rerank_provider)

    @property
    def catalog_upload_path(self) -> Path:
        return Path(self.catalog_upload_dir)

    @property
    def async_database_url(self) -> str:
        """Database URL with asyncpg driver for async SQLAlchemy."""
        url = self.database_url
        if "+psycopg" in url:
            url = url.replace("+psycopg", "+asyncpg")
        elif "postgresql://" in url and "+asyncpg" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://")
        return url

    @property
    def sync_database_url(self) -> str:
        """Database URL with sync driver for Alembic."""
        url = self.database_url
        if "+asyncpg" in url:
            url = url.replace("+asyncpg", "")
        elif "+psycopg" in url:
            url = url.replace("+psycopg", "")
        return url


settings = Settings()
settings.apply_env_provider_secrets()
