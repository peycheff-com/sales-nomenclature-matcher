from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from matcher.api.v1.upload import _validate_excel_content
from matcher.db.models import User


def _admin_user() -> User:
    return User(
        user_id="u1",
        username="test_admin",
        hashed_password="x",
        role="admin",
        is_active=True,
    )


def _xlsx_bytes() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<Types />")
        zf.writestr("xl/workbook.xml", "<workbook />")
    return buffer.getvalue()


def _upload_files(name: str = "input.xlsx", content: bytes | None = None) -> dict:
    return {
        "file": (
            name,
            BytesIO(content if content is not None else _xlsx_bytes()),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }


def _assert_parse_received_xlsx_with_ai(parse: AsyncMock) -> None:
    parse.assert_awaited_once()
    args, kwargs = parse.await_args

    assert isinstance(args[0], bytes)
    assert args[0].startswith(b"PK")
    assert kwargs == {"use_ai": True}


class TestExcelValidation:
    def test_validate_excel_content_accepts_xlsx_and_legacy_xls_headers(self):
        _validate_excel_content(_xlsx_bytes())
        _validate_excel_content(b"\xd0\xcf\x11\xe0legacy-xls")

    @pytest.mark.parametrize(
        ("content", "detail"),
        [
            (b"123", "File is too small to be a valid Excel file."),
            (
                b"not-excel",
                "File does not appear to be a valid Excel file."
                " Only .xlsx and .xls files are accepted.",
            ),
            (
                b"\x50\x4b\x03\x04not-a-zip",
                "File is corrupted or not a valid Excel file.",
            ),
        ],
    )
    def test_validate_excel_content_rejects_invalid_content(self, content, detail):
        with pytest.raises(Exception) as exc_info:
            _validate_excel_content(content)

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == detail

    def test_validate_excel_content_rejects_zip_without_excel_markers(self):
        buffer = BytesIO()
        with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as zf:
            zf.writestr("README.txt", "not a workbook")

        with pytest.raises(Exception) as exc_info:
            _validate_excel_content(buffer.getvalue())

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "File appears to be a ZIP archive, not a valid Excel file."


class TestUploadEndpoints:
    @pytest.mark.asyncio
    async def test_upload_match_file_creates_request_items_and_enqueues(
        self, async_client, auth_headers, mock_db_session
    ):
        parsed_items = [
            {"line_id": 1, "raw_text": "SKF 6205", "original_row": {"Номенклатура": "SKF 6205"}}
        ]

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.upload.parse_excel_upload", new_callable=AsyncMock) as parse,
            patch("matcher.api.v1.upload.MatchRepo") as MockMatchRepo,
            patch("matcher.api.v1.upload.enqueue_request_job", new_callable=AsyncMock) as enqueue,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            parse.return_value = parsed_items
            MockMatchRepo.return_value.create_request = AsyncMock()
            MockMatchRepo.return_value.create_items = AsyncMock()

            resp = await async_client.post(
                "/api/v1/match/upload",
                files=_upload_files(),
                data={"supplier_id": "sup_1"},
                headers=auth_headers,
            )

        assert resp.status_code == 202
        assert resp.json()["status"] == "queued"
        MockMatchRepo.return_value.create_request.assert_awaited_once()
        MockMatchRepo.return_value.create_items.assert_awaited_once()
        enqueue.assert_awaited_once()
        mock_db_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upload_match_file_loads_settings_for_ai_picker(
        self, async_client, auth_headers, mock_db_session
    ):
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.upload.load_persisted_settings", new_callable=AsyncMock) as load,
            patch("matcher.api.v1.upload.parse_excel_upload", new_callable=AsyncMock) as parse,
            patch("matcher.api.v1.upload.MatchRepo") as MockMatchRepo,
            patch("matcher.api.v1.upload.enqueue_request_job", new_callable=AsyncMock),
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            parse.return_value = [{"line_id": 1, "raw_text": "item", "original_row": {}}]
            MockMatchRepo.return_value.create_request = AsyncMock()
            MockMatchRepo.return_value.create_items = AsyncMock()

            resp = await async_client.post(
                "/api/v1/match/upload",
                files=_upload_files(),
                data={"use_ai_column_picker": "true"},
                headers=auth_headers,
            )

        assert resp.status_code == 202
        load.assert_awaited_once_with(mock_db_session, force=True)
        _assert_parse_received_xlsx_with_ai(parse)

    @pytest.mark.asyncio
    async def test_upload_match_file_rejects_empty_parse(self, async_client, auth_headers):
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.upload.parse_excel_upload", new_callable=AsyncMock) as parse,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            parse.return_value = []

            resp = await async_client.post(
                "/api/v1/match/upload",
                files=_upload_files(),
                headers=auth_headers,
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == (
            "No data found. Ensure file contains a column with 'Номенклатура'."
        )

    @pytest.mark.asyncio
    async def test_upload_match_file_wraps_parse_errors(self, async_client, auth_headers):
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.upload.parse_excel_upload", new_callable=AsyncMock) as parse,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            parse.side_effect = ValueError("missing column")

            resp = await async_client.post(
                "/api/v1/match/upload",
                files=_upload_files(),
                headers=auth_headers,
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Failed to process file: missing column"

    @pytest.mark.asyncio
    async def test_upload_match_file_rejects_oversized_files(self, async_client, auth_headers):
        with patch("matcher.auth.deps.UserRepo") as MockUserRepo:
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            resp = await async_client.post(
                "/api/v1/match/upload",
                files=_upload_files(content=b"x" * (50 * 1024 * 1024 + 1)),
                headers=auth_headers,
            )

        assert resp.status_code == 413
        assert resp.json()["detail"] == "File exceeds 50 MB limit."

    @pytest.mark.asyncio
    async def test_parse_match_file_returns_simple_items(self, async_client, auth_headers):
        items = [{"line_id": 1, "raw_text": "SKF 6205", "original_row": {}}]

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.upload.load_persisted_settings", new_callable=AsyncMock),
            patch("matcher.api.v1.upload.parse_excel_upload", new_callable=AsyncMock) as parse,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            parse.return_value = items
            resp = await async_client.post(
                "/api/v1/match/parse",
                files=_upload_files(),
                headers=auth_headers,
            )

        assert resp.status_code == 200
        assert resp.json() == {"mode": "simple", "items": items}
        parse.assert_awaited_once_with(_xlsx_bytes(), use_ai=False)

    @pytest.mark.asyncio
    async def test_parse_match_file_uses_ai_column_picker(self, async_client, auth_headers):
        items = [{"line_id": 1, "raw_text": "SKF 6205", "original_row": {}}]

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.upload.load_persisted_settings", new_callable=AsyncMock),
            patch("matcher.api.v1.upload.parse_excel_upload", new_callable=AsyncMock) as parse,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            parse.return_value = items
            resp = await async_client.post(
                "/api/v1/match/parse",
                files=_upload_files(),
                data={"use_ai_column_picker": "true"},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        _assert_parse_received_xlsx_with_ai(parse)

    @pytest.mark.asyncio
    async def test_parse_match_file_rejects_oversized_files(self, async_client, auth_headers):
        with patch("matcher.auth.deps.UserRepo") as MockUserRepo:
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            resp = await async_client.post(
                "/api/v1/match/parse",
                files=_upload_files(content=b"x" * (50 * 1024 * 1024 + 1)),
                headers=auth_headers,
            )

        assert resp.status_code == 413
        assert resp.json()["detail"] == "File exceeds 50 MB limit."

    @pytest.mark.asyncio
    async def test_parse_match_file_returns_structure_analysis(self, async_client, auth_headers):
        analysis = SimpleNamespace(
            supplier_items=[{"line_id": 1, "raw_text": "supplier item"}],
            catalog_items=[{"raw_text": "catalog item"}],
            supplier_name="Acme",
            tables_detected=2,
        )

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.upload.load_persisted_settings", new_callable=AsyncMock),
            patch(
                "matcher.api.v1.upload.analyze_file_structure", new_callable=AsyncMock
            ) as analyze,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            analyze.return_value = analysis
            resp = await async_client.post(
                "/api/v1/match/parse",
                files=_upload_files(),
                data={"analyze_structure": "true"},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        assert resp.json() == {
            "mode": "structured",
            "supplier_items": analysis.supplier_items,
            "catalog_items": analysis.catalog_items,
            "supplier_name": "Acme",
            "tables_detected": 2,
        }

    @pytest.mark.asyncio
    async def test_parse_match_file_wraps_errors(self, async_client, auth_headers):
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.upload.load_persisted_settings", new_callable=AsyncMock),
            patch("matcher.api.v1.upload.parse_excel_upload", new_callable=AsyncMock) as parse,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            parse.side_effect = ValueError("bad sheet")
            resp = await async_client.post(
                "/api/v1/match/parse",
                files=_upload_files(),
                headers=auth_headers,
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Failed to parse file: bad sheet"

    @pytest.mark.asyncio
    async def test_smart_upload_creates_supplier_when_needed(
        self, async_client, auth_headers, mock_db_session
    ):
        analysis = SimpleNamespace(
            supplier_items=[{"line_id": 1, "raw_text": "supplier item", "original_row": {}}],
            catalog_items=[{"raw_text": "catalog item", "unit": "pcs"}],
            supplier_name="New Supplier",
        )

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.upload.load_persisted_settings", new_callable=AsyncMock),
            patch(
                "matcher.api.v1.upload.analyze_file_structure", new_callable=AsyncMock
            ) as analyze,
            patch("matcher.db.repos.supplier.SupplierRepo") as MockSupplierRepo,
            patch("matcher.api.v1.upload.MatchRepo") as MockMatchRepo,
            patch("matcher.api.v1.upload.enqueue_request_job", new_callable=AsyncMock) as enqueue,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            analyze.return_value = analysis
            MockSupplierRepo.return_value.list_suppliers = AsyncMock(return_value=[])
            MockSupplierRepo.return_value.create_supplier = AsyncMock()
            MockMatchRepo.return_value.create_request = AsyncMock()
            MockMatchRepo.return_value.create_items = AsyncMock()

            resp = await async_client.post(
                "/api/v1/match/smart-upload",
                files=_upload_files(),
                headers=auth_headers,
            )

        assert resp.status_code == 202
        MockSupplierRepo.return_value.create_supplier.assert_awaited_once()
        MockMatchRepo.return_value.create_request.assert_awaited_once()
        enqueue.assert_awaited_once()
        mock_db_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_smart_upload_rejects_oversized_files(self, async_client, auth_headers):
        with patch("matcher.auth.deps.UserRepo") as MockUserRepo:
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            resp = await async_client.post(
                "/api/v1/match/smart-upload",
                files=_upload_files(content=b"x" * (50 * 1024 * 1024 + 1)),
                headers=auth_headers,
            )

        assert resp.status_code == 413
        assert resp.json()["detail"] == "File exceeds 50 MB limit."

    @pytest.mark.asyncio
    async def test_smart_upload_reuses_existing_supplier(self, async_client, auth_headers):
        analysis = SimpleNamespace(
            supplier_items=[{"line_id": 1, "raw_text": "supplier item", "original_row": {}}],
            catalog_items=[],
            supplier_name="Acme",
        )
        supplier = SimpleNamespace(supplier_id="sup_existing", supplier_name="ACME")

        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.upload.load_persisted_settings", new_callable=AsyncMock),
            patch(
                "matcher.api.v1.upload.analyze_file_structure", new_callable=AsyncMock
            ) as analyze,
            patch("matcher.db.repos.supplier.SupplierRepo") as MockSupplierRepo,
            patch("matcher.api.v1.upload.MatchRepo") as MockMatchRepo,
            patch("matcher.api.v1.upload.enqueue_request_job", new_callable=AsyncMock),
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            analyze.return_value = analysis
            MockSupplierRepo.return_value.list_suppliers = AsyncMock(return_value=[supplier])
            MockSupplierRepo.return_value.create_supplier = AsyncMock()
            MockMatchRepo.return_value.create_request = AsyncMock()
            MockMatchRepo.return_value.create_items = AsyncMock()

            resp = await async_client.post(
                "/api/v1/match/smart-upload",
                files=_upload_files(),
                headers=auth_headers,
            )

        assert resp.status_code == 202
        MockSupplierRepo.return_value.create_supplier.assert_not_awaited()
        kwargs = MockMatchRepo.return_value.create_request.await_args.kwargs
        assert kwargs["supplier_id"] == "sup_existing"

    @pytest.mark.asyncio
    async def test_smart_upload_rejects_analysis_errors_and_missing_supplier_items(
        self, async_client, auth_headers
    ):
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.upload.load_persisted_settings", new_callable=AsyncMock),
            patch(
                "matcher.api.v1.upload.analyze_file_structure", new_callable=AsyncMock
            ) as analyze,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            analyze.side_effect = ValueError("no tables")
            resp = await async_client.post(
                "/api/v1/match/smart-upload",
                files=_upload_files(),
                headers=auth_headers,
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Failed to analyze file: no tables"

        empty_analysis = SimpleNamespace(supplier_items=[], catalog_items=[], supplier_name=None)
        with (
            patch("matcher.auth.deps.UserRepo") as MockUserRepo,
            patch("matcher.api.v1.upload.load_persisted_settings", new_callable=AsyncMock),
            patch(
                "matcher.api.v1.upload.analyze_file_structure", new_callable=AsyncMock
            ) as analyze,
        ):
            MockUserRepo.return_value.get_by_username = AsyncMock(return_value=_admin_user())
            analyze.return_value = empty_analysis
            resp = await async_client.post(
                "/api/v1/match/smart-upload",
                files=_upload_files(),
                headers=auth_headers,
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Не обнаружены данные поставщика для сопоставления."
