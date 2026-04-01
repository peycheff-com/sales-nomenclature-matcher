from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

import httpx
from openai import AsyncOpenAI

from matcher.config import settings
from matcher.pipeline.token_tracker import TokenTracker

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None
_token_tracker: TokenTracker | None = None


def set_token_tracker(tracker: TokenTracker | None) -> None:
    """Set the active token tracker for embedding operations."""
    global _token_tracker
    _token_tracker = tracker


def _get_client() -> AsyncOpenAI:
    """Get an OpenAI-compatible client configured for the active embedding provider."""
    global _client
    if _client is None:
        if settings.embedding_provider == "none":
            raise RuntimeError(
                "Embedding provider is set to 'none'. "
                "Semantic search disabled. Set EMBEDDING_PROVIDER=openai or openrouter to enable."
            )

        api_key = settings.active_embedding_api_key
        base_url = settings.active_embedding_base_url

        if settings.embedding_provider != "local" and (
            not api_key or api_key in ("sk-your-key-here", "your-key-here")
        ):
            raise RuntimeError(
                f"No API key configured for embedding provider '{settings.embedding_provider}'. "
                "Configure it in Settings -> AI Gateway."
            )

        extra_headers = {}
        if settings.embedding_provider == "openrouter":
            extra_headers["HTTP-Referer"] = "https://matcher.internal"
            extra_headers["X-Title"] = "Sales Nomenclature Matcher"

        _client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers=extra_headers or None,
            timeout=httpx.Timeout(60.0, connect=10.0),
        )
        logger.info(
            f"Embedding client initialized: provider={settings.embedding_provider}, "
            f"base_url={base_url}, model={settings.embedding_model}"
        )
    return _client


def reset_client() -> None:
    """Reset the cached client (useful when switching providers)."""
    global _client
    _client = None


async def embed_texts(
    texts: Sequence[str],
    model: str | None = None,
    dimensions: int | None = None,
    batch_size: int = 100,
    max_retries: int = 3,
) -> list[list[float]]:
    """Embed a list of texts using the configured provider (OpenAI or OpenRouter).

    Both providers use the OpenAI-compatible /embeddings endpoint.
    Google uses its own native REST API via batchEmbedContents.
    Returns list of embedding vectors in same order as input texts.
    """
    model = model or settings.embedding_model
    dimensions = dimensions or settings.embedding_dimensions

    if settings.embedding_provider == "google":
        return await _embed_texts_google(texts, model, dimensions, batch_size, max_retries)

    client = _get_client()

    all_embeddings: list[list[float]] = [[] for _ in texts]

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        for attempt in range(max_retries):
            try:
                kwargs: dict = {
                    "input": batch,
                    "model": model,
                }
                # dimensions param is supported by OpenAI and most OpenRouter embedding models
                if dimensions:
                    kwargs["dimensions"] = dimensions

                response = await client.embeddings.create(**kwargs)
                for j, item in enumerate(response.data):
                    all_embeddings[i + j] = item.embedding
                # Token tracking: capture usage if available
                if hasattr(response, "usage") and response.usage and _token_tracker:
                    _token_tracker.record(
                        operation="embed",
                        provider=settings.embedding_provider,
                        model=model,
                        prompt_tokens=getattr(response.usage, "prompt_tokens", 0)
                        or getattr(response.usage, "total_tokens", 0),
                        total_tokens=getattr(response.usage, "total_tokens", 0),
                    )
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                wait = 2**attempt
                logger.warning(
                    f"Embedding batch {i // batch_size} failed (attempt {attempt + 1}): {e}. "
                    f"Retrying in {wait}s"
                )
                await asyncio.sleep(wait)

        # Rate limit: small pause between batches
        if i + batch_size < len(texts):
            await asyncio.sleep(0.1)

    return all_embeddings


async def embed_single(text: str) -> list[float]:
    """Embed a single text string."""
    results = await embed_texts([text])
    return results[0]


async def _embed_texts_google(
    texts: Sequence[str],
    model: str,
    dimensions: int | None,
    batch_size: int,
    max_retries: int,
) -> list[list[float]]:
    import httpx

    api_key = settings.active_embedding_api_key
    if not api_key or api_key in ("your-key-here", ""):
        raise RuntimeError(
            "No API key configured for Google. Configure it in Settings -> AI Gateway."
        )

    # Google's model names often don't have the 'models/' prefix when supplied in configs
    model_name = model if model.startswith("models/") else f"models/{model}"

    batch_url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:batchEmbedContents?key={api_key}"

    all_embeddings: list[list[float]] = [[] for _ in texts]

    async with httpx.AsyncClient() as client:
        # Avoid creating batches larger than API limits (often 100 for gemini embeddings)
        batch_size = min(batch_size, 100)

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]

            requests = []
            for text in batch:
                req = {"model": model_name, "content": {"parts": [{"text": text}]}}
                if dimensions:
                    req["outputDimensionality"] = dimensions
                requests.append(req)

            payload = {"requests": requests}

            for attempt in range(max_retries):
                try:
                    resp = await client.post(batch_url, json=payload, timeout=30.0)
                    resp.raise_for_status()
                    data = resp.json()

                    for j, item in enumerate(data.get("embeddings", [])):
                        all_embeddings[i + j] = item["values"]
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    wait = 2**attempt
                    logger.warning(
                        f"Google Embedding batch {i // batch_size} "
                        f"failed (attempt {attempt + 1}): {e}. "
                        f"Retrying in {wait}s"
                    )
                    await asyncio.sleep(wait)

            if i + batch_size < len(texts):
                await asyncio.sleep(0.5)

    return all_embeddings
