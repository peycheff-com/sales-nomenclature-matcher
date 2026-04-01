from __future__ import annotations

import asyncio
import logging
from typing import Sequence

from openai import AsyncOpenAI

from matcher.config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


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

        if not api_key or api_key in ("sk-your-key-here", "your-key-here"):
            raise RuntimeError(
                f"No API key configured for embedding provider '{settings.embedding_provider}'. "
                f"Set {'OPENROUTER_API_KEY' if settings.embedding_provider == 'openrouter' else 'OPENAI_API_KEY'} in .env"
            )

        extra_headers = {}
        if settings.embedding_provider == "openrouter":
            extra_headers["HTTP-Referer"] = "https://matcher.internal"
            extra_headers["X-Title"] = "Sales Nomenclature Matcher"

        _client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers=extra_headers or None,
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
    Returns list of embedding vectors in same order as input texts.
    """
    model = model or settings.embedding_model
    dimensions = dimensions or settings.embedding_dimensions
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
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                wait = 2 ** attempt
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
