from __future__ import annotations

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProviderConfig(BaseModel):
    api_key: str = ""
    base_url: str = ""


def _default_providers() -> dict[str, ProviderConfig]:
    return {
        "openai": ProviderConfig(base_url="https://api.openai.com/v1"),
        "openrouter": ProviderConfig(base_url="https://openrouter.ai/api/v1"),
        "together": ProviderConfig(base_url="https://api.together.xyz/v1"),
        "dashscope": ProviderConfig(base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "jina": ProviderConfig(base_url="https://api.jina.ai/v1"),
        "cohere": ProviderConfig(base_url="https://api.cohere.ai/v1"),
        "google": ProviderConfig(),
        "local": ProviderConfig(api_key="none", base_url="http://localhost:11434/v1"),
    }


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    _INSECURE_JWT_SECRETS: frozenset[str] = frozenset({
        "change-me-in-production",
        "dev-only-not-for-production",
        "secret",
        "changeme",
        "CHANGE_ME",
        "CHANGE_ME_USE_openssl_rand_hex_32",
    })

    @model_validator(mode="after")
    def _check_jwt_secret(self) -> "Settings":
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
    def _check_cors_credentials(self) -> "Settings":
        """Prevent wildcard CORS with credentials outside of debug mode."""
        if (
            "*" in self.cors_origins
            and self.log_level.upper() != "DEBUG"
        ):
            raise ValueError(
                "CORS_ORIGINS contains '*' which is unsafe with allow_credentials=True. "
                "Set explicit origins in CORS_ORIGINS for production, "
                'e.g. CORS_ORIGINS=\'["https://your-domain.com"]\'. '
                "Set LOG_LEVEL=DEBUG to bypass this check for local development."
            )
        return self

    database_url: str = "postgresql+asyncpg://matcher:matcher@localhost:5432/matcher"
    redis_url: str = "redis://localhost:6379"

    # Provider: "openai" | "openrouter" | "google"
    embedding_provider: str = "openai"
    llm_provider: str = "openai"
    rerank_provider: str = "llm-fallback"

    # Dynamic Provider Registry
    providers_registry: dict[str, dict[str, str]] = {
        "local": {"id": "local", "name": "Local Pipeline (OSS)", "api_key": "none", "base_url": "http://localhost:11434/v1"},
        "openai": {"id": "openai", "name": "OpenAI", "api_key": "", "base_url": "https://api.openai.com/v1"},
        "openrouter": {"id": "openrouter", "name": "OpenRouter", "api_key": "", "base_url": "https://openrouter.ai/api/v1"},
        "together": {"id": "together", "name": "Together AI", "api_key": "", "base_url": "https://api.together.xyz/v1"},
        "dashscope": {"id": "dashscope", "name": "Alibaba DashScope", "api_key": "", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
        "jina": {"id": "jina", "name": "Jina AI", "api_key": "", "base_url": "https://api.jina.ai/v1"},
        "google": {"id": "google", "name": "Google Gemini", "api_key": "", "base_url": ""},
        "cohere": {"id": "cohere", "name": "Cohere", "api_key": "", "base_url": "https://api.cohere.com/v1"},
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
    retrieval_top_n: int = 50
    rerank_top_n: int = 5
    rerank_enabled: bool = True
    agentic_resolution_enabled: bool = False

    # Embedding config
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 1024

    # LLM config (for reranking fallback / explanation generation)
    llm_model: str = "gpt-4o-mini"
    llm_rerank_model: str = ""  # if empty, uses llm_model

    @property
    def active_embedding_api_key(self) -> str:
        provider = self.providers_registry.get(self.embedding_provider)
        return provider.get("api_key", "") if provider else ""

    @property
    def active_embedding_base_url(self) -> str:
        provider = self.providers_registry.get(self.embedding_provider)
        return provider.get("base_url", "") if provider else ""

    @property
    def active_llm_api_key(self) -> str:
        provider = self.providers_registry.get(self.llm_provider)
        return provider.get("api_key", "") if provider else ""

    @property
    def active_llm_base_url(self) -> str:
        provider = self.providers_registry.get(self.llm_provider)
        return provider.get("base_url", "") if provider else ""

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
