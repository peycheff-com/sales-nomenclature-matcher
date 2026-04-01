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
from matcher.db.repos.audit import AuditRepo
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "operator", "catalog_operator")),
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
        _queue_name="catalog",
    )
    audit = AuditRepo(db)
    await audit.log(
        action="catalog_import",
        entity_type="catalog_product",
        user_id=current_user.user_id,
        username=current_user.username,
        details={"source_type": body.source_type, "job_id": job_id, "dry_run": body.dry_run},
    )
    await db.commit()
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
        _queue_name="catalog",
    )
    return JobAccepted(job_id=job_id, status="queued")


@router.post("/catalog/reindex", response_model=JobAccepted, status_code=202)
async def reindex_catalog(
    body: CatalogReindexInput,
    arq_pool=Depends(get_arq_pool),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "catalog_operator")),
):
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    await arq_pool.enqueue_job(
        "catalog_reindex",
        job_id,
        **body.model_dump(exclude_none=True),
        _queue_name="catalog",
    )
    audit = AuditRepo(db)
    await audit.log(
        action="catalog_reindex",
        entity_type="index_version",
        user_id=current_user.user_id,
        username=current_user.username,
        details={"job_id": job_id},
    )
    await db.commit()
    return JobAccepted(job_id=job_id, status="queued")


@router.get("/catalog/index-versions")
async def list_index_versions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all index versions with their status."""
    repo = CatalogRepo(db)
    versions = await repo.list_index_versions()
    return {
        "items": [
            {
                "index_version_id": v.index_version_id,
                "embedding_model": v.embedding_model,
                "embedding_version": v.embedding_version,
                "is_active": v.is_active,
                "product_count": v.product_count,
                "created_by": v.created_by,
                "created_at": v.created_at.isoformat() if v.created_at else None,
                "activated_at": v.activated_at.isoformat() if v.activated_at else None,
            }
            for v in versions
        ]
    }


class RollbackInput(BaseModel):
    index_version_id: str


@router.post("/catalog/rollback", status_code=200)
async def rollback_index(
    body: RollbackInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "catalog_operator")),
):
    """Roll back to a previous index version."""
    repo = CatalogRepo(db)
    success = await repo.activate_index_version(body.index_version_id)
    if not success:
        raise HTTPException(status_code=404, detail="Index version not found")

    audit = AuditRepo(db)
    await audit.log(
        action="index_rollback",
        entity_type="index_version",
        entity_id=body.index_version_id,
        user_id=current_user.user_id,
        username=current_user.username,
    )
    await db.commit()
    return {"ok": True, "activated_version": body.index_version_id}


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


@router.delete("/catalog/products", status_code=204)
async def delete_all_catalog_products(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "operator")),
):
    """Delete ALL catalog products."""
    repo = CatalogRepo(db)
    await repo.delete_all_products()
    await db.commit()
    return None
