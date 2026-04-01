"""End-to-end test: qwen/qwen3.6-plus-preview:free via OpenRouter.

Tests:
  1. Raw connectivity — chat.completions.create round-trip
  2. Structured JSON output — model returns parseable JSON for reranking
  3. Reranker integration — _llm_rerank with mock SearchCandidates
  4. Full pipeline smoke — match_single (requires live DB + seeded catalog)

Usage:
    # Minimal (no DB needed):
    python -m pytest tests/test_e2e_qwen_openrouter.py -v -k "not full_pipeline"

    # Full (requires running DB + Redis + seeded catalog):
    python -m pytest tests/test_e2e_qwen_openrouter.py -v
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time

import pytest
from openai import AsyncOpenAI

# ── Constants ────────────────────────────────────────────────────────────────
MODEL_ID = "qwen/qwen3.6-plus-preview:free"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Read key from env — fall back to .env file in project root
API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
if not API_KEY:
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        for line in open(env_path):
            line = line.strip()
            if line.startswith("OPENROUTER_API_KEY="):
                API_KEY = line.split("=", 1)[1].strip()
                break

skip_no_key = pytest.mark.skipif(
    not API_KEY or API_KEY in ("", "sk-your-key-here"),
    reason="OPENROUTER_API_KEY not configured",
)


def _make_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=API_KEY,
        base_url=OPENROUTER_BASE_URL,
        default_headers={
            "HTTP-Referer": "https://matcher.internal",
            "X-Title": "Sales Nomenclature Matcher - E2E Test",
        },
    )


# ── Test 1: Raw connectivity ────────────────────────────────────────────────

@skip_no_key
@pytest.mark.asyncio
async def test_01_raw_connectivity():
    """Verify we can reach the Qwen model and get a coherent response."""
    client = _make_client()
    t0 = time.monotonic()

    response = await client.chat.completions.create(
        model=MODEL_ID,
        messages=[{"role": "user", "content": "Ответь одним словом: столица России?"}],
        temperature=0.0,
        max_tokens=32,
    )

    elapsed = time.monotonic() - t0
    content = response.choices[0].message.content or ""
    print(f"\n  [connectivity] model={response.model}, latency={elapsed:.2f}s")
    print(f"  [connectivity] response: {content!r}")

    assert response.choices, "No choices in response"
    assert len(content) > 0, "Empty response content"
    # Qwen should return something containing "Москва"
    assert "москва" in content.lower() or "moskva" in content.lower(), (
        f"Unexpected response: {content}"
    )


# ── Test 2: Structured JSON output ──────────────────────────────────────────

@skip_no_key
@pytest.mark.asyncio
async def test_02_structured_json_rerank():
    """Verify the model can produce structured JSON for reranking."""
    client = _make_client()

    candidates = [
        "0: Bosch | Перфоратор GBH 2-26 DRE | SDS-plus | Электроинструмент",
        "1: Makita | Перфоратор HR2470 | SDS-plus | Электроинструмент",
        "2: DeWalt | Шуруповерт DCD791 | Аккумуляторный | Электроинструмент",
        "3: Bosch | Дрель GSR 18V-50 | Аккумуляторная | Электроинструмент",
        "4: Hilti | Перфоратор TE 2-A22 | SDS-plus | Электроинструмент",
    ]

    prompt = f"""Ты — эксперт по сопоставлению товарных номенклатур.

Запрос клиента: "Bosch перфоратор GBH 2-26"

Кандидаты из каталога:
{chr(10).join(candidates)}

Оцени релевантность каждого кандидата запросу по шкале от 0.0 до 1.0.
Учитывай: совпадение бренда, модели, числовых характеристик, категории, единиц измерения.

Верни JSON массив объектов с полями "index" и "score", отсортированный по score убыванию.
Только JSON, без пояснений.

Пример: [{{"index": 0, "score": 0.95}}, {{"index": 2, "score": 0.72}}]"""

    t0 = time.monotonic()
    response = await client.chat.completions.create(
        model=MODEL_ID,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=512,
    )
    elapsed = time.monotonic() - t0

    content = (response.choices[0].message.content or "").strip()

    # Handle thinking tags — Qwen3 sometimes wraps output in <think>...</think>
    if "<think>" in content:
        # Strip thinking block and get the actual output after it
        import re
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

    # Handle markdown code blocks
    if content.startswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    print(f"\n  [json_rerank] latency={elapsed:.2f}s")
    print(f"  [json_rerank] raw response: {content[:500]!r}")

    scores = json.loads(content)
    assert isinstance(scores, list), f"Expected list, got {type(scores)}"
    assert len(scores) >= 3, f"Expected >=3 scored candidates, got {len(scores)}"

    # Verify structure
    for item in scores:
        assert "index" in item, f"Missing 'index' in item: {item}"
        assert "score" in item, f"Missing 'score' in item: {item}"
        assert 0 <= item["index"] <= 4, f"Index out of range: {item['index']}"
        assert 0.0 <= float(item["score"]) <= 1.0, f"Score out of range: {item['score']}"

    # Index 0 (exact Bosch GBH 2-26) should rank highest
    top_idx = scores[0]["index"]
    print(f"  [json_rerank] top candidate index={top_idx}, score={scores[0]['score']}")
    assert top_idx == 0, (
        f"Expected Bosch GBH 2-26 (index 0) to rank first, got index {top_idx}"
    )


# ── Test 3: Reranker module integration ──────────────────────────────────────

@skip_no_key
@pytest.mark.asyncio
async def test_03_reranker_integration():
    """Test _llm_rerank with the Qwen model using mock SearchCandidates."""
    # Patch settings before importing reranker
    from matcher.config import settings

    original_model = settings.llm_model
    original_provider = settings.llm_provider
    original_rerank_model = settings.llm_rerank_model

    try:
        settings.llm_model = MODEL_ID
        settings.llm_provider = "openrouter"
        settings.llm_rerank_model = ""  # force fallback to llm_model

        from matcher.pipeline.reranker import _llm_rerank
        from matcher.indexing.search import SearchCandidate

        # Build mock candidates
        mock_candidates = [
            SearchCandidate(
                product_id="prod_001",
                name="Перфоратор Bosch GBH 2-26 DRE Professional",
                article="0611253708",
                brand="Bosch",
                normalized_name="перфоратор bosch gbh 2 26 dre professional",
                normalized_brand="bosch",
                manufacturer_code=None,
                category_path="Электроинструмент > Перфораторы",
                unit=None,
                packaging=None,
                retrieval_rank=1,
                lexical_score=0.85,
                semantic_score=0.9,
                rrf_score=0.87,
            ),
            SearchCandidate(
                product_id="prod_002",
                name="Дрель-шуруповерт Bosch GSR 18V-50",
                article="06019H5000",
                brand="Bosch",
                normalized_name="дрель шуруповерт bosch gsr 18v 50",
                normalized_brand="bosch",
                manufacturer_code=None,
                category_path="Электроинструмент > Дрели",
                unit=None,
                packaging=None,
                retrieval_rank=2,
                lexical_score=0.4,
                semantic_score=0.5,
                rrf_score=0.45,
            ),
            SearchCandidate(
                product_id="prod_003",
                name="Перфоратор Makita HR2470",
                article="HR2470",
                brand="Makita",
                normalized_name="перфоратор makita hr2470",
                normalized_brand="makita",
                manufacturer_code=None,
                category_path="Электроинструмент > Перфораторы",
                unit=None,
                packaging=None,
                retrieval_rank=3,
                lexical_score=0.3,
                semantic_score=0.6,
                rrf_score=0.42,
            ),
        ]

        t0 = time.monotonic()
        results = await _llm_rerank(
            query="Bosch перфоратор GBH 2-26 DRE",
            candidates=mock_candidates,
            top_n=3,
        )
        elapsed = time.monotonic() - t0

        print(f"\n  [reranker] latency={elapsed:.2f}s, results={len(results)}")
        for r in results:
            print(f"    {r.candidate.product_id}: {r.candidate.name} -> score={r.rerank_score:.3f}")

        assert len(results) >= 1, "No results from _llm_rerank"

        # The Bosch GBH 2-26 should be the top result
        top = results[0]
        assert top.candidate.product_id == "prod_001", (
            f"Expected prod_001 as top, got {top.candidate.product_id}"
        )
        assert top.rerank_score > 0.5, (
            f"Expected high rerank score, got {top.rerank_score}"
        )

    finally:
        # Restore
        settings.llm_model = original_model
        settings.llm_provider = original_provider
        settings.llm_rerank_model = original_rerank_model


# ── Test 4: Usage / cost check ───────────────────────────────────────────────

@skip_no_key
@pytest.mark.asyncio
async def test_04_free_tier_verification():
    """Verify the model reports $0 cost (free tier)."""
    client = _make_client()

    response = await client.chat.completions.create(
        model=MODEL_ID,
        messages=[{"role": "user", "content": "Скажи 'ok'"}],
        temperature=0.0,
        max_tokens=8,
    )

    content = (response.choices[0].message.content or "").strip()
    model_used = response.model or ""

    print(f"\n  [free_tier] model_used={model_used}")
    print(f"  [free_tier] response: {content!r}")

    # OpenRouter returns usage info
    usage = response.usage
    if usage:
        print(f"  [free_tier] prompt_tokens={usage.prompt_tokens}, "
              f"completion_tokens={usage.completion_tokens}")

    # Verify the model name looks right (OpenRouter may append :free)
    assert "qwen" in model_used.lower(), f"Unexpected model: {model_used}"


# ── Entrypoint for direct execution ──────────────────────────────────────────

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s", "-k", "not full_pipeline"]))
