from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

from matcher.config import PROVIDER_CAPABILITIES, settings
from matcher.indexing.search import SearchCandidate
from matcher.pipeline.circuit_breaker import provider_circuit
from matcher.pipeline.token_tracker import TokenTracker

logger = logging.getLogger(__name__)


@dataclass
class RerankResult:
    """A reranked candidate with its rerank score."""

    candidate: SearchCandidate
    rerank_score: float


async def rerank_candidates(
    query: str,
    candidates: list[SearchCandidate],
    top_n: int | None = None,
    token_tracker: TokenTracker | None = None,
) -> list[RerankResult]:
    """Rerank candidates using the best available method.

    Priority:
    1. Cohere Rerank API (if cohere_api_key set)
    2. LLM-based reranking via OpenAI/OpenRouter (if llm key set)
    3. Fallback to lexical RRF scores
    """
    top_n = top_n or settings.rerank_top_n

    if not candidates:
        return []

    # Skip reranking if disabled
    if not settings.rerank_enabled:
        logger.debug("Reranking disabled via RERANK_ENABLED=false")
        return _fallback_rerank(candidates, top_n)

    provider_id = settings.rerank_provider
    provider = settings.providers_registry.get(provider_id)
    if not provider:
        logger.warning(
            f"Rerank provider '{provider_id}' not found in registry. Falling back to lexical."
        )
        return _fallback_rerank(candidates, top_n)

    # Circuit breaker: skip provider if it's been failing
    if not provider_circuit.is_available(provider_id):
        logger.warning("Circuit breaker open for rerank provider %s, using fallback", provider_id)
        return _fallback_rerank(candidates, top_n)

    # Verify provider actually supports reranking (skip virtual providers)
    if provider_id not in ("llm-fallback",):
        caps = PROVIDER_CAPABILITIES.get(provider_id)
        if caps and not caps.supports_rerank:
            logger.warning(
                f"Provider '{provider_id}' does not support reranking. Falling back to lexical."
            )
            return _fallback_rerank(candidates, top_n)

    try:
        if provider_id == "llm-fallback":
            if not settings.active_llm_api_key or settings.active_llm_api_key in ("", "none"):
                logger.debug("LLM API key not configured, skipping LLM reranking")
                return _fallback_rerank(candidates, top_n)
            result = await _llm_rerank(query, candidates, top_n, token_tracker=token_tracker)
        elif provider_id == "local":
            result = await _local_rerank(query, candidates, top_n)
        elif provider_id in ("cohere", "together", "jina", "dashscope"):
            result = await _http_rerank(
                query, candidates, top_n, provider_id, provider, token_tracker=token_tracker
            )
        else:
            logger.warning(f"Rerank processor for '{provider_id}' not implemented. Falling back.")
            return _fallback_rerank(candidates, top_n)
        provider_circuit.record_success(provider_id)
        return result
    except Exception as e:
        provider_circuit.record_failure(provider_id)
        logger.error(f"Reranking failed for provider {provider_id}: {e}", exc_info=True)
        return _fallback_rerank(candidates, top_n)


async def _local_rerank(
    query: str,
    candidates: list[SearchCandidate],
    top_n: int,
) -> list[RerankResult]:
    """Rerank using a local HuggingFace CrossEncoder running in-memory."""
    try:
        from sentence_transformers import CrossEncoder
    except ImportError:
        logger.error("sentence-transformers not installed. Cannot use local reranking.")
        return _fallback_rerank(candidates, top_n)

    # Load globally scoped to avoid reloading
    global _local_scorer
    if "_local_scorer" not in globals() or _local_scorer is None:
        model_name = settings.llm_rerank_model or "BAAI/bge-reranker-v2-m3"
        logger.info(f"Loading local CrossEncoder model: {model_name}")
        _local_scorer = CrossEncoder(model_name)

    documents = [_candidate_to_document(c) for c in candidates]
    pairs = [[query, doc] for doc in documents]

    # Predict returns array of logits/scores
    scores = _local_scorer.predict(pairs)

    results = []
    for i, score in enumerate(scores):
        results.append(RerankResult(candidate=candidates[i], rerank_score=float(score)))

    results.sort(key=lambda r: r.rerank_score, reverse=True)
    return results[:top_n]


async def _http_rerank(
    query: str,
    candidates: list[SearchCandidate],
    top_n: int,
    provider_id: str,
    provider_config: dict,
    token_tracker: TokenTracker | None = None,
) -> list[RerankResult]:
    """Rerank using standardized Cohere-like or DashScope HTTP APIs."""
    import httpx

    documents = [_candidate_to_document(c) for c in candidates]
    model = settings.llm_rerank_model or "rerank-multilingual-v3.0"
    base_url = provider_config.get("base_url", "").rstrip("/")
    api_key = provider_config.get("api_key", "")

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    if provider_id == "dashscope":
        endpoint = f"{base_url}/services/aigc/text-rerank/text-rerank"
        payload = {
            "model": model or "gte-rerank",
            "input": {"query": query, "documents": documents},
            "parameters": {"top_n": top_n},
        }
    else:
        # Standard format (Cohere, Together, Jina)
        endpoint = f"{base_url}/rerank" if not base_url.endswith("/rerank") else base_url
        if provider_id == "jina":
            model = model or "jina-reranker-v2-base-multilingual"
        payload = {"model": model, "query": query, "documents": documents, "top_n": top_n}

    async with httpx.AsyncClient() as client:
        resp = await client.post(endpoint, json=payload, headers=headers, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()

    # Token tracking for HTTP rerank APIs
    if token_tracker:
        # Estimate tokens from query + document lengths
        est_tokens = len(query.split()) + sum(len(d.split()) for d in documents)
        billed = data.get("meta", {}).get("billed_units", {})
        token_tracker.record(
            operation="rerank",
            provider=provider_id,
            model=model,
            prompt_tokens=billed.get("search_units", est_tokens),
            total_tokens=billed.get("search_units", est_tokens),
        )

    results = []
    if provider_id == "dashscope":
        items = data.get("output", {}).get("results", [])
        for item in items:
            results.append(
                RerankResult(
                    candidate=candidates[item["index"]], rerank_score=float(item["relevance_score"])
                )
            )
    else:
        items = data.get("results", [])
        for item in items:
            results.append(
                RerankResult(
                    candidate=candidates[item["index"]], rerank_score=float(item["relevance_score"])
                )
            )

    # Normalize rerank scores to [0, 1] range.
    # Some providers (Jina, Together) return raw logits or unbounded scores.
    # Min-max normalize so the scoring formula gets usable values.
    if results and len(results) > 1:
        scores = [r.rerank_score for r in results]
        min_s, max_s = min(scores), max(scores)
        if max_s > min_s:
            for r in results:
                r.rerank_score = (r.rerank_score - min_s) / (max_s - min_s)
        elif max_s > 0:
            # All scores are the same positive value — normalize to 1.0
            for r in results:
                r.rerank_score = 1.0

    return results


async def _llm_rerank(
    query: str,
    candidates: list[SearchCandidate],
    top_n: int,
    token_tracker: TokenTracker | None = None,
) -> list[RerankResult]:
    """Rerank using LLM scoring via OpenAI-compatible API (OpenAI or OpenRouter).

    Asks the LLM to score relevance of top candidates to the query.
    Works with any OpenAI-compatible provider including OpenRouter.
    """
    # Only rerank top candidates to limit cost/latency
    to_rerank = candidates[: min(len(candidates), top_n * 2)]

    model = settings.llm_rerank_model or settings.llm_model

    extra_headers = {}
    if settings.llm_provider == "openrouter":
        extra_headers["HTTP-Referer"] = "https://matcher.internal"
        extra_headers["X-Title"] = "Sales Nomenclature Matcher"

    client = AsyncOpenAI(
        api_key=settings.active_llm_api_key,
        base_url=settings.active_llm_base_url,
        default_headers=extra_headers or None,
    )

    # Build candidate list for the prompt
    candidate_lines = []
    for i, c in enumerate(to_rerank):
        candidate_lines.append(f"{i}: {_candidate_to_document(c)}")
    candidates_text = "\n".join(candidate_lines)

    prompt = f"""Ты — эксперт по сопоставлению товарных номенклатур.

Запрос клиента: "{query}"

Кандидаты из каталога:
{candidates_text}

Оцени релевантность каждого кандидата запросу по шкале от 0.0 до 1.0.
Учитывай: совпадение бренда, модели, числовых характеристик, категории, единиц измерения.

Верни JSON массив объектов с полями "index" и "score", отсортированный по score убыванию.
Только JSON, без пояснений.

Пример: [{{"index": 0, "score": 0.95}}, {{"index": 2, "score": 0.72}}]"""

    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=1024,
        extra_body={"no_thinking": True} if "qwen" in model.lower() else {},
    )

    # Token tracking
    if hasattr(response, "usage") and response.usage and token_tracker:
        token_tracker.record(
            operation="llm_rerank",
            provider=settings.llm_provider,
            model=model,
            prompt_tokens=response.usage.prompt_tokens or 0,
            completion_tokens=response.usage.completion_tokens or 0,
        )

    content = response.choices[0].message.content or "[]"
    # Extract JSON from response (handle markdown code blocks)
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        scores = json.loads(content)
    except json.JSONDecodeError:
        logger.warning(f"LLM rerank returned invalid JSON: {content[:200]}")
        return _fallback_rerank(candidates, top_n)

    # Build results
    results = []
    for item in scores:
        idx = item.get("index", -1)
        score = float(item.get("score", 0))
        if 0 <= idx < len(to_rerank):
            results.append(
                RerankResult(
                    candidate=to_rerank[idx],
                    rerank_score=score,
                )
            )

    # Sort by score descending, take top_n
    results.sort(key=lambda r: r.rerank_score, reverse=True)
    return results[:top_n]


def _candidate_to_document(c: SearchCandidate) -> str:
    """Format a candidate as a document string for the reranker."""
    parts = []
    if c.brand:
        parts.append(c.brand)
    parts.append(c.name)
    if c.article:
        parts.append(c.article)
    if c.category_path:
        parts.append(c.category_path)
    return " | ".join(parts)


def _fallback_rerank(
    candidates: list[SearchCandidate],
    top_n: int,
) -> list[RerankResult]:
    """Fallback: use RRF score as rerank proxy."""
    sorted_candidates = sorted(candidates, key=lambda c: c.rrf_score or 0.0, reverse=True)
    return [
        RerankResult(candidate=c, rerank_score=(c.rrf_score or 0.0))
        for c in sorted_candidates[:top_n]
    ]
