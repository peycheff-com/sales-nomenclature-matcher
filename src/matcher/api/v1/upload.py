import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.api.deps import get_arq_pool, get_db
from matcher.api.v1.settings import load_persisted_settings
from matcher.auth.deps import get_current_user
from matcher.db.models import User
from matcher.db.repos.match import MatchRepo
from matcher.ingestion.parser import analyze_file_structure, parse_excel_upload
from matcher.schemas.match import BatchRequestAccepted

router = APIRouter(tags=["Upload"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

# XLSX/ZIP magic bytes (PK\x03\x04)
_XLSX_MAGIC = b"\x50\x4b\x03\x04"
# Old XLS magic bytes (Microsoft Compound File)
_XLS_MAGIC = b"\xd0\xcf\x11\xe0"


def _validate_excel_content(content: bytes) -> None:
    """Reject files that don't look like Excel based on magic bytes."""
    if len(content) < 4:
        raise HTTPException(status_code=400, detail="File is too small to be a valid Excel file.")
    header = content[:4]
    if header not in (_XLSX_MAGIC, _XLS_MAGIC):
        raise HTTPException(
            status_code=400,
            detail=(
                "File does not appear to be a valid Excel file."
                " Only .xlsx and .xls files are accepted."
            ),
        )


@router.post("/match/upload", response_model=BatchRequestAccepted, status_code=202)
async def upload_match_file(
    file: UploadFile = File(...),
    supplier_id: str | None = Form(None),
    use_ai_column_picker: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    arq_pool=Depends(get_arq_pool),
    current_user: User = Depends(get_current_user),
):
    """Securely upload an Excel file and enqueue it for batch matching."""
    contents = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 50 MB limit.")
    _validate_excel_content(contents)
    try:
        if use_ai_column_picker:
            await load_persisted_settings(db, force=True)
        items = await parse_excel_upload(contents, use_ai=use_ai_column_picker)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process file: {str(e)}")

    if not items:
        raise HTTPException(
            status_code=400,
            detail="No data found. Ensure file contains a column with 'Номенклатура'.",
        )

    request_id = f"req_{uuid.uuid4().hex[:12]}"
    repo = MatchRepo(db)

    # Store request
    await repo.create_request(
        request_id=request_id,
        supplier_id=supplier_id,
        source_type="excel_upload",
        file_name=file.filename,
        submitted_by=current_user.username,
        total_items=len(items),
    )

    # Convert items to dict structure for repo
    items_data = [
        {"line_id": str(i["line_id"]), "raw_text": i["raw_text"], "original_row": i["original_row"]}
        for i in items
    ]
    await repo.create_items(request_id, items_data)
    await db.commit()

    # Enqueue ARQ job
    await arq_pool.enqueue_job("batch_match", request_id)

    return BatchRequestAccepted(request_id=request_id, status="queued")


@router.post("/match/parse")
async def parse_match_file(
    file: UploadFile = File(...),
    use_ai_column_picker: bool = Form(False),
    analyze_structure: bool = Form(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Parse an Excel file and return extracted nomenclature candidates for UI preview.

    When ``analyze_structure`` is True, uses AI to detect multiple tables
    (supplier input vs catalog reference) and returns a structured analysis.
    """
    contents = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 50 MB limit.")
    _validate_excel_content(contents)

    try:
        await load_persisted_settings(db, force=True)

        if analyze_structure:
            result = await analyze_file_structure(contents)
            return {
                "mode": "structured",
                "supplier_items": result.supplier_items,
                "catalog_items": result.catalog_items,
                "supplier_name": result.supplier_name,
                "tables_detected": result.tables_detected,
            }

        if use_ai_column_picker:
            items = await parse_excel_upload(contents, use_ai=True)
        else:
            items = await parse_excel_upload(contents, use_ai=False)

        return {"mode": "simple", "items": items}

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")


@router.post("/match/smart-upload", response_model=BatchRequestAccepted, status_code=202)
async def smart_upload(
    file: UploadFile = File(...),
    supplier_name: str | None = Form(None),
    supplier_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    arq_pool=Depends(get_arq_pool),
    current_user: User = Depends(get_current_user),
):
    """Smart upload: AI-analyze file, ingest catalog, create supplier, and match.

    This endpoint is the one-shot workflow:
    1. Saves the raw file contents
    2. Enqueues a ``smart_upload`` worker task that:
       a. Re-runs structure analysis
       b. Ingests catalog items into catalog_products
       c. Creates supplier profile if needed
       d. Reindexes embeddings
       e. Runs batch matching on supplier items
    """
    contents = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 50 MB limit.")
    _validate_excel_content(contents)

    await load_persisted_settings(db, force=True)

    # Pre-analyze to get total item count for the MatchRequest
    try:
        result = await analyze_file_structure(contents)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to analyze file: {str(e)}")

    if not result.supplier_items:
        raise HTTPException(
            status_code=400,
            detail="Не обнаружены данные поставщика для сопоставления.",
        )

    # Determine supplier_id
    effective_supplier_name = supplier_name or result.supplier_name
    effective_supplier_id = supplier_id

    if not effective_supplier_id and effective_supplier_name:
        # Auto-create or find supplier
        from matcher.db.repos.supplier import SupplierRepo

        supplier_repo = SupplierRepo(db)
        suppliers = await supplier_repo.list_suppliers(active_only=False)
        existing = next(
            (s for s in suppliers if s.supplier_name.lower() == effective_supplier_name.lower()),
            None,
        )
        if existing:
            effective_supplier_id = existing.supplier_id
        else:
            sid = f"sup_{uuid.uuid4().hex[:8]}"
            await supplier_repo.create_supplier(sid, effective_supplier_name)
            effective_supplier_id = sid

    # Create the match request (so the UI can track it immediately)
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    repo = MatchRepo(db)
    await repo.create_request(
        request_id=request_id,
        supplier_id=effective_supplier_id,
        source_type="smart_upload",
        file_name=file.filename,
        submitted_by=current_user.username,
        total_items=len(result.supplier_items),
    )

    # Store supplier items
    items_data = [
        {
            "line_id": str(i["line_id"]),
            "raw_text": i["raw_text"],
            "original_row": i.get("original_row", {}),
        }
        for i in result.supplier_items
    ]
    await repo.create_items(request_id, items_data)
    await db.commit()

    # Enqueue the smart_upload worker task with catalog items inline
    # (avoids re-reading the file in the worker)
    catalog_items_payload = [
        {"raw_text": i["raw_text"], "unit": i.get("unit")} for i in result.catalog_items
    ]
    await arq_pool.enqueue_job(
        "smart_upload",
        request_id,
        catalog_items=catalog_items_payload,
        catalog_count=len(result.catalog_items),
    )

    return BatchRequestAccepted(request_id=request_id, status="queued")
