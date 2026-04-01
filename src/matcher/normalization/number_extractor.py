from __future__ import annotations

import re

from matcher.normalization.pipeline import NormalizationContext, load_config


def extract_numbers(ctx: NormalizationContext) -> NormalizationContext:
    """Extract numbers and dimensions from text."""
    text = ctx.text
    config = load_config()

    # Extract dimensions (e.g., "3x2.5", "100x50x25")
    for pat_str in config.get("dimension_patterns", []):
        for m in re.finditer(pat_str, text):
            dims = [m.group("d1"), m.group("d2")]
            if m.group("d3"):
                dims.append(m.group("d3"))
            ctx.dimensions = [d.replace(",", ".") for d in dims]

    # Normalize comma decimals to dot
    text = re.sub(r'(\d),(\d)', r'\1.\2', text)

    # Extract all numbers
    numbers = []
    for m in re.finditer(r'\d+(?:\.\d+)?', text):
        try:
            numbers.append(float(m.group()))
        except ValueError:
            pass
    ctx.numbers = numbers
    ctx.text = text
    return ctx
