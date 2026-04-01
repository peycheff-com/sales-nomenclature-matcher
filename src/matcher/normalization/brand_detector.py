from __future__ import annotations

from matcher.normalization.pipeline import NormalizationContext, load_config


def detect_brand(ctx: NormalizationContext) -> NormalizationContext:
    """Detect and normalize brand names from text."""
    config = load_config()
    brand_map = config.get("brand_aliases", {})

    text_lower = ctx.text.lower()
    text_lower.split()

    detected_brand = None
    best_match_len = 0

    # Check multi-word brands first, then single-word
    # Sort by key length descending
    sorted_brands = sorted(brand_map.keys(), key=len, reverse=True)

    for brand_src in sorted_brands:
        brand_src_lower = brand_src.lower()
        if brand_src_lower in text_lower:
            if len(brand_src_lower) > best_match_len:
                detected_brand = brand_map[brand_src]
                best_match_len = len(brand_src_lower)
                # Replace in text with normalized form
                ctx.text = ctx.text.lower().replace(brand_src_lower, detected_brand)

    ctx.brand = detected_brand
    return ctx
