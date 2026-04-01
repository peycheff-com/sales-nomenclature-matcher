"""Apply DB-driven synonyms to a normalization context.

This module bridges the sync normalization pipeline with async DB lookups,
applying global and supplier-specific synonym replacements after the
YAML-based pipeline has run.
"""

from __future__ import annotations

import re

from matcher.db.repos.synonym import SynonymRepo
from matcher.normalization.pipeline import NormalizationContext


async def apply_db_synonyms(
    ctx: NormalizationContext,
    synonym_repo: SynonymRepo,
    supplier_id: str | None = None,
    synonym_map: dict[str, str] | None = None,
) -> NormalizationContext:
    """Apply DB-driven synonym replacements to normalized text.

    Loads global synonyms and supplier-specific overrides, then applies
    replacements sorted by length descending (longest match first) to
    avoid partial-match issues.

    If ``synonym_map`` is provided, the DB query is skipped and the
    pre-built map is used directly (useful for caching across a batch).
    """
    if synonym_map is None:
        synonym_map = await synonym_repo.build_synonym_map(supplier_id=supplier_id)
    if not synonym_map:
        return ctx

    text = ctx.text
    # Sort by source length descending — longest match first
    sorted_sources = sorted(synonym_map.keys(), key=len, reverse=True)
    applied: list[str] = []

    for source in sorted_sources:
        pattern = r"(?<!\w)" + re.escape(source) + r"(?!\w)"
        new_text = re.sub(pattern, synonym_map[source], text, flags=re.IGNORECASE)
        if new_text != text:
            text = new_text
            applied.append(f"{source}->{synonym_map[source]}")

    if applied:
        ctx.text = text
        ctx.extras["db_synonyms_applied"] = applied

    return ctx
