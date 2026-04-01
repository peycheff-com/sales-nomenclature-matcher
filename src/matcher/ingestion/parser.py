import io
import json
import logging
import uuid
from dataclasses import dataclass, field

import pandas as pd
from openai import AsyncOpenAI

from matcher.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures for multi-table analysis
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
    label: str = ""  # Human-readable label extracted from the header


@dataclass
class FileAnalysisResult:
    """Full analysis of an uploaded file."""

    supplier_items: list[dict] = field(default_factory=list)
    catalog_items: list[dict] = field(default_factory=list)
    supplier_name: str | None = None
    tables_detected: int = 0


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


async def _identify_column_via_llm(df_head: pd.DataFrame) -> str | None:
    """Use the configured LLM to identify the target nomenclature column."""
    client, model, extra_body = _make_llm_client()

    sample_data = df_head.fillna("").head(5).to_dict(orient="records")
    columns = list(df_head.columns)

    prompt = f"""You are a data extraction assistant.
I have a dataset with the following columns: {columns}

Here are the first 5 rows:
{json.dumps(sample_data, ensure_ascii=False, indent=2)}

Your task is to identify which column contains the "product nomenclature", "product name", "item description" or basically the raw string that a human would recognize as the primary product being sold or ordered. 
Usually it's named something like "Номенклатура", "Наименование", "Товар", "Product", "Description", but it could be deeply nested or misspelled in messy files.
Do NOT select columns that only contain quantities, prices, article codes (unless it's the only descriptive text), or sequential IDs.

Return ONLY a valid JSON object with a single key "target_column" and the exact string name of the column as the value. Do not explain anything. Output raw JSON.
Example: {{"target_column": "Наименование товара"}}
"""

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
# AI Structure Analysis — multi-table detection
# ---------------------------------------------------------------------------


async def _analyze_structure_via_llm(raw_rows: list[list]) -> dict | None:
    """Ask the LLM to identify all data regions/tables in a raw sheet.

    ``raw_rows`` is a list of lists — the first ~12 rows of the sheet with
    values converted to strings (None → "").
    Returns the parsed JSON from the LLM or None on failure.
    """
    llm_key = settings.active_llm_api_key
    if not llm_key or llm_key in ("", "sk-your-key-here", "your-key-here", "none"):
        raise ValueError(
            "Умный анализ файла включен, но API ключ LLM провайдера не настроен."
        )

    client, model, extra_body = _make_llm_client()

    # Build column letters for context (A, B, C, …)
    max_cols = max(len(r) for r in raw_rows) if raw_rows else 0
    col_letters = [chr(ord("A") + i) if i < 26 else f"A{chr(ord('A') + i - 26)}" for i in range(max_cols)]

    # Format as a grid with column letters
    grid_lines: list[str] = []
    grid_lines.append("     " + "  |  ".join(col_letters[:max_cols]))
    grid_lines.append("     " + "-----" * max_cols)
    for row_idx, row in enumerate(raw_rows):
        cells = []
        for c in range(max_cols):
            v = str(row[c]) if c < len(row) and row[c] is not None else ""
            cells.append(v[:50])  # Truncate long values
        grid_lines.append(f"R{row_idx + 1:>3}: " + "  |  ".join(cells))

    grid_text = "\n".join(grid_lines)

    prompt = f"""You are an expert data analyst. Below is a raw spreadsheet grid (first ~12 rows).
The sheet may contain MULTIPLE SEPARATE TABLES side by side, separated by empty columns.
Each table might represent different data: one could be a client/supplier product list, 
another could be a reference catalog, or metadata/notes.

GRID:
{grid_text}

TASK: Identify ALL distinct data tables/regions in this grid. For each table, determine:
1. "role" — classify as "supplier_input" (client/external product list to match), 
   "catalog_reference" (our own canonical product catalog), or "metadata" (notes, mappings, auxiliary)
2. "col_start" — first column letter (e.g. "A")
3. "col_end" — last column letter (e.g. "C")
4. "header_row" — 1-based row number where the column headers are
5. "name_col" — column letter containing the product name/nomenclature
6. "unit_col" — column letter containing unit of measure (or null if not present)
7. "label" — a short human-readable label for this table, derived from any title/header text

Also extract:
- "supplier_name" — if you can identify the client/supplier company name from any headers or titles, provide it (e.g. from text like "Номенклатура клиента = КЕМИКС" → "КЕМИКС"). null if not found.

IMPORTANT RULES:
- Look for visual separators (empty columns) between tables
- Headers like "Номенклатура клиента" or "Номенклатура нашего поставщика" indicate supplier_input
- Headers like "Номенклатура наша" or "Каталог" or "Эталонная номенклатура" indicate catalog_reference
- If a column contains "Единицы измерения" or "ед.", that's the unit column
- A table with client/external products is supplier_input; the company's own products are catalog_reference
- If you can only detect ONE table, set its role to "supplier_input"

Return ONLY valid JSON:
{{
  "tables": [
    {{
      "role": "supplier_input",
      "col_start": "A",
      "col_end": "C",
      "header_row": 2,
      "name_col": "B",
      "unit_col": "C",
      "label": "Номенклатура клиента (КЕМИКС)"
    }},
    ...
  ],
  "supplier_name": "КЕМИКС"
}}
"""

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=512,
            extra_body=extra_body or {},
        )
        result = _clean_json_response(response.choices[0].message.content or "{}")
        tables = result.get("tables")
        if not isinstance(tables, list) or len(tables) == 0:
            logger.warning("LLM structure analysis returned no tables")
            return None
        logger.info(
            "LLM detected %d table(s), supplier=%s",
            len(tables),
            result.get("supplier_name"),
        )
        return result
    except Exception as e:
        logger.warning("LLM structure analysis failed: %s", e)
        return None


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
) -> list[dict]:
    """Extract items from a specific rectangular region of the raw DataFrame.

    Parameters use 0-based indices. ``df_raw`` is read with header=None.
    """
    # Slice the region
    region = df_raw.iloc[header_row:, col_start : col_end + 1].copy()
    if region.empty:
        return []

    # Use first row as header
    new_headers = [str(v).strip() if pd.notna(v) else f"col_{i}" for i, v in enumerate(region.iloc[0])]
    region.columns = new_headers
    region = region.iloc[1:]  # Drop header row
    region = region.dropna(how="all")
    region = region.fillna("")

    # The name column index relative to the sliced region
    name_col_relative = name_col - col_start
    if name_col_relative < 0 or name_col_relative >= len(region.columns):
        logger.warning("name_col %d outside region bounds [%d, %d]", name_col, col_start, col_end)
        return []

    target_col_name = region.columns[name_col_relative]

    unit_col_name = None
    if unit_col is not None:
        unit_col_relative = unit_col - col_start
        if 0 <= unit_col_relative < len(region.columns):
            unit_col_name = region.columns[unit_col_relative]

    items: list[dict] = []
    for idx, row in region.iterrows():
        raw_text = str(row[target_col_name]).strip()
        if not raw_text or len(raw_text) <= 1 or raw_text.lower() in ("nan", "none", ""):
            continue

        item: dict = {
            "line_id": str(idx),
            "raw_text": raw_text,
            "original_row": {k: (str(v) if pd.notna(v) else "") for k, v in row.to_dict().items()},
        }
        if unit_col_name:
            unit_val = str(row.get(unit_col_name, "")).strip()
            if unit_val and unit_val.lower() not in ("nan", "none"):
                item["unit"] = unit_val

        items.append(item)

    return items


async def analyze_file_structure(file_contents: bytes) -> FileAnalysisResult:
    """AI-driven analysis of an Excel file to detect multiple tables.

    Returns a FileAnalysisResult with supplier items, catalog items,
    and detected supplier name.
    """
    try:
        df_raw = pd.read_excel(io.BytesIO(file_contents), header=None)
    except Exception as e:
        raise ValueError(f"Failed to read Excel file: {e}")

    if df_raw.empty:
        return FileAnalysisResult()

    # Get first ~12 rows as raw values for LLM
    sample_rows: list[list] = []
    for i in range(min(12, len(df_raw))):
        row_vals = []
        for v in df_raw.iloc[i]:
            row_vals.append(str(v) if pd.notna(v) else "")
        sample_rows.append(row_vals)

    analysis = await _analyze_structure_via_llm(sample_rows)

    if not analysis:
        # Fallback: treat entire file as single supplier_input table
        items = await parse_excel_upload(file_contents, use_ai=True)
        return FileAnalysisResult(supplier_items=items, tables_detected=1)

    result = FileAnalysisResult(
        supplier_name=analysis.get("supplier_name"),
        tables_detected=len(analysis.get("tables", [])),
    )

    for table_spec in analysis.get("tables", []):
        try:
            col_start = _col_letter_to_index(table_spec["col_start"])
            col_end = _col_letter_to_index(table_spec["col_end"])
            header_row = int(table_spec["header_row"]) - 1  # Convert to 0-based
            name_col = _col_letter_to_index(table_spec["name_col"])
            unit_col = (
                _col_letter_to_index(table_spec["unit_col"])
                if table_spec.get("unit_col")
                else None
            )

            items = _extract_region_items(
                df_raw, col_start, col_end, header_row, name_col, unit_col
            )

            role = table_spec.get("role", "supplier_input")
            if role == "catalog_reference":
                result.catalog_items.extend(items)
            elif role == "supplier_input":
                result.supplier_items.extend(items)
            # "metadata" role is ignored

            logger.info(
                "Extracted %d items from %s table '%s' (cols %s-%s)",
                len(items),
                role,
                table_spec.get("label", "?"),
                table_spec["col_start"],
                table_spec["col_end"],
            )
        except Exception as e:
            logger.warning("Failed to extract region from table spec %s: %s", table_spec, e)

    return result


# ---------------------------------------------------------------------------
# Legacy single-column extraction (unchanged)
# ---------------------------------------------------------------------------


async def parse_excel_upload(file_contents: bytes, use_ai: bool = False) -> list[dict]:
    """Smart parse messy Excel file to extract nomenclature listings."""
    try:
        df = pd.read_excel(io.BytesIO(file_contents), header=None)
    except Exception as e:
        raise ValueError(f"Failed to read Excel file: {e}")

    if df.empty:
        return []

    # Look for keywords that suggest a header is starting
    keywords = ["номенклатура", "наименование", "название", "товар", "name", "артикул"]
    header_idx = 0
    for i in range(min(15, len(df))):
        row_vals = df.iloc[i].astype(str).str.lower()
        if any(any(kw in val for kw in keywords) for val in row_vals):
            header_idx = i
            break

    # Read actual data starting from the chosen header
    df = pd.read_excel(io.BytesIO(file_contents), header=header_idx)
    df = df.dropna(how="all")
    df = df.fillna("")

    target_col = None
    if use_ai:
        llm_key = settings.active_llm_api_key
        if not llm_key or llm_key in ("", "sk-your-key-here", "your-key-here", "none"):
            raise ValueError("Умный поиск включен, но API ключ LLM провайдера не настроен в настройках.")
        # Let the LLM judge first what the column is
        target_col = await _identify_column_via_llm(df)

    # Try to find the target terminology column fallback
    if not target_col:
        for col in df.columns:
            cl = str(col).lower().strip()
            if "номенклатура клиента" in cl or "наименование клиента" in cl:
                target_col = col
                break

    if not target_col:
        for col in df.columns:
            cl = str(col).lower().strip()
            if "номенклатура" in cl or "наименование" in cl or "name" in cl:
                target_col = col
                break

    # Fallback: Score string density to avoid purely numerical columns
    if not target_col:
        best_col = None
        best_score = -1
        for col in df.columns:
            sample = df[col].dropna().astype(str).str.strip()
            if len(sample) == 0:
                continue

            is_num = sample.str.match(r'^-?\d+(?:[\.,]\d+)?$')
            str_rows = sample[~is_num]

            txt_ratio = len(str_rows) / len(sample)
            avg_len = str_rows.str.len().mean() if len(str_rows) > 0 else 0

            score = txt_ratio * avg_len
            if score > best_score:
                best_score = score
                best_col = col

        target_col = best_col if best_score > 1.5 else df.columns[0]

    items = []
    for idx, row in df.iterrows():
        raw_text = str(row[target_col]).strip()
        if raw_text and len(raw_text) > 1 and raw_text.lower() not in ["nan", "none"]:
            items.append({
                "line_id": str(idx),
                "raw_text": raw_text,
                "original_row": row.to_dict()
            })

    return items
