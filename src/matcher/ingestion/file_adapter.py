from __future__ import annotations

import csv
import io
import uuid
from pathlib import Path

import chardet
import openpyxl

from matcher.ingestion.base import RawCatalogItem

# Standard column name mappings (Russian -> field name)
COLUMN_MAP = {
    "код": "code",
    "артикул": "article",
    "наименование": "name",
    "полное наименование": "full_name",
    "бренд": "brand",
    "производитель": "manufacturer",
    "код производителя": "manufacturer_code",
    "единица": "unit",
    "единица измерения": "unit",
    "ед": "unit",
    "ед.": "unit",
    "категория": "category_path",
    "группа": "category_path",
    "упаковка": "packaging",
    "вес": "weight_value",
    "объем": "volume_value",
    "размер": "size_value",
    "ссылка": "onec_ref",
    "ref": "onec_ref",
    "id": "product_id",
    "product_id": "product_id",
    "code": "code",
    "article": "article",
    "name": "name",
    "full_name": "full_name",
    "brand": "brand",
    "manufacturer": "manufacturer",
    "manufacturer_code": "manufacturer_code",
    "unit": "unit",
    "category_path": "category_path",
    "packaging": "packaging",
    "weight_value": "weight_value",
    "volume_value": "volume_value",
    "size_value": "size_value",
    "onec_ref": "onec_ref",
}


def _detect_encoding(raw_bytes: bytes) -> str:
    result = chardet.detect(raw_bytes[:10000])
    return result.get("encoding", "utf-8") or "utf-8"


def _map_columns(headers: list[str]) -> dict[int, str]:
    """Map column indices to field names."""
    mapping = {}
    for idx, header in enumerate(headers):
        key = header.strip().lower()
        if key in COLUMN_MAP:
            mapping[idx] = COLUMN_MAP[key]
    return mapping


def _row_to_item(row: list, col_map: dict[int, str]) -> RawCatalogItem | None:
    data = {}
    for idx, field_name in col_map.items():
        if idx < len(row):
            val = row[idx]
            if val is not None:
                val = str(val).strip()
                if val:
                    data[field_name] = val

    if not data.get("name"):
        return None

    # Parse numeric fields
    for num_field in ("weight_value", "volume_value", "size_value"):
        if num_field in data:
            try:
                data[num_field] = float(str(data[num_field]).replace(",", "."))
            except (ValueError, TypeError):
                del data[num_field]

    if "product_id" not in data:
        data["product_id"] = f"prd_{uuid.uuid4().hex[:12]}"

    return RawCatalogItem(**data)


def parse_csv(file_path: str | Path) -> list[RawCatalogItem]:
    """Parse a CSV file into raw catalog items."""
    path = Path(file_path)
    raw_bytes = path.read_bytes()
    encoding = _detect_encoding(raw_bytes)
    text = raw_bytes.decode(encoding)

    reader = csv.reader(io.StringIO(text), delimiter=_detect_delimiter(text))
    rows = list(reader)
    if not rows:
        return []

    col_map = _map_columns(rows[0])
    if not col_map:
        raise ValueError(f"No recognized columns in headers: {rows[0]}")

    items = []
    for row in rows[1:]:
        item = _row_to_item(row, col_map)
        if item:
            items.append(item)
    return items


def _detect_delimiter(text: str) -> str:
    """Detect CSV delimiter from first line."""
    first_line = text.split("\n")[0]
    if "\t" in first_line:
        return "\t"
    if ";" in first_line:
        return ";"
    return ","


def parse_xlsx(file_path: str | Path) -> list[RawCatalogItem]:
    """Parse an XLSX file into raw catalog items."""
    wb = openpyxl.load_workbook(str(file_path), read_only=True, data_only=True)
    ws = wb.active
    if ws is None:
        return []

    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return []

    headers = [str(c) if c else "" for c in rows[0]]
    col_map = _map_columns(headers)
    if not col_map:
        raise ValueError(f"No recognized columns in headers: {headers}")

    items = []
    for row in rows[1:]:
        row_list = list(row)
        item = _row_to_item(row_list, col_map)
        if item:
            items.append(item)
    return items


def parse_file(file_path: str | Path) -> list[RawCatalogItem]:
    """Parse CSV or XLSX file based on extension."""
    path = Path(file_path)
    ext = path.suffix.lower()
    if ext == ".xlsx":
        return parse_xlsx(path)
    elif ext in (".csv", ".tsv", ".txt"):
        return parse_csv(path)
    else:
        raise ValueError(f"Unsupported file format: {ext}")
