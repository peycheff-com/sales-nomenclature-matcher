from __future__ import annotations

import re

from matcher.normalization.pipeline import NormalizationContext, load_config


def normalize_units(ctx: NormalizationContext) -> NormalizationContext:
    """Normalize measurement units to standard forms."""
    config = load_config()
    unit_map = config.get("unit_aliases", {})
    text = ctx.text

    detected_unit = None

    # Sort by length descending to match longer patterns first
    sorted_units = sorted(unit_map.keys(), key=len, reverse=True)

    for unit_src in sorted_units:
        # Match unit after a number or as standalone word
        pattern = r"(?<=\d)\s*" + re.escape(unit_src) + r"(?=\s|$|[,;.])"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            normalized = unit_map[unit_src]
            if detected_unit is None:
                detected_unit = normalized
            text = text[: match.start()] + " " + normalized + text[match.end() :]

    # Also check standalone unit words
    for unit_src in sorted_units:
        pattern = r"\b" + re.escape(unit_src) + r"\b"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            normalized = unit_map[unit_src]
            if detected_unit is None:
                detected_unit = normalized
            text = re.sub(pattern, normalized, text, flags=re.IGNORECASE)

    ctx.text = re.sub(r"\s+", " ", text).strip()
    ctx.unit = detected_unit
    return ctx
