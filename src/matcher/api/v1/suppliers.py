from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.api.deps import get_db
from matcher.auth.deps import get_current_user, require_role
from matcher.db.models import User
from matcher.db.repos.audit import AuditRepo
from matcher.db.repos.supplier import SupplierRepo
from matcher.normalization.pipeline import run_pipeline
from matcher.schemas.supplier import (
    SupplierCreate,
    SupplierMapping,
    SupplierMappingInput,
    SupplierProfile,
    SupplierUpdate,
)

router = APIRouter(tags=["Suppliers"])


@router.get("/suppliers")
async def list_suppliers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    repo = SupplierRepo(db)
    suppliers = await repo.list_suppliers(active_only=False)
    return {"items": [SupplierProfile.model_validate(s) for s in suppliers]}


@router.post("/suppliers", response_model=SupplierProfile, status_code=201)
async def create_supplier(
    body: SupplierCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "operator")),
):
    repo = SupplierRepo(db)
    existing = await repo.get_supplier(body.supplier_id)
    if existing:
        raise HTTPException(status_code=400, detail="Supplier with this ID already exists")

    supplier = await repo.create_supplier(
        supplier_id=body.supplier_id,
        name=body.supplier_name,
        strict_mode=body.strict_mode,
    )
    await db.commit()
    return SupplierProfile.model_validate(supplier)


@router.put("/suppliers/{supplier_id}", response_model=SupplierProfile)
async def update_supplier(
    supplier_id: str,
    body: SupplierUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "operator")),
):
    repo = SupplierRepo(db)
    supplier = await repo.update_supplier(
        supplier_id=supplier_id,
        **body.model_dump(exclude_none=True),
    )
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    await db.commit()
    return SupplierProfile.model_validate(supplier)


@router.post(
    "/suppliers/{supplier_id}/mappings",
    response_model=SupplierMapping,
    status_code=201,
)
async def create_supplier_mapping(
    supplier_id: str,
    body: SupplierMappingInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "operator")),
):
    repo = SupplierRepo(db)

    # Verify supplier exists
    supplier = await repo.get_supplier(supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    # Normalize raw text if provided
    normalized_text = None
    if body.supplier_raw_text:
        ctx = run_pipeline(body.supplier_raw_text)
        normalized_text = ctx.text

    mapping = await repo.create_mapping(
        supplier_id=supplier_id,
        data={
            "supplier_sku": body.supplier_sku,
            "supplier_article": body.supplier_article,
            "supplier_raw_text": body.supplier_raw_text,
            "normalized_supplier_text": normalized_text,
            "product_id": body.product_id,
            "mapping_type": body.mapping_type,
            "confidence": body.confidence,
            "approved_by": current_user.username,
        },
    )

    audit = AuditRepo(db)
    await audit.log(
        action="mapping_create",
        entity_type="supplier_mapping",
        entity_id=supplier_id,
        user_id=current_user.user_id,
        username=current_user.username,
        details={
            "product_id": body.product_id,
            "mapping_type": body.mapping_type,
            "supplier_raw_text": body.supplier_raw_text,
        },
    )

    await db.commit()
    return SupplierMapping.model_validate(mapping)


@router.delete("/suppliers/{supplier_id}", status_code=200)
async def delete_supplier(
    supplier_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "operator")),
):
    repo = SupplierRepo(db)
    success = await repo.delete_supplier(supplier_id)
    if not success:
        raise HTTPException(status_code=404, detail="Supplier not found")
    await db.commit()
    return {"ok": True}


@router.get("/suppliers/{supplier_id}/mappings")
async def list_supplier_mappings(
    supplier_id: str,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = SupplierRepo(db)
    supplier = await repo.get_supplier(supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    mappings = await repo.get_supplier_mappings(supplier_id, limit=limit, offset=offset)
    return {"items": [SupplierMapping.model_validate(m) for m in mappings]}
