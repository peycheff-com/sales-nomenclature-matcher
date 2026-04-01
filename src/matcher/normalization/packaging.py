"""Normalize packaging terms and extract packaging info."""

from __future__ import annotations

import re

from matcher.normalization.pipeline import NormalizationContext, load_config


def normalize_packaging(ctx: NormalizationContext) -> NormalizationContext:
    """Normalize packaging-related terms and extract packaging info."""
    config = load_config()
    packaging_aliases: dict[str, str] = config.get("packaging_aliases", {})
    packaging_keywords: list[str] = config.get("packaging_keywords", [])

    text = ctx.text

    # Apply packaging aliases (e.g., "упак." -> "упаковка")
    for alias in sorted(packaging_aliases.keys(), key=len, reverse=True):
        pattern = r"(?<!\w)" + re.escape(alias) + r"(?!\w)"
        text = re.sub(pattern, packaging_aliases[alias], text, flags=re.IGNORECASE)

    # Detect packaging type from keywords (word boundary match)
    text_lower = text.lower()
    for keyword in packaging_keywords:
        pattern = r"(?<!\w)" + re.escape(keyword.lower()) + r"(?!\w)"
        if re.search(pattern, text_lower):
            ctx.packaging = keyword
            break

    ctx.text = text
    return ctx
