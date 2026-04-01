"""LLM-direct matching: single LLM call replaces retrieval->rerank->scoring."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.config import settings
from matcher.indexing.search import SearchCandidate
from matcher.pipeline.llm_client import clean_json_response, make_llm_client
from matcher.pipeline.token_tracker import TokenTracker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class LLMMatchResult:
    product_id: str | None
    confidence: float
    reasoning: str
    alternatives: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Catalog cache (module-level, worker-process scoped)
# ---------------------------------------------------------------------------

_cached_catalog: list[SearchCandidate] | None = None


async def get_cached_catalog(session: AsyncSession) -> list[SearchCandidate]:
    """Load all active products into memory. Cached after first call."""
    global _cached_catalog
    if _cached_catalog is not None:
        return _cached_catalog

    result = await session.execute(
        text("""
            SELECT product_id, name, normalized_name, article,
                   brand, normalized_brand, manufacturer_code,
                   category_id, category_path, unit, packaging, search_document
            FROM catalog_products
            WHERE is_active = true
            ORDER BY name
        """)
    )
    rows = result.fetchall()
    _cached_catalog = [
        SearchCandidate(
            product_id=row[0],
            name=row[1],
            normalized_name=row[2],
            article=row[3],
            brand=row[4],
            normalized_brand=row[5],
            manufacturer_code=row[6],
            category_id=row[7],
            category_path=row[8],
            unit=row[9],
            packaging=row[10],
            search_document=row[11],
        )
        for row in rows
    ]
    return _cached_catalog


def invalidate_catalog_cache() -> None:
    """Reset the cached catalog. Call after import/reindex."""
    global _cached_catalog
    _cached_catalog = None


# ---------------------------------------------------------------------------
# Prompt formatting
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
Ты — эксперт по сопоставлению товарных номенклатур B2B.

Каталог товаров:
ID | Название | Артикул | Бренд | Ед.изм | Категория
{catalog_table}

Правила:
- confidence >= 0.93: ты уверен что это тот же товар (бренд, модель, характеристики совпадают)
- confidence 0.75-0.92: похожий товар, но есть расхождения (размер, модификация)
- confidence < 0.75: совпадений нет или товар из другой категории
- Разные размеры/модификации одного товара — это confidence 0.80-0.90, не 0.95+
- При неуверенности занижай confidence, а не завышай"""

_USER_PROMPT_SINGLE = """\
Запрос поставщика: "{raw_text}"
Нормализованный: "{normalized_text}"
Атрибуты: бренд={brand}, артикул={article}, числа={numbers}, ед.изм={unit}, упаковка={packaging}

Верни JSON: {{"product_id": "...", "confidence": 0.XX, "reasoning": "...", \
"alternatives": [{{"product_id": "...", "confidence": 0.XX, "reasoning": "..."}}]}}
Если совпадений нет: {{"product_id": null, "confidence": 0.0, "reasoning": "...", \
"alternatives": []}}"""

_USER_PROMPT_BATCH = """\
Сопоставь каждый запрос с товаром из каталога:
{items_list}

Верни JSON массив: [{{"item_index": 0, "product_id": "...", "confidence": 0.XX, \
"reasoning": "..."}}, ...]
Если для запроса нет совпадения: {{"item_index": N, "product_id": null, \
"confidence": 0.0, "reasoning": "..."}}"""


def _format_catalog_table(candidates: list[SearchCandidate]) -> str:
    lines = []
    for c in candidates:
        parts = [
            c.product_id,
            c.name,
            c.article or "—",
            c.brand or "—",
            c.unit or "—",
            c.category_path or "—",
        ]
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def _format_attrs(attrs: dict) -> dict:
    return {
        "brand": attrs.get("brand") or "—",
        "article": attrs.get("article") or "—",
        "numbers": ", ".join(str(n) for n in attrs.get("numbers", [])) or "—",
        "unit": attrs.get("unit") or "—",
        "packaging": attrs.get("packaging") or "—",
    }


# ---------------------------------------------------------------------------
# LLM match functions
# ---------------------------------------------------------------------------


async def llm_match(
    raw_text: str,
    normalized_text: str,
    extracted_attrs: dict,
    candidates: list[SearchCandidate],
    token_tracker: TokenTracker | None = None,
) -> LLMMatchResult | None:
    """Match a single item against candidates via one LLM call.

    Returns LLMMatchResult on success, None on any failure.
    """
    model_override = settings.llm_matcher_model or None
    client, model, extra_body = make_llm_client(model_override=model_override)

    catalog_table = _format_catalog_table(candidates)
    system = _SYSTEM_PROMPT.format(catalog_table=catalog_table)
    attrs = _format_attrs(extracted_attrs)
    user = _USER_PROMPT_SINGLE.format(
        raw_text=raw_text,
        normalized_text=normalized_text,
        **attrs,
    )

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            max_tokens=1024,
            extra_body=extra_body or {},
        )
    except Exception as e:
        logger.error("LLM matcher API call failed: %s", e)
        return None

    if hasattr(response, "usage") and response.usage and token_tracker:
        token_tracker.record(
            operation="llm_match",
            provider=settings.llm_provider,
            model=model,
            prompt_tokens=response.usage.prompt_tokens or 0,
            completion_tokens=response.usage.completion_tokens or 0,
        )

    content = response.choices[0].message.content or "{}"
    content = clean_json_response(content)

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("LLM matcher returned invalid JSON: %s", content[:200])
        return None

    return LLMMatchResult(
        product_id=data.get("product_id"),
        confidence=float(data.get("confidence", 0.0)),
        reasoning=data.get("reasoning", ""),
        alternatives=data.get("alternatives", []),
    )


async def llm_match_batch(
    items: list[dict],
    catalog: list[SearchCandidate],
    token_tracker: TokenTracker | None = None,
) -> list[LLMMatchResult | None]:
    """Match multiple items in batched LLM calls. Falls back to single calls."""
    batch_size = settings.llm_matcher_batch_size
    results: list[LLMMatchResult | None] = [None] * len(items)

    model_override = settings.llm_matcher_model or None
    catalog_table = _format_catalog_table(catalog)
    system = _SYSTEM_PROMPT.format(catalog_table=catalog_table)

    for batch_start in range(0, len(items), batch_size):
        batch = items[batch_start : batch_start + batch_size]
        batch_indices = list(range(batch_start, batch_start + len(batch)))

        items_lines = []
        for i, item in enumerate(batch):
            attrs = _format_attrs(item.get("extracted_attrs", {}))
            items_lines.append(
                f'{i}. "{item["raw_text"]}" '
                f"(бренд={attrs['brand']}, артикул={attrs['article']}, "
                f"числа={attrs['numbers']}, ед.изм={attrs['unit']})"
            )
        user = _USER_PROMPT_BATCH.format(items_list="\n".join(items_lines))

        client, model, extra_body = make_llm_client(model_override=model_override)

        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.0,
                max_tokens=2048,
                extra_body=extra_body or {},
            )

            if hasattr(response, "usage") and response.usage and token_tracker:
                token_tracker.record(
                    operation="llm_match",
                    provider=settings.llm_provider,
                    model=model,
                    prompt_tokens=response.usage.prompt_tokens or 0,
                    completion_tokens=response.usage.completion_tokens or 0,
                )

            content = response.choices[0].message.content or "[]"
            content = clean_json_response(content)
            data = json.loads(content)

            if isinstance(data, list):
                for entry in data:
                    idx = entry.get("item_index", -1)
                    if 0 <= idx < len(batch):
                        results[batch_indices[idx]] = LLMMatchResult(
                            product_id=entry.get("product_id"),
                            confidence=float(entry.get("confidence", 0.0)),
                            reasoning=entry.get("reasoning", ""),
                            alternatives=entry.get("alternatives", []),
                        )
        except Exception as e:
            logger.warning("Batch LLM match failed at %d: %s", batch_start, e)

        # Fallback: items without results get individual calls
        for i, global_idx in enumerate(batch_indices):
            if results[global_idx] is None:
                item = batch[i]
                results[global_idx] = await llm_match(
                    raw_text=item["raw_text"],
                    normalized_text=item.get("normalized_text", item["raw_text"]),
                    extracted_attrs=item.get("extracted_attrs", {}),
                    candidates=catalog,
                    token_tracker=token_tracker,
                )

    return results
