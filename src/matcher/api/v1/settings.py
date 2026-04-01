"""Settings API -- runtime configuration for models, 1C, thresholds."""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.api.deps import get_db
from matcher.auth.deps import get_current_user, require_role
from matcher.config import settings
from matcher.db.models import User
from matcher.db.repos.settings import SettingsRepo
from matcher.security.url_validator import SSRFError, validate_url_safe

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Settings"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class OneCConnectionSettings(BaseModel):
    base_url: str = ""
    username: str = ""
    password: str = ""
    catalog_endpoint: str = "/hs/catalog/v1/nomenclature"
    enabled: bool = False


class ProviderConfigResponse(BaseModel):
    id: str
    name: str
    api_key_set: bool
    base_url: str

class SettingsResponse(BaseModel):
    # Provider
    llm_provider: str
    embedding_provider: str
    rerank_provider: str
    providers_registry: list[ProviderConfigResponse]
    # Models
    llm_model: str
    llm_rerank_model: str
    embedding_model: str
    embedding_dimensions: int
    # Thresholds
    auto_match_threshold: float
    review_threshold: float
    retrieval_top_n: int
    rerank_top_n: int
    agentic_resolution_enabled: bool
    # 1C Connection
    onec: OneCConnectionSettings


class ProviderConfigInput(BaseModel):
    id: str
    api_key: str | None = None
    base_url: str | None = None

class SettingsUpdateInput(BaseModel):
    llm_provider: str | None = None
    embedding_provider: str | None = None
    rerank_provider: str | None = None
    providers_registry: list[ProviderConfigInput] | None = None
    llm_model: str | None = None
    llm_rerank_model: str | None = None
    embedding_model: str | None = None
    embedding_dimensions: int | None = None
    auto_match_threshold: float | None = None
    review_threshold: float | None = None
    retrieval_top_n: int | None = None
    rerank_top_n: int | None = None
    agentic_resolution_enabled: bool | None = None
    onec: OneCConnectionSettings | None = None

    @model_validator(mode="after")
    def _validate_thresholds(self) -> "SettingsUpdateInput":
        if self.auto_match_threshold is not None and not (0.0 <= self.auto_match_threshold <= 1.0):
            raise ValueError("auto_match_threshold must be between 0.0 and 1.0")
        if self.review_threshold is not None and not (0.0 <= self.review_threshold <= 1.0):
            raise ValueError("review_threshold must be between 0.0 and 1.0")
        if self.retrieval_top_n is not None and not (1 <= self.retrieval_top_n <= 500):
            raise ValueError("retrieval_top_n must be between 1 and 500")
        if self.rerank_top_n is not None and not (1 <= self.rerank_top_n <= 100):
            raise ValueError("rerank_top_n must be between 1 and 100")
        if self.embedding_dimensions is not None and not (64 <= self.embedding_dimensions <= 4096):
            raise ValueError("embedding_dimensions must be between 64 and 4096")
        return self


class OpenRouterModel(BaseModel):
    id: str
    name: str
    context_length: int


class OpenRouterModelsResponse(BaseModel):
    models: list[OpenRouterModel]


# ── In-memory 1C settings ──────────────────────────────────────────────────

_onec_settings = OneCConnectionSettings()
_db_loaded: bool = False

# Keys that are persisted to the system_settings table.
_PERSIST_KEYS = (
    "auto_match_threshold",
    "review_threshold",
    "retrieval_top_n",
    "rerank_top_n",
    "agentic_resolution_enabled",
    "onec",
    "llm_provider",
    "embedding_provider",
    "rerank_provider",
    "llm_model",
    "llm_rerank_model",
    "embedding_model",
    "embedding_dimensions",
    "providers_registry",
)


async def load_persisted_settings(db: AsyncSession, force: bool = False) -> None:
    """Load persisted settings from DB into in-memory state."""
    global _onec_settings, _db_loaded

    if _db_loaded and not force:
        return

    try:
        repo = SettingsRepo(db)
        stored = await repo.get_all()
    except Exception:
        logger.debug("system_settings table not available yet, skipping load")
        return

    if "auto_match_threshold" in stored and stored["auto_match_threshold"] is not None:
        settings.auto_match_threshold = float(stored["auto_match_threshold"])
    if "review_threshold" in stored and stored["review_threshold"] is not None:
        settings.review_threshold = float(stored["review_threshold"])
    if "retrieval_top_n" in stored and stored["retrieval_top_n"] is not None:
        settings.retrieval_top_n = int(stored["retrieval_top_n"])
    if "rerank_top_n" in stored and stored["rerank_top_n"] is not None:
        settings.rerank_top_n = int(stored["rerank_top_n"])
    if "agentic_resolution_enabled" in stored and stored["agentic_resolution_enabled"] is not None:
        settings.agentic_resolution_enabled = stored["agentic_resolution_enabled"].lower() == "true"
    if "embedding_dimensions" in stored and stored["embedding_dimensions"] is not None:
        settings.embedding_dimensions = int(stored["embedding_dimensions"])

    for k in ("llm_provider", "embedding_provider", "rerank_provider", "llm_model", "llm_rerank_model", "embedding_model"):
        if k in stored and stored[k] is not None:
            setattr(settings, k, stored[k])

    if "providers_registry" in stored and stored["providers_registry"] is not None:
        try:
            persisted_providers = json.loads(stored["providers_registry"])
            for pid, pdata in persisted_providers.items():
                if pid in settings.providers_registry:
                    settings.providers_registry[pid].update(pdata)
                else:
                    settings.providers_registry[pid] = pdata
        except Exception as e:
            logger.warning("Failed to parse providers_registry: %s", e)

    if "onec" in stored and stored["onec"] is not None:
        try:
            _onec_settings = OneCConnectionSettings(**json.loads(stored["onec"]))
        except Exception:
            logger.warning("Failed to parse persisted 1C settings, keeping defaults")

    _db_loaded = True
    logger.info("Loaded persisted settings from DB")


async def _persist_settings(db: AsyncSession) -> None:
    """Write current threshold + 1C settings to DB."""
    repo = SettingsRepo(db)
    await repo.upsert("auto_match_threshold", str(settings.auto_match_threshold))
    await repo.upsert("review_threshold", str(settings.review_threshold))
    await repo.upsert("retrieval_top_n", str(settings.retrieval_top_n))
    await repo.upsert("rerank_top_n", str(settings.rerank_top_n))
    await repo.upsert("agentic_resolution_enabled", str(settings.agentic_resolution_enabled).lower())
    await repo.upsert("embedding_dimensions", str(settings.embedding_dimensions))
    await repo.upsert("onec", _onec_settings.model_dump_json())

    await repo.upsert("providers_registry", json.dumps(settings.providers_registry))

    for k in ("llm_provider", "embedding_provider", "rerank_provider", "llm_model", "llm_rerank_model", "embedding_model"):
        val = getattr(settings, k)
        if val is not None:
            await repo.upsert(k, str(val))


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/settings", response_model=SettingsResponse)
async def get_settings(
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> SettingsResponse:
    """Get current runtime settings."""
    await load_persisted_settings(db)
    prov_resp = []
    for pid, pdata in settings.providers_registry.items():
        prov_resp.append(
            ProviderConfigResponse(
                id=pid,
                name=pdata.get("name", pid),
                api_key_set=bool(pdata.get("api_key") and pdata.get("api_key") not in ("none", "", "your-key-here", "sk-your-key-here")),
                base_url=pdata.get("base_url", "")
            )
        )

    return SettingsResponse(
        llm_provider=settings.llm_provider,
        embedding_provider=settings.embedding_provider,
        rerank_provider=settings.rerank_provider,
        providers_registry=prov_resp,
        llm_model=settings.llm_model,
        llm_rerank_model=settings.llm_rerank_model,
        embedding_model=settings.embedding_model,
        embedding_dimensions=settings.embedding_dimensions,
        auto_match_threshold=settings.auto_match_threshold,
        review_threshold=settings.review_threshold,
        retrieval_top_n=settings.retrieval_top_n,
        rerank_top_n=settings.rerank_top_n,
        agentic_resolution_enabled=settings.agentic_resolution_enabled,
        onec=OneCConnectionSettings(
            base_url=_onec_settings.base_url,
            username=_onec_settings.username,
            password="********" if _onec_settings.password else "",
            catalog_endpoint=_onec_settings.catalog_endpoint,
            enabled=_onec_settings.enabled,
        ),
    )


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(
    body: SettingsUpdateInput,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> SettingsResponse:
    """Update runtime settings. Only provided fields are updated."""
    global _onec_settings

    if body.llm_provider is not None:
        settings.llm_provider = body.llm_provider
    if body.embedding_provider is not None:
        settings.embedding_provider = body.embedding_provider
    if body.rerank_provider is not None:
        settings.rerank_provider = body.rerank_provider
        
    if body.providers_registry is not None:
        for p in body.providers_registry:
            if p.id in settings.providers_registry:
                if p.api_key is not None:
                    settings.providers_registry[p.id]["api_key"] = p.api_key
                if p.base_url is not None:
                    settings.providers_registry[p.id]["base_url"] = p.base_url

    if body.llm_model is not None:
        settings.llm_model = body.llm_model
    if body.llm_rerank_model is not None:
        settings.llm_rerank_model = body.llm_rerank_model
    if body.embedding_model is not None:
        settings.embedding_model = body.embedding_model
    if body.embedding_dimensions is not None:
        settings.embedding_dimensions = body.embedding_dimensions
    if body.auto_match_threshold is not None:
        settings.auto_match_threshold = body.auto_match_threshold
    if body.review_threshold is not None:
        settings.review_threshold = body.review_threshold
    if body.retrieval_top_n is not None:
        settings.retrieval_top_n = body.retrieval_top_n
    if body.rerank_top_n is not None:
        settings.rerank_top_n = body.rerank_top_n
    if body.agentic_resolution_enabled is not None:
        settings.agentic_resolution_enabled = body.agentic_resolution_enabled
    if body.onec is not None:
        _onec_settings = body.onec

    # Persist thresholds + 1C settings to DB
    try:
        await _persist_settings(db)
    except Exception:
        logger.warning("Failed to persist settings to DB", exc_info=True)

    # Reset cached embedding client when provider/key changes
    if body.embedding_provider or body.providers_registry:
        from matcher.indexing.embedder import reset_client
        reset_client()

    logger.info("Settings updated by %s", current_user.username)
    return await get_settings(current_user=current_user, db=db)


@router.get("/settings/models", response_model=OpenRouterModelsResponse)
async def list_models(
    current_user: User = Depends(get_current_user),
) -> OpenRouterModelsResponse:
    """Fetch all available models from OpenRouter."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get("https://openrouter.ai/api/v1/models")
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("Failed to fetch OpenRouter models: %s", e)
        # Return a hardcoded fallback list
        return OpenRouterModelsResponse(models=_FALLBACK_MODELS)

    models: list[OpenRouterModel] = []
    for m in data.get("data", []):
        arch = m.get("architecture", {})
        modality = arch.get("modality", "")
        # Filter primarily for text capabilities, although we'll allow mixed modalities
        if "text" in modality or not modality:
            models.append(OpenRouterModel(
                id=m["id"],
                name=m.get("name", m["id"]),
                context_length=m.get("context_length", 0),
            ))

    models.sort(key=lambda x: x.context_length, reverse=True)
    return OpenRouterModelsResponse(models=models)


@router.post("/settings/test-onec")
async def test_onec_connection(
    current_user: User = Depends(require_role("admin")),
) -> dict:
    """Test 1C OData connection: checks $metadata + fetches 1 record."""
    if not _onec_settings.enabled or not _onec_settings.base_url:
        raise HTTPException(status_code=400, detail="1C connection not configured")

    # Validate URL to prevent SSRF (allow_http=True for internal 1C servers)
    try:
        validate_url_safe(_onec_settings.base_url, allow_http=True)
    except SSRFError as e:
        return {"status": "error", "detail": f"URL validation failed: {e}"}

    from matcher.ingestion.onec_adapter import OneCODataClient

    client = OneCODataClient(
        base_url=_onec_settings.base_url,
        username=_onec_settings.username,
        password=_onec_settings.password,
        endpoint=_onec_settings.catalog_endpoint or "/odata/standard.odata/",
    )

    result = await client.health_check()
    if result["status"] == "ok":
        try:
            count = await client.get_total_count()
            result["total_items"] = count
        except Exception:
            pass
        try:
            fields = await client.get_metadata_fields()
            result["available_fields"] = fields[:30]
        except Exception:
            pass

    return result


# ── Fallback model list ─────────────────────────────────────────────────────

_FALLBACK_MODELS = [
    OpenRouterModel(id="openai/gpt-4o", name="OpenAI GPT-4o", context_length=128000),
    OpenRouterModel(id="openai/gpt-4o-mini", name="OpenAI GPT-4o-mini", context_length=128000),
    OpenRouterModel(id="anthropic/claude-3.5-sonnet", name="Anthropic Claude 3.5 Sonnet", context_length=200000),
    OpenRouterModel(id="anthropic/claude-3-haiku", name="Anthropic Claude 3 Haiku", context_length=200000),
    OpenRouterModel(id="google/gemini-1.5-pro", name="Google Gemini 1.5 Pro", context_length=2000000),
    OpenRouterModel(id="google/gemini-1.5-flash", name="Google Gemini 1.5 Flash", context_length=1000000),
    OpenRouterModel(id="meta-llama/llama-3.1-70b-instruct", name="Meta Llama 3.1 70B", context_length=131072),
]
