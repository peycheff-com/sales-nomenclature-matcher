import uuid

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.api.deps import get_db, get_arq_pool
from matcher.auth.deps import get_current_user
from matcher.db.models import User
from matcher.db.repos.match import MatchRepo
from matcher.ingestion.parser import parse_excel_upload
from matcher.schemas.match import BatchRequestAccepted

router = APIRouter(tags=["Upload"])

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
            detail="File does not appear to be a valid Excel file. Only .xlsx and .xls files are accepted.",
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
    contents = await file.read()
    _validate_excel_content(contents)
    try:
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
    current_user: User = Depends(get_current_user),
):
    """Parse an Excel file and return extracted nomenclature candidates for UI preview."""
    contents = await file.read()
    _validate_excel_content(contents)
    try:
        items = await parse_excel_upload(contents, use_ai=use_ai_column_picker)
        return {"items": items}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")
