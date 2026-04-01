#!/usr/bin/env python3
"""CLI script to import catalog from CSV/XLSX file."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from matcher.config import settings
from matcher.ingestion.file_adapter import parse_file
from matcher.ingestion.transformer import transform_item


async def main(file_path: str, dry_run: bool = False) -> None:
    raw_items = parse_file(file_path)
    print(f"Parsed {len(raw_items)} items from {file_path}")

    transformed = []
    errors = 0
    for raw in raw_items:
        try:
            item = transform_item(raw)
            transformed.append(item)
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  Error transforming '{raw.name}': {e}")

    print(f"Transformed: {len(transformed)}, Errors: {errors}")

    if dry_run:
        print("Dry run — not writing to database")
        for item in transformed[:5]:
            print(f"  {item['product_id']}: {item['name']} -> {item['normalized_name']}")
            if item.get("normalized_brand"):
                print(f"    brand: {item['normalized_brand']}")
        return

    # Insert into database
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(settings.async_database_url)
    async with engine.begin() as conn:
        for item in transformed:
            await conn.execute(
                text("""
                    INSERT INTO catalog_products (
                        product_id, onec_ref, code, article, name, full_name,
                        normalized_name, normalized_full_name, brand, normalized_brand,
                        manufacturer, manufacturer_code, category_id, category_path,
                        unit, packaging, size_value, size_unit, weight_value, weight_unit,
                        volume_value, volume_unit, attributes_json, search_document,
                        is_active, source_hash
                    ) VALUES (
                        :product_id, :onec_ref, :code, :article, :name, :full_name,
                        :normalized_name, :normalized_full_name, :brand, :normalized_brand,
                        :manufacturer, :manufacturer_code, :category_id, :category_path,
                        :unit, :packaging, :size_value, :size_unit, :weight_value, :weight_unit,
                        :volume_value, :volume_unit, :attributes_json, :search_document,
                        :is_active, :source_hash
                    )
                    ON CONFLICT (product_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        normalized_name = EXCLUDED.normalized_name,
                        article = EXCLUDED.article,
                        brand = EXCLUDED.brand,
                        normalized_brand = EXCLUDED.normalized_brand,
                        search_document = EXCLUDED.search_document,
                        source_hash = EXCLUDED.source_hash,
                        updated_at = now()
                """),
                {**item, "attributes_json": str(item["attributes_json"])},
            )
    await engine.dispose()
    print(f"Imported {len(transformed)} items to database")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import catalog from CSV/XLSX")
    parser.add_argument("file", help="Path to CSV or XLSX file")
    parser.add_argument("--dry-run", action="store_true", help="Parse and transform only")
    args = parser.parse_args()
    asyncio.run(main(args.file, args.dry_run))
