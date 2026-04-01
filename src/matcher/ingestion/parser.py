import io
import json
import logging

import pandas as pd
from openai import AsyncOpenAI

from matcher.config import settings

logger = logging.getLogger(__name__)


async def _identify_column_via_llm(df_head: pd.DataFrame) -> str | None:
    """Use the configured LLM to identify the target nomenclature column."""
    llm_key = settings.active_llm_api_key
    model = settings.llm_model

    extra_headers = {}
    if settings.llm_provider == "openrouter":
        extra_headers["HTTP-Referer"] = "https://matcher.internal"
        extra_headers["X-Title"] = "Sales Nomenclature Matcher"

    client = AsyncOpenAI(
        api_key=llm_key,
        base_url=settings.active_llm_base_url,
        default_headers=extra_headers or None,
    )

    # Convert the first 5 rows to JSON
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
            extra_body={"no_thinking": True} if "qwen" in model.lower() else {},
        )
        content = response.choices[0].message.content or "{}"
        content = content.strip()
        if content.startswith("```json"):
            content = content.split("```json", 1)[-1].rsplit("```", 1)[0].strip()
        elif content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        data = json.loads(content)
        target = data.get("target_column")
        if target in df_head.columns:
            logger.info("LLM selected target column: %s", target)
            return target
    except Exception as e:
        logger.warning(f"LLM column identification failed: {e}")
    
    return None

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
        if not llm_key or llm_key in ("", "sk-your-key-here", "your-key-here"):
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
            
            # Use pandas built-in numeric check equivalent
            # Find rows that are NOT just digits/floats
            # A simple regex for pure numbers
            is_num = sample.str.match(r'^-?\d+(?:[\.,]\d+)?$')
            str_rows = sample[~is_num]
            
            txt_ratio = len(str_rows) / len(sample)
            avg_len = str_rows.str.len().mean() if len(str_rows) > 0 else 0
            
            score = txt_ratio * avg_len
            if score > best_score:
                best_score = score
                best_col = col
                
        # Only fallback to df.columns[0] if even the best score is totally completely broken
        target_col = best_col if best_score > 1.5 else df.columns[0]

    items = []
    # Extract items
    for idx, row in df.iterrows():
        raw_text = str(row[target_col]).strip()
        # Filter out random numbers or tiny strings
        if raw_text and len(raw_text) > 1 and raw_text.lower() not in ["nan", "none"]:
            items.append({
                "line_id": str(idx),
                "raw_text": raw_text,
                "original_row": row.to_dict()
            })
            
    return items
