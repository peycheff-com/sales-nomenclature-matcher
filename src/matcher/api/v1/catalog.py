from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.api.deps import get_arq_pool, get_db
from matcher.auth.deps import get_current_user, require_role
from matcher.db.models import User
from matcher.db.repos.catalog import CatalogRepo
from matcher.schemas.catalog import CatalogImportInput, CatalogReindexInput, JobAccepted


class CatalogProductOut(BaseModel):
    product_id: str
    name: str
    article: str | None = None
    brand: str | None = None
    category_path: str | None = None
    is_active: bool


class CatalogStats(BaseModel):
    total_products: int
    onec_connected: bool


router = APIRouter(tags=["Catalog"])


@router.get("/catalog/products", response_model=list[CatalogProductOut])
async def search_catalog_products(
    q: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search active products by name, article, or brand."""
    repo = CatalogRepo(db)
    products = await repo.search_products(query=q, limit=limit)
    return [
        CatalogProductOut(
            product_id=p.product_id,
            name=p.name,
            article=p.article,
            brand=p.brand,
            category_path=p.category_path,
            is_active=p.is_active,
        )
        for p in products
    ]


@router.get("/catalog/stats", response_model=CatalogStats)
async def catalog_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get catalog statistics and 1C connection status."""
    repo = CatalogRepo(db)
    total = await repo.count_active()

    from matcher.api.v1.settings import _onec_settings

    onec_connected = bool(_onec_settings.enabled and _onec_settings.base_url)

    return CatalogStats(total_products=total, onec_connected=onec_connected)


@router.post("/catalog/import", response_model=JobAccepted, status_code=202)
async def import_catalog(
    body: CatalogImportInput,
    arq_pool=Depends(get_arq_pool),
    current_user: User = Depends(require_role("admin", "operator")),
):
    """Import catalog from 1C OData or file URL."""
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    await arq_pool.enqueue_job(
        "catalog_import",
        job_id,
        source_type=body.source_type,
        file_url=body.file_url,
        dry_run=body.dry_run,
        source_version=body.source_version,
    )
    return JobAccepted(job_id=job_id, status="queued")


@router.post("/catalog/upload", response_model=JobAccepted, status_code=202)
async def upload_catalog_file(
    file: UploadFile = File(...),
    arq_pool=Depends(get_arq_pool),
    current_user: User = Depends(require_role("admin", "operator")),
):
    """Upload a CSV/XLSX catalog file directly and enqueue import."""
    from fastapi import HTTPException

    MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".csv", ".xlsx"):
        raise HTTPException(status_code=400, detail="Only .csv and .xlsx files are supported")

    source_type = "xlsx" if suffix == ".xlsx" else "csv"

    # Read file with size limit to prevent resource exhaustion
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size is {MAX_UPLOAD_SIZE // (1024 * 1024)} MB",
        )

    # Validate file content matches expected type
    if source_type == "xlsx" and len(content) >= 4:
        if content[:4] != b"\x50\x4b\x03\x04":
            raise HTTPException(status_code=400, detail="File content does not match .xlsx format.")

    # Save uploaded file to temp directory
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False, dir="/tmp") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    await arq_pool.enqueue_job(
        "catalog_import",
        job_id,
        source_type=source_type,
        file_path=tmp_path,
    )
    return JobAccepted(job_id=job_id, status="queued")


@router.post("/catalog/reindex", response_model=JobAccepted, status_code=202)
async def reindex_catalog(
    body: CatalogReindexInput,
    arq_pool=Depends(get_arq_pool),
    current_user: User = Depends(require_role("admin")),
):
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    await arq_pool.enqueue_job(
        "catalog_reindex",
        job_id,
        **body.model_dump(exclude_none=True),
    )
    return JobAccepted(job_id=job_id, status="queued")


@router.delete("/catalog/products/{product_id}", status_code=204)
async def delete_catalog_product(
    product_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "operator")),
):
    """Delete a single catalog product by ID."""
    repo = CatalogRepo(db)
    deleted = await repo.delete_product(product_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Product not found")
    await db.commit()
    return None
