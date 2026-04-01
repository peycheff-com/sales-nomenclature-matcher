"""Expand common Russian abbreviations in product nomenclature."""

from __future__ import annotations

import re

from matcher.normalization.pipeline import NormalizationContext, load_config


def expand_abbreviations(ctx: NormalizationContext) -> NormalizationContext:
    """Expand known abbreviations in the text."""
    config = load_config()
    abbr_map: dict[str, str] = config.get("abbreviations", {})

    if not abbr_map:
        return ctx

    text = ctx.text
    # Sort by length descending to match longest abbreviations first
    for abbr in sorted(abbr_map.keys(), key=len, reverse=True):
        # Word-boundary match (case-insensitive)
        pattern = r"(?<!\w)" + re.escape(abbr) + r"(?!\w)"
        text = re.sub(pattern, abbr_map[abbr], text, flags=re.IGNORECASE)

    ctx.text = text
    return ctx
