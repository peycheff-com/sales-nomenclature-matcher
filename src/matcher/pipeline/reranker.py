from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

from matcher.config import settings
from matcher.indexing.search import SearchCandidate

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

    # Try Cohere first
    if settings.cohere_api_key and settings.cohere_api_key != "your-key-here":
        try:
            return await _cohere_rerank(query, candidates, top_n)
        except Exception as e:
            logger.warning(f"Cohere rerank failed: {e}")

    # Try LLM-based reranking
    llm_key = settings.active_llm_api_key
    if llm_key and llm_key not in ("", "sk-your-key-here", "your-key-here"):
        try:
            return await _llm_rerank(query, candidates, top_n)
        except Exception as e:
            logger.warning(f"LLM rerank failed: {e}")

    # Fallback
    logger.info("No reranker available, using lexical scores as proxy")
    return _fallback_rerank(candidates, top_n)


async def _cohere_rerank(
    query: str,
    candidates: list[SearchCandidate],
    top_n: int,
) -> list[RerankResult]:
    """Rerank using Cohere Rerank API."""
    import cohere

    client = cohere.AsyncClientV2(api_key=settings.cohere_api_key)
    documents = [_candidate_to_document(c) for c in candidates]

    response = await client.rerank(
        query=query,
        documents=documents,
        model="rerank-multilingual-v3.0",
        top_n=top_n,
    )

    results = []
    for item in response.results:
        results.append(RerankResult(
            candidate=candidates[item.index],
            rerank_score=item.relevance_score,
        ))
    return results


async def _llm_rerank(
    query: str,
    candidates: list[SearchCandidate],
    top_n: int,
) -> list[RerankResult]:
    """Rerank using LLM scoring via OpenAI-compatible API (OpenAI or OpenRouter).

    Asks the LLM to score relevance of top candidates to the query.
    Works with any OpenAI-compatible provider including OpenRouter.
    """
    # Only rerank top candidates to limit cost/latency
    to_rerank = candidates[:min(len(candidates), top_n * 2)]

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
            results.append(RerankResult(
                candidate=to_rerank[idx],
                rerank_score=score,
            ))

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
    sorted_candidates = sorted(candidates, key=lambda c: c.rrf_score, reverse=True)
    return [
        RerankResult(candidate=c, rerank_score=c.rrf_score)
        for c in sorted_candidates[:top_n]
    ]
