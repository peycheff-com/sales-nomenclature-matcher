#!/usr/bin/env python3
"""Production bootstrap helper for initial catalog/index/supplier preparation."""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import uuid
from pathlib import Path

from sqlalchemy import select, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from matcher.db.engine import async_session_factory  # noqa: E402
from matcher.db.models import IndexVersion  # noqa: E402
from matcher.db.repos.catalog import CatalogRepo  # noqa: E402
from matcher.db.repos.metrics import MetricsRepo  # noqa: E402
from matcher.db.repos.supplier import SupplierRepo  # noqa: E402
from matcher.indexing.indexer import reindex_catalog  # noqa: E402
from scripts.import_catalog import import_catalog_file  # noqa: E402


def _supplier_id_for(name: str, ordinal: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        slug = f"bootstrap-{ordinal:02d}"
    return f"sup_{slug[:48]}"


async def _save_quality_baseline() -> str:
    async with async_session_factory() as session:
        metrics_repo = MetricsRepo(session)
        metrics = await metrics_repo.compute_quality_metrics()

        active_index_stmt = select(IndexVersion).where(IndexVersion.is_active == True)  # noqa: E712
        active_index = (await session.execute(active_index_stmt)).scalar_one_or_none()

        report = await metrics_repo.save_quality_report(
            {
                "index_version_id": (
                    active_index.index_version_id if active_index is not None else None
                ),
                "scope": "all",
                "scope_value": None,
                "total_cases": metrics["total_cases"],
                "top1_accuracy": metrics["top1_accuracy"],
                "top3_recall": metrics["top3_recall"],
                "precision_at_1": metrics["precision_at_1"],
                "auto_match_fp_rate": (
                    metrics.get("auto_match_fp_rate")
                    or metrics.get("auto_match_false_positive_rate")
                ),
                "review_acceptance_rate": metrics["review_acceptance_rate"],
                "avg_latency_ms": metrics["avg_latency_ms"],
                "report_json": metrics,
            }
        )
        await session.commit()
        return report.report_id


async def _ensure_suppliers(names: list[str]) -> list[tuple[str, str]]:
    created: list[tuple[str, str]] = []
    if not names:
        return created

    async with async_session_factory() as session:
        repo = SupplierRepo(session)
        suppliers = await repo.list_suppliers(False)
        existing = {supplier.supplier_name.lower(): supplier for supplier in suppliers}
        for ordinal, name in enumerate(names, start=1):
            normalized = name.strip()
            if not normalized:
                continue
            match = existing.get(normalized.lower())
            if match is not None:
                created.append((match.supplier_id, match.supplier_name))
                continue

            supplier_id = _supplier_id_for(normalized, ordinal)
            while await repo.get_supplier(supplier_id) is not None:
                supplier_id = f"{supplier_id}-{uuid.uuid4().hex[:4]}"
            supplier = await repo.create_supplier(supplier_id, normalized)
            created.append((supplier.supplier_id, supplier.supplier_name))

        await session.commit()

    return created


async def _catalog_coverage() -> tuple[int, int]:
    async with async_session_factory() as session:
        total = await CatalogRepo(session).count_active()
        embedded = (
            await session.execute(
                text(
                    """
                    SELECT count(*)
                    FROM catalog_products p
                    JOIN catalog_embeddings e ON e.product_id = p.product_id
                    WHERE p.is_active = true
                    """
                )
            )
        ).scalar() or 0
    return int(total), int(embedded)


async def main(args: argparse.Namespace) -> None:
    if not args.catalog_file.exists():
        raise FileNotFoundError(f"Catalog file not found: {args.catalog_file}")

    affected, errors = await import_catalog_file(str(args.catalog_file))
    print(f"Catalog import complete: affected={affected}, transform_errors={errors}")

    created_suppliers = await _ensure_suppliers(args.supplier or [])
    if created_suppliers:
        print("Suppliers ensured:")
        for supplier_id, supplier_name in created_suppliers:
            print(f"  {supplier_id}: {supplier_name}")

    reindex_result = await reindex_catalog(
        embedding_model=args.embedding_model,
        embedding_version=args.embedding_version,
        batch_size=args.batch_size,
        session_factory=async_session_factory,
    )
    print(f"Reindex complete: {reindex_result}")

    total_products, embedded_products = await _catalog_coverage()
    print(
        "Catalog coverage: "
        f"total_products={total_products}, embedded_products={embedded_products}"
    )
    if total_products == 0 or embedded_products < total_products:
        raise RuntimeError("Bootstrap failed: catalog embeddings are not at 100% coverage")

    if args.save_quality_baseline:
        report_id = await _save_quality_baseline()
        print(f"Saved quality baseline: {report_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Bootstrap production catalog, suppliers, embeddings, and quality baseline."
    )
    parser.add_argument(
        "--catalog-file",
        required=True,
        type=Path,
        help="Path to the master catalog CSV/XLSX file.",
    )
    parser.add_argument(
        "--supplier",
        action="append",
        default=[],
        help="Supplier name to ensure exists. Repeat for multiple suppliers.",
    )
    parser.add_argument(
        "--embedding-model",
        default=None,
        help="Optional embedding model override for reindex.",
    )
    parser.add_argument(
        "--embedding-version",
        default="bootstrap-v1",
        help="Embedding version tag to save in index_versions.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Embedding batch size for reindex.",
    )
    parser.add_argument(
        "--skip-quality-baseline",
        action="store_true",
        help="Skip saving the initial quality report after bootstrap.",
    )
    parsed = parser.parse_args()
    parsed.save_quality_baseline = not parsed.skip_quality_baseline
    asyncio.run(main(parsed))
