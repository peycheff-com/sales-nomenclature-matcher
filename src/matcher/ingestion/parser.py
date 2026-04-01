"""
State-of-the-art file parser for messy supplier price lists and catalogs.

Handles:
- Multiple tables on the same sheet (side-by-side or stacked)
- Headers on arbitrary rows, multi-row headers, title rows above data
- Merged cells (explicit unmerge via openpyxl)
- Mixed supplier + catalog data on the same sheet
- CSV/TSV/TXT with encoding detection and delimiter sniffing
- Multi-sheet Excel files (scans all sheets, picks the best)
- Empty row/column gap detection for table boundary finding
- Duplicate row deduplication
- Graceful fallback when LLM is unavailable
"""

import csv
import io
import json
import logging
import re
from dataclasses import dataclass, field

import chardet
import pandas as pd
from openai import AsyncOpenAI

from matcher.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class DetectedTable:
    """A single data region detected inside a file."""

    role: str  # "supplier_input" | "catalog_reference" | "metadata"
    col_start: int  # 0-based column index
    col_end: int  # 0-based column index (inclusive)
    header_row: int  # 0-based row index
    name_col_index: int  # 0-based column index of the nomenclature column
    unit_col_index: int | None = None
    price_col_index: int | None = None
    article_col_index: int | None = None
    label: str = ""


@dataclass
class FileAnalysisResult:
    """Full analysis of an uploaded file."""

    supplier_items: list[dict] = field(default_factory=list)
    catalog_items: list[dict] = field(default_factory=list)
    supplier_name: str | None = None
    tables_detected: int = 0


# ---------------------------------------------------------------------------
# Constants for heuristic detection
# ---------------------------------------------------------------------------

_NAME_KEYWORDS = [
    "номенклатура", "наименование", "название", "товар", "продукт",
    "описание", "продукция", "позиция", "name", "product", "description", "item",
]
_UNIT_KEYWORDS = ["ед.изм", "ед. изм", "единица", "единицы", "unit", "измерен"]
_PRICE_KEYWORDS = ["цена", "стоимость", "price", "руб", "₽", "cost"]
_ARTICLE_KEYWORDS = ["артикул", "арт", "код", "sku", "article", "code", "id товара"]
_HEADER_KEYWORDS = _NAME_KEYWORDS + _UNIT_KEYWORDS + _PRICE_KEYWORDS + _ARTICLE_KEYWORDS
_SUPPLIER_HINT_KEYWORDS = [
    "клиент", "поставщик", "заказчик", "покупатель", "supplier", "client",
]
_CATALOG_HINT_KEYWORDS = [
    "каталог", "наш", "эталон", "база", "справочник", "catalog", "reference",
]
# Rows that look like totals / summaries to skip
_SKIP_ROW_PATTERNS = re.compile(
    r"^\s*(итого|всего|total|subtotal|сумма|итог)\b", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------


def _make_llm_client() -> tuple[AsyncOpenAI, str, dict]:
    """Create an OpenAI-compatible client using current settings."""
    llm_key = settings.active_llm_api_key
    model = settings.llm_model

    extra_headers: dict[str, str] = {}
    if settings.llm_provider == "openrouter":
        extra_headers["HTTP-Referer"] = "https://matcher.internal"
        extra_headers["X-Title"] = "Sales Nomenclature Matcher"

    client = AsyncOpenAI(
        api_key=llm_key,
        base_url=settings.active_llm_base_url,
        default_headers=extra_headers or None,
        timeout=30.0,
    )
    extra_body: dict = {}
    if "qwen" in model.lower():
        extra_body["no_thinking"] = True

    return client, model, extra_body


def _clean_json_response(content: str) -> dict:
    """Strip markdown fences and parse JSON from LLM response."""
    content = content.strip()
    if content.startswith("```json"):
        content = content.split("```json", 1)[-1].rsplit("```", 1)[0].strip()
    elif content.startswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return json.loads(content)


def _llm_available() -> bool:
    """Check if an LLM provider is configured with a valid key."""
    key = settings.active_llm_api_key
    return bool(key and key not in ("", "sk-your-key-here", "your-key-here", "none"))


# ---------------------------------------------------------------------------
# Low-level sheet reading utilities
# ---------------------------------------------------------------------------


def _read_excel_raw(file_contents: bytes, sheet_name: int | str = 0) -> pd.DataFrame:
    """Read an Excel file with merged cell handling."""
    try:
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(file_contents), read_only=False, data_only=True)
        ws = wb.worksheets[sheet_name] if isinstance(sheet_name, int) else wb[sheet_name]

        # Unmerge cells and fill values
        for merge in list(ws.merged_cells.ranges):
            min_row, min_col = merge.min_row, merge.min_col
            val = ws.cell(min_row, min_col).value
            ws.unmerge_cells(str(merge))
            for row in range(merge.min_row, merge.max_row + 1):
                for col in range(merge.min_col, merge.max_col + 1):
                    ws.cell(row, col).value = val

        # Convert to list of lists
        data = []
        for row in ws.iter_rows(values_only=True):
            data.append(list(row))
        wb.close()

        return pd.DataFrame(data) if data else pd.DataFrame()
    except Exception:
        # Fallback to pandas if openpyxl fails
        return pd.read_excel(io.BytesIO(file_contents), header=None, sheet_name=sheet_name)


def _read_csv_raw(file_contents: bytes) -> pd.DataFrame:
    """Read a CSV/TSV file with encoding detection and delimiter sniffing."""
    # Detect encoding
    detected = chardet.detect(file_contents[:10000])
    encoding = detected.get("encoding", "utf-8") or "utf-8"

    try:
        text = file_contents.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        text = file_contents.decode("utf-8", errors="replace")

    # Remove BOM
    text = text.lstrip("\ufeff")

    # Sniff delimiter
    sample = text[:4000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="\t;,|")
        delimiter = dialect.delimiter
    except csv.Error:
        # Count occurrences to guess
        tab_count = sample.count("\t")
        semi_count = sample.count(";")
        comma_count = sample.count(",")
        if tab_count > semi_count and tab_count > comma_count:
            delimiter = "\t"
        elif semi_count > comma_count:
            delimiter = ";"
        else:
            delimiter = ","

    try:
        df = pd.read_csv(io.StringIO(text), header=None, sep=delimiter, engine="python",
                         on_bad_lines="skip", dtype=str)
    except Exception:
        df = pd.read_csv(io.StringIO(text), header=None, sep=delimiter, engine="python",
                         on_bad_lines="skip", dtype=str, quoting=csv.QUOTE_NONE)

    return df


def _get_best_sheet(file_contents: bytes) -> tuple[pd.DataFrame, str]:
    """Pick the sheet with the most data from a multi-sheet Excel file."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(file_contents), read_only=True, data_only=True)
        sheet_names = wb.sheetnames
        wb.close()
    except Exception:
        return _read_excel_raw(file_contents, 0), "Sheet1"

    if len(sheet_names) <= 1:
        return _read_excel_raw(file_contents, 0), sheet_names[0] if sheet_names else "Sheet1"

    best_df = pd.DataFrame()
    best_name = sheet_names[0]
    best_score = -1

    for name in sheet_names:
        try:
            df = _read_excel_raw(file_contents, name)
            # Score: non-empty cells * row count
            non_empty = df.notna().sum().sum()
            score = non_empty * len(df)
            if score > best_score:
                best_score = score
                best_df = df
                best_name = name
        except Exception:
            continue

    logger.info("Selected sheet '%s' from %d sheets (score=%d)", best_name, len(sheet_names), best_score)
    return best_df, best_name


# ---------------------------------------------------------------------------
# Heuristic table boundary detection (no LLM required)
# ---------------------------------------------------------------------------


def _find_empty_col_gaps(df: pd.DataFrame, threshold: float = 0.85) -> list[int]:
    """Find column indices that are mostly empty (table separators)."""
    gaps = []
    for c in range(len(df.columns)):
        col = df.iloc[:, c]
        empty_ratio = col.isna().sum() / max(len(col), 1)
        if empty_ratio >= threshold:
            gaps.append(c)
    return gaps


def _find_empty_row_gaps(df: pd.DataFrame, threshold: float = 0.85) -> list[int]:
    """Find row indices that are mostly empty (potential table separators)."""
    gaps = []
    for r in range(len(df)):
        row = df.iloc[r]
        empty_ratio = row.isna().sum() / max(len(row), 1)
        if empty_ratio >= threshold:
            gaps.append(r)
    return gaps


def _split_into_column_groups(df: pd.DataFrame) -> list[tuple[int, int]]:
    """Split the DataFrame into column groups separated by empty columns.

    Returns list of (col_start, col_end) tuples (inclusive, 0-based).
    """
    gaps = set(_find_empty_col_gaps(df))
    groups: list[tuple[int, int]] = []
    start = None

    for c in range(len(df.columns)):
        if c in gaps:
            if start is not None:
                groups.append((start, c - 1))
                start = None
        else:
            if start is None:
                start = c

    if start is not None:
        groups.append((start, len(df.columns) - 1))

    return groups


def _detect_header_row(df: pd.DataFrame, col_start: int, col_end: int) -> int:
    """Detect the header row within a column group using keyword scoring.

    Penalizes merged-cell title rows (where all cells are identical) and
    prefers rows with diverse, short, keyword-rich cells.
    """
    best_row = 0
    best_score = -1

    for i in range(min(20, len(df))):
        row = df.iloc[i, col_start: col_end + 1]
        row_strs = [str(v).lower().strip() for v in row if pd.notna(v)]
        if not row_strs:
            continue

        # Penalize merged-cell title rows: all cells identical
        unique_vals = set(row_strs)
        if len(unique_vals) == 1 and len(row_strs) > 1:
            continue  # Skip — this is a title/merged row, not headers

        # Count keyword matches — only match keywords that are likely headers,
        # not data values. Require keyword to be a significant part of the cell.
        keyword_hits = 0
        for val in row_strs:
            for kw in _HEADER_KEYWORDS:
                if kw in val:
                    # Keyword should be a major part of the cell (not just "шт" in "штуках")
                    if len(kw) >= len(val) * 0.3 or len(val) < 30:
                        keyword_hits += 1
                        break

        cell_count = len([v for v in row_strs if v])
        diversity = len(unique_vals) / max(len(row_strs), 1)
        # Strong brevity bonus: headers are short (< 25 chars avg), data is longer
        avg_len = sum(len(v) for v in row_strs) / max(len(row_strs), 1)
        brevity = max(0, 2.0 - avg_len / 15)

        score = keyword_hits * 5 + cell_count * 1.5 + diversity * 3 + brevity * 4

        if score > best_score:
            best_score = score
            best_row = i

    return best_row


def _classify_column(df: pd.DataFrame, col_idx: int, header_row: int) -> str:
    """Classify a column as 'name', 'unit', 'price', 'article', 'number', or 'other'."""
    header_val = str(df.iloc[header_row, col_idx]).lower().strip() if header_row < len(df) else ""

    # Check header keywords
    if any(kw in header_val for kw in _NAME_KEYWORDS):
        return "name"
    if any(kw in header_val for kw in _UNIT_KEYWORDS):
        return "unit"
    if any(kw in header_val for kw in _PRICE_KEYWORDS):
        return "price"
    if any(kw in header_val for kw in _ARTICLE_KEYWORDS):
        return "article"

    # Analyze data content (first 20 data rows after header)
    data_rows = df.iloc[header_row + 1: header_row + 21, col_idx].dropna().astype(str).str.strip()
    data_rows = data_rows[data_rows != ""]
    if len(data_rows) == 0:
        return "other"

    is_numeric = data_rows.str.match(r"^-?\d+(?:[\.,]\d+)?\s*(?:руб|₽|шт|кг|л)?\.?$")
    numeric_ratio = is_numeric.sum() / len(data_rows)

    if numeric_ratio > 0.8:
        avg_val = data_rows.str.replace(r"[^\d.,]", "", regex=True).str.replace(",", ".").apply(
            lambda x: float(x) if x else 0
        ).mean()
        # Prices tend to be > 1, quantities small
        if avg_val > 10:
            return "price"
        return "number"

    avg_len = data_rows.str.len().mean()
    if avg_len > 15:
        return "name"  # Long text → likely nomenclature
    if avg_len < 5:
        return "unit" if data_rows.str.len().max() < 8 else "article"

    return "other"


def _classify_table_role(
    df: pd.DataFrame, col_start: int, col_end: int, header_row: int
) -> str:
    """Classify a table group as supplier_input or catalog_reference."""
    # Check header row text for hints
    row = df.iloc[header_row, col_start: col_end + 1]
    header_text = " ".join(str(v).lower() for v in row if pd.notna(v))

    # Check rows above header for title hints
    for i in range(max(0, header_row - 3), header_row):
        title_row = df.iloc[i, col_start: col_end + 1]
        header_text += " " + " ".join(str(v).lower() for v in title_row if pd.notna(v))

    if any(kw in header_text for kw in _SUPPLIER_HINT_KEYWORDS):
        return "supplier_input"
    if any(kw in header_text for kw in _CATALOG_HINT_KEYWORDS):
        return "catalog_reference"

    return "supplier_input"  # Default


def _extract_supplier_name(
    df: pd.DataFrame, col_start: int, col_end: int, header_row: int
) -> str | None:
    """Try to extract a supplier/client name from title rows above the header."""
    for i in range(max(0, header_row - 5), header_row):
        row = df.iloc[i, col_start: col_end + 1]
        for v in row:
            if pd.isna(v):
                continue
            s = str(v).strip()
            # Pattern: "Номенклатура клиента = КЕМИКС" or "Поставщик: ООО Ромашка"
            for pattern in [
                r"(?:номенклатура\s+клиента)\s*[=:–—-]\s*(.+)",
                r"(?:клиент|поставщик|заказчик)\s*[=:]\s*(.+)",
                r"(?:номенклатура\s+(?:клиента|поставщика))\s*[=:–—-]\s*(.+)",
                r"^(ООО|ОАО|АО|ИП|ЗАО)\s+.+",
            ]:
                m = re.search(pattern, s, re.IGNORECASE)
                if m:
                    name = m.group(1) if m.lastindex else s
                    return name.strip().strip("\"'«»")
    return None


# ---------------------------------------------------------------------------
# Heuristic-based multi-table extraction (no LLM)
# ---------------------------------------------------------------------------


def _analyze_heuristic(df_raw: pd.DataFrame) -> FileAnalysisResult:
    """Detect tables and extract items using purely heuristic methods."""
    col_groups = _split_into_column_groups(df_raw)
    if not col_groups:
        return FileAnalysisResult()

    result = FileAnalysisResult(tables_detected=len(col_groups))

    for col_start, col_end in col_groups:
        width = col_end - col_start + 1
        if width < 1:
            continue

        header_row = _detect_header_row(df_raw, col_start, col_end)

        # Classify columns
        name_col = None
        unit_col = None
        price_col = None
        article_col = None

        for c in range(col_start, col_end + 1):
            ctype = _classify_column(df_raw, c, header_row)
            if ctype == "name" and name_col is None:
                name_col = c
            elif ctype == "unit" and unit_col is None:
                unit_col = c
            elif ctype == "price" and price_col is None:
                price_col = c
            elif ctype == "article" and article_col is None:
                article_col = c

        # If no name column found, pick the column with longest text
        if name_col is None:
            best_len = 0
            for c in range(col_start, col_end + 1):
                data = df_raw.iloc[header_row + 1:, c].dropna().astype(str)
                avg_len = data.str.len().mean() if len(data) > 0 else 0
                if avg_len > best_len:
                    best_len = avg_len
                    name_col = c
            if name_col is None:
                name_col = col_start

        role = _classify_table_role(df_raw, col_start, col_end, header_row)

        # Try to extract supplier name
        if role == "supplier_input" and result.supplier_name is None:
            result.supplier_name = _extract_supplier_name(df_raw, col_start, col_end, header_row)

        items = _extract_region_items(
            df_raw, col_start, col_end, header_row, name_col, unit_col, price_col
        )

        if role == "catalog_reference":
            result.catalog_items.extend(items)
        else:
            result.supplier_items.extend(items)

        logger.info(
            "Heuristic: extracted %d items from %s table (cols %d-%d, header row %d)",
            len(items), role, col_start, col_end, header_row,
        )

    return result


# ---------------------------------------------------------------------------
# LLM-based structure analysis
# ---------------------------------------------------------------------------


async def _analyze_structure_via_llm(raw_rows: list[list]) -> dict | None:
    """Ask the LLM to identify all data regions/tables in a raw sheet."""
    if not _llm_available():
        return None

    client, model, extra_body = _make_llm_client()

    max_cols = max(len(r) for r in raw_rows) if raw_rows else 0
    col_letters = []
    for i in range(max_cols):
        if i < 26:
            col_letters.append(chr(ord("A") + i))
        else:
            col_letters.append(chr(ord("A") + i // 26 - 1) + chr(ord("A") + i % 26))

    # Format grid
    grid_lines: list[str] = []
    grid_lines.append("     " + "  |  ".join(col_letters))
    grid_lines.append("     " + "-----" * max_cols)
    for row_idx, row in enumerate(raw_rows):
        cells = []
        for c in range(max_cols):
            v = str(row[c]) if c < len(row) and row[c] is not None else ""
            cells.append(v[:40])
        grid_lines.append(f"R{row_idx + 1:>3}: " + "  |  ".join(cells))

    grid_text = "\n".join(grid_lines)

    prompt = f"""You are an expert data analyst parsing messy supplier spreadsheets.
Below is a raw grid (first rows of a sheet). It may contain MULTIPLE SEPARATE TABLES
side by side, separated by empty columns. Common patterns:
- Left table: supplier/client product list to be matched
- Right table: canonical catalog/reference products
- Title rows above data (company names, dates, notes)
- Mixed headers on different rows per table
- Price columns, unit columns, article/SKU columns mixed in

GRID:
{grid_text}

TASK: Identify ALL distinct data tables. For each:
1. "role": "supplier_input" (client products to match) or "catalog_reference" (our catalog) or "metadata"
2. "col_start", "col_end": column letters bounding the table
3. "header_row": 1-based row number of column headers
4. "name_col": column letter of the product name/nomenclature
5. "unit_col": column letter of unit of measure (null if absent)
6. "price_col": column letter of price (null if absent)
7. "label": short label from any title/header

Also extract "supplier_name" if you can identify a company name.

RULES:
- Empty columns between populated columns = table boundary
- "Номенклатура клиента" / "Товар поставщика" → supplier_input
- "Номенклатура наша" / "Каталог" / "Эталон" → catalog_reference
- If only ONE table found → role = "supplier_input"
- Skip summary/total rows
- The nomenclature column has the LONGEST text strings (product descriptions)

Return ONLY valid JSON:
{{"tables": [...], "supplier_name": "..." or null}}"""

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=800,
            extra_body=extra_body or {},
        )
        result = _clean_json_response(response.choices[0].message.content or "{}")
        tables = result.get("tables")
        if not isinstance(tables, list) or len(tables) == 0:
            return None
        logger.info("LLM detected %d table(s), supplier=%s", len(tables), result.get("supplier_name"))
        return result
    except Exception as e:
        logger.warning("LLM structure analysis failed: %s", e)
        return None


async def _identify_column_via_llm(df_head: pd.DataFrame) -> str | None:
    """Use the configured LLM to identify the target nomenclature column."""
    if not _llm_available():
        return None

    client, model, extra_body = _make_llm_client()

    sample_data = df_head.fillna("").head(5).to_dict(orient="records")
    columns = list(df_head.columns)

    prompt = f"""You are a data extraction assistant.
I have a dataset with columns: {columns}

First 5 rows:
{json.dumps(sample_data, ensure_ascii=False, indent=2)}

Which column contains the PRIMARY product nomenclature/name/description?
NOT quantities, NOT prices, NOT article codes (unless only descriptive text).
Look for the column with the longest human-readable product descriptions.

Return ONLY JSON: {{"target_column": "exact column name"}}"""

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=64,
            extra_body=extra_body or {},
        )
        data = _clean_json_response(response.choices[0].message.content or "{}")
        target = data.get("target_column")
        if target in df_head.columns:
            logger.info("LLM selected target column: %s", target)
            return target
    except Exception as e:
        logger.warning("LLM column identification failed: %s", e)

    return None


# ---------------------------------------------------------------------------
# Region extraction
# ---------------------------------------------------------------------------


def _col_letter_to_index(letter: str) -> int:
    """Convert column letter (A, B, ..., Z, AA, AB, ...) to 0-based index."""
    letter = letter.upper().strip()
    result = 0
    for ch in letter:
        result = result * 26 + (ord(ch) - ord("A") + 1)
    return result - 1


def _extract_region_items(
    df_raw: pd.DataFrame,
    col_start: int,
    col_end: int,
    header_row: int,
    name_col: int,
    unit_col: int | None = None,
    price_col: int | None = None,
) -> list[dict]:
    """Extract items from a rectangular region, deduplicating."""
    region = df_raw.iloc[header_row:, col_start: col_end + 1].copy()
    if region.empty:
        return []

    # Use first row as header
    new_headers = [
        str(v).strip() if pd.notna(v) else f"col_{i}" for i, v in enumerate(region.iloc[0])
    ]
    # Handle duplicate header names
    seen: dict[str, int] = {}
    for i, h in enumerate(new_headers):
        if h in seen:
            seen[h] += 1
            new_headers[i] = f"{h}_{seen[h]}"
        else:
            seen[h] = 0

    region.columns = new_headers
    region = region.iloc[1:]
    region = region.dropna(how="all")
    region = region.fillna("")

    name_col_relative = name_col - col_start
    if name_col_relative < 0 or name_col_relative >= len(region.columns):
        return []

    target_col_name = region.columns[name_col_relative]

    unit_col_name = None
    if unit_col is not None:
        unit_rel = unit_col - col_start
        if 0 <= unit_rel < len(region.columns):
            unit_col_name = region.columns[unit_rel]

    price_col_name = None
    if price_col is not None:
        price_rel = price_col - col_start
        if 0 <= price_rel < len(region.columns):
            price_col_name = region.columns[price_rel]

    items: list[dict] = []
    seen_texts: set[str] = set()

    for idx, row in region.iterrows():
        raw_text = str(row[target_col_name]).strip()
        if not raw_text or len(raw_text) <= 1 or raw_text.lower() in ("nan", "none", ""):
            continue
        # Skip total/summary rows
        if _SKIP_ROW_PATTERNS.match(raw_text):
            continue
        # Deduplicate
        lower_text = raw_text.lower()
        if lower_text in seen_texts:
            continue
        seen_texts.add(lower_text)

        item: dict = {
            "line_id": str(idx),
            "raw_text": raw_text,
            "original_row": {k: (str(v) if pd.notna(v) else "") for k, v in row.to_dict().items()},
        }
        if unit_col_name:
            val = str(row.get(unit_col_name, "")).strip()
            if val and val.lower() not in ("nan", "none"):
                item["unit"] = val
        if price_col_name:
            val = str(row.get(price_col_name, "")).strip()
            if val and val.lower() not in ("nan", "none"):
                item["price"] = val

        items.append(item)

    return items


# ---------------------------------------------------------------------------
# Public API: analyze_file_structure (AI + heuristic hybrid)
# ---------------------------------------------------------------------------


async def analyze_file_structure(file_contents: bytes) -> FileAnalysisResult:
    """AI-driven analysis with heuristic fallback for multi-table detection."""
    df_raw, sheet_name = _get_best_sheet(file_contents)
    if df_raw.empty:
        return FileAnalysisResult()

    logger.info("Analyzing structure of sheet '%s' (%d rows, %d cols)", sheet_name, len(df_raw), len(df_raw.columns))

    # First try: heuristic gap detection to see if there are multiple column groups
    col_groups = _split_into_column_groups(df_raw)
    has_multiple_tables = len(col_groups) > 1

    # Try LLM analysis (richer results)
    sample_rows: list[list] = []
    for i in range(min(15, len(df_raw))):
        row_vals = [str(v) if pd.notna(v) else "" for v in df_raw.iloc[i]]
        sample_rows.append(row_vals)

    llm_result = await _analyze_structure_via_llm(sample_rows)

    if llm_result:
        result = FileAnalysisResult(
            supplier_name=llm_result.get("supplier_name"),
            tables_detected=len(llm_result.get("tables", [])),
        )
        for table_spec in llm_result.get("tables", []):
            try:
                cs = _col_letter_to_index(table_spec["col_start"])
                ce = _col_letter_to_index(table_spec["col_end"])
                hr = int(table_spec["header_row"]) - 1
                nc = _col_letter_to_index(table_spec["name_col"])
                uc = _col_letter_to_index(table_spec["unit_col"]) if table_spec.get("unit_col") else None
                pc = _col_letter_to_index(table_spec["price_col"]) if table_spec.get("price_col") else None

                items = _extract_region_items(df_raw, cs, ce, hr, nc, uc, pc)
                role = table_spec.get("role", "supplier_input")
                if role == "catalog_reference":
                    result.catalog_items.extend(items)
                elif role == "supplier_input":
                    result.supplier_items.extend(items)

                logger.info("LLM: %d items from %s '%s' (cols %s-%s)",
                            len(items), role, table_spec.get("label", "?"),
                            table_spec["col_start"], table_spec["col_end"])
            except Exception as e:
                logger.warning("Failed to extract LLM-detected region: %s", e)

        if result.supplier_items or result.catalog_items:
            return result

    # Fallback: heuristic analysis
    logger.info("Using heuristic analysis (LLM unavailable or returned no results)")
    result = _analyze_heuristic(df_raw)
    if result.supplier_items or result.catalog_items:
        return result

    # Last resort: single-table extraction
    items = await parse_excel_upload(file_contents, use_ai=_llm_available())
    return FileAnalysisResult(supplier_items=items, tables_detected=1)


# ---------------------------------------------------------------------------
# Public API: parse_excel_upload (single-table extraction)
# ---------------------------------------------------------------------------


async def parse_excel_upload(file_contents: bytes, use_ai: bool = False) -> list[dict]:
    """Extract nomenclature items from a file (Excel, CSV, TSV, TXT)."""
    # Detect file type by magic bytes
    is_excel = (
        file_contents[:4] == b"PK\x03\x04"  # XLSX
        or file_contents[:4] == b"\xd0\xcf\x11\xe0"  # XLS
    )

    if is_excel:
        df_raw, _ = _get_best_sheet(file_contents)
    else:
        df_raw = _read_csv_raw(file_contents)

    if df_raw.empty:
        return []

    # Detect header row
    header_idx = _detect_header_row(df_raw, 0, len(df_raw.columns) - 1)

    # Re-read with header
    if is_excel:
        try:
            df = pd.read_excel(io.BytesIO(file_contents), header=header_idx)
        except Exception:
            df = df_raw.copy()
            headers = [str(v).strip() if pd.notna(v) else f"col_{i}" for i, v in enumerate(df.iloc[header_idx])]
            df.columns = headers
            df = df.iloc[header_idx + 1:]
    else:
        df = df_raw.copy()
        headers = [str(v).strip() if pd.notna(v) else f"col_{i}" for i, v in enumerate(df.iloc[header_idx])]
        df.columns = headers
        df = df.iloc[header_idx + 1:]

    df = df.dropna(how="all")
    df = df.fillna("")

    # Find target column
    target_col = None
    if use_ai:
        if not _llm_available():
            raise ValueError("Умный поиск включен, но API ключ LLM провайдера не настроен в настройках.")
        target_col = await _identify_column_via_llm(df)

    # Heuristic fallbacks
    if not target_col:
        # Priority 1: exact keyword match
        for col in df.columns:
            cl = str(col).lower().strip()
            if "номенклатура клиента" in cl or "наименование клиента" in cl:
                target_col = col
                break

    if not target_col:
        # Priority 2: keyword match
        for col in df.columns:
            cl = str(col).lower().strip()
            if any(kw in cl for kw in _NAME_KEYWORDS):
                target_col = col
                break

    if not target_col:
        # Priority 3: text density scoring
        best_col = None
        best_score = -1.0
        for col in df.columns:
            sample = df[col].dropna().astype(str).str.strip()
            sample = sample[sample != ""]
            if len(sample) == 0:
                continue
            is_num = sample.str.match(r"^-?\d+(?:[\.,]\d+)?\s*$")
            str_rows = sample[~is_num]
            txt_ratio = len(str_rows) / len(sample)
            avg_len = str_rows.str.len().mean() if len(str_rows) > 0 else 0
            score = txt_ratio * avg_len
            if score > best_score:
                best_score = score
                best_col = col

        target_col = best_col if best_score > 1.5 else df.columns[0]

    # Extract items
    items: list[dict] = []
    seen: set[str] = set()
    for idx, row in df.iterrows():
        raw_text = str(row[target_col]).strip()
        if not raw_text or len(raw_text) <= 1 or raw_text.lower() in ("nan", "none"):
            continue
        if _SKIP_ROW_PATTERNS.match(raw_text):
            continue
        lower = raw_text.lower()
        if lower in seen:
            continue
        seen.add(lower)
        items.append({
            "line_id": str(idx),
            "raw_text": raw_text,
            "original_row": {k: str(v) for k, v in row.to_dict().items()},
        })

    return items
