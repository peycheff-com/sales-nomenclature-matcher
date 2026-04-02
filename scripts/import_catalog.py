#!/usr/bin/env python3
"""CLI script to import catalog from CSV/XLSX file."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from matcher.db.engine import async_session_factory
from matcher.db.repos.catalog import CatalogRepo
from matcher.ingestion.file_adapter import parse_file
from matcher.ingestion.transformer import transform_item


async def load_catalog_products(file_path: str) -> tuple[list[dict], int]:
    raw_items = parse_file(file_path)
    print(f"Parsed {len(raw_items)} items from {file_path}")
    if not raw_items:
        raise RuntimeError("Catalog import produced 0 rows")

    transformed: list[dict] = []
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
    if not transformed:
        raise RuntimeError("Catalog import produced 0 valid products")
    return transformed, errors


async def import_catalog_file(file_path: str) -> tuple[int, int]:
    transformed, errors = await load_catalog_products(file_path)
    async with async_session_factory() as session:
        repo = CatalogRepo(session)
        affected = await repo.upsert_products(transformed)
        await session.commit()
    return affected, errors


async def main(file_path: str, dry_run: bool = False) -> None:
    transformed, errors = await load_catalog_products(file_path)

    if dry_run:
        print("Dry run — not writing to database")
        for item in transformed[:5]:
            print(f"  {item['product_id']}: {item['name']} -> {item['normalized_name']}")
            if item.get("normalized_brand"):
                print(f"    brand: {item['normalized_brand']}")
        return

    affected, _ = await import_catalog_file(file_path)
    print(f"Imported {affected} items to database")
    if errors:
        print(f"Completed with {errors} transformation errors")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import catalog from CSV/XLSX")
    parser.add_argument("file", help="Path to CSV or XLSX file")
    parser.add_argument("--dry-run", action="store_true", help="Parse and transform only")
    args = parser.parse_args()
    asyncio.run(main(args.file, args.dry_run))
