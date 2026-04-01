from __future__ import annotations

import hashlib
import json

from matcher.ingestion.base import RawCatalogItem
from matcher.normalization.pipeline import run_pipeline


def transform_item(raw: RawCatalogItem) -> dict:
    """Transform a raw catalog item into a dict ready for DB insertion.

    Returns a dict matching catalog_products columns.
    """
    # Run normalization on name
    name_ctx = run_pipeline(raw.name)

    full_name_normalized = None
    if raw.full_name:
        full_ctx = run_pipeline(raw.full_name)
        full_name_normalized = full_ctx.text

    brand_normalized = None
    if raw.brand:
        brand_ctx = run_pipeline(raw.brand)
        brand_normalized = brand_ctx.brand or brand_ctx.text

    # Build search document: concatenation of key fields for FTS/trigram
    search_parts = [raw.name]
    if raw.full_name:
        search_parts.append(raw.full_name)
    if raw.brand:
        search_parts.append(raw.brand)
    if raw.article:
        search_parts.append(raw.article)
    if raw.manufacturer:
        search_parts.append(raw.manufacturer)
    if raw.manufacturer_code:
        search_parts.append(raw.manufacturer_code)
    if raw.category_path:
        search_parts.append(raw.category_path)
    search_document = " | ".join(search_parts)

    # Source hash for idempotent imports
    hash_input = json.dumps(
        {
            "name": raw.name,
            "article": raw.article,
            "brand": raw.brand,
            "code": raw.code,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    source_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    # Deterministic product_id from source_hash for file imports — prevents duplicates.
    # 1C imports keep their native UUID (onec_ref) as product_id.
    product_id = raw.product_id
    if not raw.onec_ref and (not product_id or product_id.startswith("prd_")):
        product_id = f"prd_{source_hash}"

    return {
        "product_id": product_id,
        "onec_ref": raw.onec_ref,
        "code": raw.code,
        "article": raw.article,
        "name": raw.name,
        "full_name": raw.full_name,
        "normalized_name": name_ctx.text,
        "normalized_full_name": full_name_normalized,
        "brand": raw.brand,
        "normalized_brand": brand_normalized,
        "manufacturer": raw.manufacturer,
        "manufacturer_code": raw.manufacturer_code,
        "category_id": raw.category_id,
        "category_path": raw.category_path,
        "unit": raw.unit,
        "packaging": raw.packaging,
        "size_value": raw.size_value,
        "size_unit": raw.size_unit,
        "weight_value": raw.weight_value,
        "weight_unit": raw.weight_unit,
        "volume_value": raw.volume_value,
        "volume_unit": raw.volume_unit,
        "attributes_json": raw.attributes or {},
        "search_document": search_document,
        "is_active": True,
        "source_hash": source_hash,
    }
