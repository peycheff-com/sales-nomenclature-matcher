"""Settings API -- runtime configuration for models, 1C, thresholds."""
from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator

from matcher.auth.deps import get_current_user, require_role
from matcher.config import settings
from matcher.db.models import User
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


class SettingsResponse(BaseModel):
    # Provider
    llm_provider: str
    embedding_provider: str
    # Models
    llm_model: str
    llm_rerank_model: str
    embedding_model: str
    embedding_dimensions: int
    # API Keys (masked)
    openrouter_api_key_set: bool
    openai_api_key_set: bool
    cohere_api_key_set: bool
    # Thresholds
    auto_match_threshold: float
    review_threshold: float
    retrieval_top_n: int
    rerank_top_n: int
    # 1C Connection
    onec: OneCConnectionSettings


class SettingsUpdateInput(BaseModel):
    llm_provider: str | None = None
    embedding_provider: str | None = None
    llm_model: str | None = None
    llm_rerank_model: str | None = None
    embedding_model: str | None = None
    embedding_dimensions: int | None = None
    openrouter_api_key: str | None = None
    openai_api_key: str | None = None
    cohere_api_key: str | None = None
    auto_match_threshold: float | None = None
    review_threshold: float | None = None
    retrieval_top_n: int | None = None
    rerank_top_n: int | None = None
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


class FreeModel(BaseModel):
    id: str
    name: str
    context_length: int


class FreeModelsResponse(BaseModel):
    models: list[FreeModel]


# ── In-memory 1C settings (persisted to env in production) ───────────────────

_onec_settings = OneCConnectionSettings()


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/settings", response_model=SettingsResponse)
async def get_settings(
    current_user: User = Depends(require_role("admin")),
) -> SettingsResponse:
    """Get current runtime settings."""
    return SettingsResponse(
        llm_provider=settings.llm_provider,
        embedding_provider=settings.embedding_provider,
        llm_model=settings.llm_model,
        llm_rerank_model=settings.llm_rerank_model,
        embedding_model=settings.embedding_model,
        embedding_dimensions=settings.embedding_dimensions,
        openrouter_api_key_set=bool(
            settings.openrouter_api_key
            and settings.openrouter_api_key not in ("", "sk-your-key-here")
        ),
        openai_api_key_set=bool(
            settings.openai_api_key
            and settings.openai_api_key not in ("", "sk-your-key-here")
        ),
        cohere_api_key_set=bool(
            settings.cohere_api_key
            and settings.cohere_api_key not in ("", "your-key-here")
        ),
        auto_match_threshold=settings.auto_match_threshold,
        review_threshold=settings.review_threshold,
        retrieval_top_n=settings.retrieval_top_n,
        rerank_top_n=settings.rerank_top_n,
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
) -> SettingsResponse:
    """Update runtime settings. Only provided fields are updated."""
    global _onec_settings

    if body.llm_provider is not None:
        settings.llm_provider = body.llm_provider
    if body.embedding_provider is not None:
        settings.embedding_provider = body.embedding_provider
    if body.llm_model is not None:
        settings.llm_model = body.llm_model
    if body.llm_rerank_model is not None:
        settings.llm_rerank_model = body.llm_rerank_model
    if body.embedding_model is not None:
        settings.embedding_model = body.embedding_model
    if body.embedding_dimensions is not None:
        settings.embedding_dimensions = body.embedding_dimensions
    if body.openrouter_api_key is not None:
        settings.openrouter_api_key = body.openrouter_api_key
    if body.openai_api_key is not None:
        settings.openai_api_key = body.openai_api_key
    if body.cohere_api_key is not None:
        settings.cohere_api_key = body.cohere_api_key
    if body.auto_match_threshold is not None:
        settings.auto_match_threshold = body.auto_match_threshold
    if body.review_threshold is not None:
        settings.review_threshold = body.review_threshold
    if body.retrieval_top_n is not None:
        settings.retrieval_top_n = body.retrieval_top_n
    if body.rerank_top_n is not None:
        settings.rerank_top_n = body.rerank_top_n
    if body.onec is not None:
        _onec_settings = body.onec

    # Reset cached embedding client when provider/key changes
    if any([body.embedding_provider, body.openrouter_api_key, body.openai_api_key]):
        from matcher.indexing.embedder import reset_client
        reset_client()

    logger.info("Settings updated by %s", current_user.username)
    return await get_settings(current_user=current_user)


@router.get("/settings/free-models", response_model=FreeModelsResponse)
async def list_free_models(
    current_user: User = Depends(get_current_user),
) -> FreeModelsResponse:
    """Fetch currently available free models from OpenRouter."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get("https://openrouter.ai/api/v1/models")
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("Failed to fetch OpenRouter models: %s", e)
        # Return a hardcoded fallback list
        return FreeModelsResponse(models=_FALLBACK_FREE_MODELS)

    free: list[FreeModel] = []
    for m in data.get("data", []):
        pricing = m.get("pricing", {})
        prompt_price = float(pricing.get("prompt", "1") or "1")
        completion_price = float(pricing.get("completion", "1") or "1")
        arch = m.get("architecture", {})
        modality = arch.get("modality", "")

        # Only include free text→text models (skip audio/image-only)
        if prompt_price == 0 and completion_price == 0 and "text" in modality:
            free.append(FreeModel(
                id=m["id"],
                name=m.get("name", m["id"]),
                context_length=m.get("context_length", 0),
            ))

    free.sort(key=lambda x: x.context_length, reverse=True)
    return FreeModelsResponse(models=free)


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

_FALLBACK_FREE_MODELS = [
    FreeModel(id="qwen/qwen3.6-plus-preview:free", name="Qwen 3.6 Plus Preview", context_length=1000000),
    FreeModel(id="qwen/qwen3-coder:free", name="Qwen 3 Coder 480B", context_length=262000),
    FreeModel(id="nvidia/nemotron-3-super-120b-a12b:free", name="NVIDIA Nemotron 3 Super", context_length=262144),
    FreeModel(id="meta-llama/llama-3.3-70b-instruct:free", name="Llama 3.3 70B Instruct", context_length=65536),
    FreeModel(id="google/gemma-3-27b-it:free", name="Google Gemma 3 27B", context_length=131072),
    FreeModel(id="nousresearch/hermes-3-llama-3.1-405b:free", name="Nous Hermes 3 405B", context_length=131072),
    FreeModel(id="stepfun/step-3.5-flash:free", name="StepFun Step 3.5 Flash", context_length=256000),
    FreeModel(id="minimax/minimax-m2.5:free", name="MiniMax M2.5", context_length=196608),
    FreeModel(id="openai/gpt-oss-120b:free", name="OpenAI GPT-OSS 120B", context_length=131072),
]
