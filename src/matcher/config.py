from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

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

    # OpenAI
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"

    # OpenRouter
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Cohere (for reranker)
    cohere_api_key: str = ""

    # Google
    google_api_key: str = ""

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

    # Embedding config
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 1024

    # LLM config (for reranking fallback / explanation generation)
    llm_model: str = "gpt-4o-mini"
    llm_rerank_model: str = ""  # if empty, uses llm_model

    @property
    def active_embedding_api_key(self) -> str:
        if self.embedding_provider == "openrouter":
            return self.openrouter_api_key
        if self.embedding_provider == "google":
            return self.google_api_key
        return self.openai_api_key

    @property
    def active_embedding_base_url(self) -> str:
        if self.embedding_provider == "openrouter":
            return self.openrouter_base_url
        return self.openai_base_url

    @property
    def active_llm_api_key(self) -> str:
        if self.llm_provider == "openrouter":
            return self.openrouter_api_key
        return self.openai_api_key

    @property
    def active_llm_base_url(self) -> str:
        if self.llm_provider == "openrouter":
            return self.openrouter_base_url
        return self.openai_base_url

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
