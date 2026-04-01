"""Native 1C:Enterprise OData integration.

Supports the standard 1C REST interface (OData v3.0) published at:
    http://<server>/<publication>/odata/standard.odata/

Reference: https://v8.1c.ru/platforma/rest-interfeys/

Typical catalog resource:
    Catalog_Номенклатура  (or Catalog_Products for English configs)

Authentication: HTTP Basic Auth with a 1C user that has the
    "УдаленныйДоступOData" role assigned.
"""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator
from urllib.parse import urlencode, urljoin

import httpx

from matcher.ingestion.base import RawCatalogItem

logger = logging.getLogger(__name__)

# ── Default OData config ────────────────────────────────────────────────────

DEFAULT_PAGE_SIZE = 500
DEFAULT_TIMEOUT = 120.0  # seconds per request

# Standard 1C OData catalog resource name
DEFAULT_RESOURCE = "Catalog_Номенклатура"

# Fields to request via $select (keeps responses lean).
# These are the standard 1C:УТ / 1С:ERP nomenclature fields.
# The actual field set depends on the customer's configuration —
# the $metadata endpoint should be queried for the exact schema.
STANDARD_SELECT_FIELDS = [
    "Ref_Key",
    "Code",
    "Description",
    "Артикул",
    "НаименованиеПолное",
    "Производитель",
    "Производитель_Key",
    "ЕдиницаИзмерения",
    "ЕдиницаИзмерения_Key",
    "Родитель_Key",
    "IsFolder",
    "DeletionMark",
    "КодПроизводителя",
    "Бренд",
    "Бренд_Key",
    "Вес",
    "Объем",
]

# Map from 1C OData field names to RawCatalogItem field names.
# 1C configurations vary — both Russian and English field names are handled.
FIELD_ALIASES: dict[str, list[str]] = {
    "name": ["Description", "Наименование", "Name", "name"],
    "full_name": ["НаименованиеПолное", "FullName", "full_name"],
    "article": ["Артикул", "Article", "article", "SKU"],
    "code": ["Code", "Код", "code"],
    "onec_ref": ["Ref_Key", "Ссылка_Key", "Ref", "id", "uid"],
    "brand": ["Бренд", "Brand", "brand"],
    "manufacturer": ["Производитель", "Manufacturer", "manufacturer"],
    "manufacturer_code": ["КодПроизводителя", "ManufacturerCode", "manufacturer_code"],
    "unit": ["ЕдиницаИзмерения", "Unit", "unit", "BaseUnit"],
    "category_id": ["Родитель_Key", "Parent_Key"],
    "packaging": ["Упаковка", "Packaging", "packaging"],
    "weight_value": ["Вес", "Weight", "weight"],
    "volume_value": ["Объем", "Volume", "volume"],
}


# ── Public API ──────────────────────────────────────────────────────────────


class OneCODataClient:
    """Client for 1C:Enterprise standard OData REST interface."""

    def __init__(
        self,
        base_url: str,
        username: str = "",
        password: str = "",
        resource: str = DEFAULT_RESOURCE,
        endpoint: str = "/odata/standard.odata/",
        page_size: int = DEFAULT_PAGE_SIZE,
        timeout: float = DEFAULT_TIMEOUT,
        select_fields: list[str] | None = None,
        filter_expr: str | None = None,
    ):
        # Build the OData service root URL
        self.service_root = base_url.rstrip("/") + endpoint
        self.resource = resource
        self.auth = (username, password) if username else None
        self.page_size = page_size
        self.timeout = timeout
        self.select_fields = select_fields or STANDARD_SELECT_FIELDS
        self.filter_expr = filter_expr or "DeletionMark eq false and IsFolder eq false"

    def _resource_url(self) -> str:
        return self.service_root.rstrip("/") + "/" + self.resource

    # ── Health / Metadata ────────────────────────────────────────────────

    async def health_check(self) -> dict:
        """Test connectivity by fetching $metadata and the first record."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Check metadata endpoint
            meta_url = self.service_root.rstrip("/") + "/$metadata"
            try:
                resp = await client.get(meta_url, auth=self.auth)
                meta_ok = resp.status_code == 200
            except Exception as e:
                return {"status": "error", "detail": f"Metadata unreachable: {e}"}

            # Check catalog with $top=1
            try:
                url = self._resource_url()
                params = {"$format": "json", "$top": "1"}
                resp = await client.get(url, params=params, auth=self.auth)
                resp.raise_for_status()
                data = resp.json()
                sample_count = len(data.get("value", []))
            except Exception as e:
                return {
                    "status": "error",
                    "detail": f"Catalog query failed: {e}",
                    "metadata_ok": meta_ok,
                }

            return {
                "status": "ok",
                "metadata_ok": meta_ok,
                "sample_records": sample_count,
            }

    async def get_metadata_fields(self) -> list[str]:
        """Fetch $metadata and extract field names for the catalog entity."""
        from defusedxml import ElementTree as ET

        meta_url = self.service_root.rstrip("/") + "/$metadata"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(meta_url, auth=self.auth)
            resp.raise_for_status()

        # Parse OData EDMX metadata (defusedxml prevents XXE attacks)
        root = ET.fromstring(resp.text)
        ns = {
            "edmx": "http://schemas.microsoft.com/ado/2007/06/edmx",
            "edm": "http://schemas.microsoft.com/ado/2008/09/edm",
        }
        fields = []
        # Find the entity type matching our resource
        entity_name = self.resource.replace("Catalog_", "Catalog_") + "Type"
        for entity_type in root.iter("{http://schemas.microsoft.com/ado/2008/09/edm}EntityType"):
            name = entity_type.get("Name", "")
            if self.resource.split("_")[-1] in name:
                for prop in entity_type.findall("{http://schemas.microsoft.com/ado/2008/09/edm}Property"):
                    fields.append(prop.get("Name", ""))
                break
        return fields

    # ── Count ────────────────────────────────────────────────────────────

    async def get_total_count(self) -> int:
        """Get total number of records using $count endpoint."""
        url = self._resource_url() + "/$count"
        params: dict[str, str] = {}
        if self.filter_expr:
            params["$filter"] = self.filter_expr

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params, auth=self.auth)
            resp.raise_for_status()
            return int(resp.text.strip())

    # ── Paginated fetch ──────────────────────────────────────────────────

    async def fetch_page(self, skip: int = 0) -> list[dict[str, Any]]:
        """Fetch a single page of catalog items."""
        url = self._resource_url()
        params: dict[str, str] = {
            "$format": "json",
            "$top": str(self.page_size),
            "$skip": str(skip),
            "$orderby": "Code asc",
        }
        if self.select_fields:
            params["$select"] = ",".join(self.select_fields)
        if self.filter_expr:
            params["$filter"] = self.filter_expr

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(url, params=params, auth=self.auth)
            resp.raise_for_status()
            data = resp.json()

        # OData v3 wraps results in {"value": [...]}
        if isinstance(data, dict):
            return data.get("value", data.get("d", {}).get("results", []))
        return data if isinstance(data, list) else []

    async def fetch_all(
        self,
        progress_callback: Any | None = None,
    ) -> list[RawCatalogItem]:
        """Fetch all catalog items with automatic pagination."""
        total = await self.get_total_count()
        logger.info("1C OData: total records = %d, page_size = %d", total, self.page_size)

        all_items: list[RawCatalogItem] = []
        skip = 0

        while skip < total:
            page = await self.fetch_page(skip=skip)
            if not page:
                break

            for row in page:
                item = map_onec_odata_item(row)
                if item is not None:
                    all_items.append(item)

            skip += len(page)

            if progress_callback:
                progress_callback(fetched=skip, total=total)

            logger.info("1C OData: fetched %d / %d", min(skip, total), total)

        logger.info("1C OData: complete — %d items mapped", len(all_items))
        return all_items

    async def fetch_iter(self) -> AsyncIterator[RawCatalogItem]:
        """Iterate over all catalog items page by page (memory-efficient)."""
        total = await self.get_total_count()
        skip = 0

        while skip < total:
            page = await self.fetch_page(skip=skip)
            if not page:
                break

            for row in page:
                item = map_onec_odata_item(row)
                if item is not None:
                    yield item

            skip += len(page)


# ── Category/group resolution ───────────────────────────────────────────────


async def fetch_category_map(
    base_url: str,
    username: str = "",
    password: str = "",
    resource: str = DEFAULT_RESOURCE,
    endpoint: str = "/odata/standard.odata/",
) -> dict[str, str]:
    """Fetch folder items to build Ref_Key → full category path map.

    1C catalogs store groups as IsFolder=true items in the same table.
    Parent_Key / Родитель_Key links child → parent.
    """
    service_root = base_url.rstrip("/") + endpoint
    url = service_root.rstrip("/") + "/" + resource
    auth = (username, password) if username else None

    params = {
        "$format": "json",
        "$filter": "IsFolder eq true",
        "$select": "Ref_Key,Description,Родитель_Key,Code",
        "$top": "5000",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(url, params=params, auth=auth)
        resp.raise_for_status()
        data = resp.json()

    folders = data.get("value", [])

    # Build lookup: ref_key → {name, parent_key}
    lookup: dict[str, dict] = {}
    empty_guid = "00000000-0000-0000-0000-000000000000"
    for f in folders:
        ref = f.get("Ref_Key", "")
        lookup[ref] = {
            "name": f.get("Description", ""),
            "parent": f.get("Родитель_Key", empty_guid),
        }

    # Resolve full paths
    def resolve_path(ref_key: str, depth: int = 0) -> str:
        if depth > 10 or ref_key not in lookup or ref_key == empty_guid:
            return ""
        node = lookup[ref_key]
        parent_path = resolve_path(node["parent"], depth + 1)
        if parent_path:
            return parent_path + "/" + node["name"]
        return node["name"]

    return {ref: resolve_path(ref) for ref in lookup}


# ── Field mapping ───────────────────────────────────────────────────────────


def _get_field(row: dict[str, Any], aliases: list[str]) -> Any:
    """Get a field value trying multiple possible names."""
    for alias in aliases:
        val = row.get(alias)
        if val is not None and val != "":
            return val
    return None


def _resolve_ref_field(row: dict[str, Any], key_field: str, desc_field: str | None = None) -> str | None:
    """Resolve a 1C reference field.

    In OData responses, reference fields can appear as:
    - A string (the Description if $expand was used)
    - A dict with Description key (nested expand)
    - Just the _Key GUID (needs separate resolution)
    """
    val = row.get(key_field)
    if isinstance(val, dict):
        return val.get("Description", val.get("Наименование", str(val)))
    if desc_field:
        desc = row.get(desc_field)
        if desc:
            return str(desc)
    return None


def _parse_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(str(val).replace(",", "."))
    except (ValueError, TypeError):
        return None


def map_onec_odata_item(
    row: dict[str, Any],
    category_map: dict[str, str] | None = None,
) -> RawCatalogItem | None:
    """Map a 1C OData JSON row to a RawCatalogItem.

    Handles both Russian and English field names, as well as
    standard OData system fields (Ref_Key, DeletionMark, etc.).
    """
    # Skip deleted and folder items
    if row.get("DeletionMark", False):
        return None
    if row.get("IsFolder", False):
        return None

    name = _get_field(row, FIELD_ALIASES["name"])
    if not name or not str(name).strip():
        return None

    onec_ref = _get_field(row, FIELD_ALIASES["onec_ref"])
    code = _get_field(row, FIELD_ALIASES["code"])
    article = _get_field(row, FIELD_ALIASES["article"])
    full_name = _get_field(row, FIELD_ALIASES["full_name"])
    brand = _get_field(row, FIELD_ALIASES["brand"])
    manufacturer = _get_field(row, FIELD_ALIASES["manufacturer"])
    manufacturer_code = _get_field(row, FIELD_ALIASES["manufacturer_code"])
    unit = _get_field(row, FIELD_ALIASES["unit"])
    packaging = _get_field(row, FIELD_ALIASES["packaging"])

    # Handle reference-type fields (expand to Description or resolve from map)
    if isinstance(brand, dict):
        brand = brand.get("Description", str(brand))
    if isinstance(manufacturer, dict):
        manufacturer = manufacturer.get("Description", str(manufacturer))
    if isinstance(unit, dict):
        unit = unit.get("Description", unit.get("Наименование", str(unit)))

    # Resolve category path from parent key
    category_id = _get_field(row, FIELD_ALIASES["category_id"])
    category_path = None
    empty_guid = "00000000-0000-0000-0000-000000000000"
    if category_id and category_id != empty_guid:
        if category_map:
            category_path = category_map.get(category_id, "")
        else:
            category_path = str(category_id)  # Will be resolved later

    # Build item
    return RawCatalogItem(
        product_id=str(onec_ref) if onec_ref else None,
        onec_ref=str(onec_ref) if onec_ref else None,
        code=str(code).strip() if code else None,
        article=str(article).strip() if article else None,
        name=str(name).strip(),
        full_name=str(full_name).strip() if full_name else None,
        brand=str(brand).strip() if brand else None,
        manufacturer=str(manufacturer).strip() if manufacturer else None,
        manufacturer_code=str(manufacturer_code).strip() if manufacturer_code else None,
        category_id=str(category_id) if category_id else None,
        category_path=category_path,
        unit=str(unit).strip() if unit else None,
        packaging=str(packaging).strip() if packaging else None,
        weight_value=_parse_float(_get_field(row, FIELD_ALIASES["weight_value"])),
        volume_value=_parse_float(_get_field(row, FIELD_ALIASES["volume_value"])),
        extra={k: v for k, v in row.items() if k not in _ALL_KNOWN_FIELDS},
    )


# Set of all known field names to filter extras
_ALL_KNOWN_FIELDS: set[str] = set()
for aliases in FIELD_ALIASES.values():
    _ALL_KNOWN_FIELDS.update(aliases)
_ALL_KNOWN_FIELDS.update({"DeletionMark", "IsFolder", "DataVersion", "Predefined", "PredefinedDataName"})


# ── Convenience function (backwards compatible) ─────────────────────────────


async def fetch_onec_catalog(
    base_url: str | None = None,
    username: str | None = None,
    password: str | None = None,
    endpoint: str | None = None,
    resource: str = DEFAULT_RESOURCE,
    page_size: int = DEFAULT_PAGE_SIZE,
    dry_run: bool = False,
) -> list[RawCatalogItem]:
    """Fetch entire catalog from 1C OData. High-level convenience function.

    If base_url/username/password not provided, reads from settings.
    """
    if base_url is None:
        from matcher.api.v1.settings import _onec_settings
        if not _onec_settings.enabled or not _onec_settings.base_url:
            raise ValueError("1C connection is not enabled. Configure in Settings → 1C.")
        base_url = _onec_settings.base_url
        username = _onec_settings.username
        password = _onec_settings.password
        endpoint = _onec_settings.catalog_endpoint or "/odata/standard.odata/"

    client = OneCODataClient(
        base_url=base_url,
        username=username or "",
        password=password or "",
        resource=resource,
        endpoint=endpoint or "/odata/standard.odata/",
        page_size=page_size,
    )

    if dry_run:
        count = await client.get_total_count()
        return [RawCatalogItem(name=f"[dry-run] {count} items available")]

    # First fetch the category map for resolving parent references
    logger.info("Fetching 1C category hierarchy...")
    category_map = await fetch_category_map(
        base_url=base_url,
        username=username or "",
        password=password or "",
        resource=resource,
        endpoint=endpoint or "/odata/standard.odata/",
    )
    logger.info("Loaded %d category groups from 1C", len(category_map))

    # Then fetch all items with the category map for path resolution
    items = await client.fetch_all()

    # Resolve category paths
    for item in items:
        if item.category_id and item.category_id in category_map:
            item.category_path = category_map[item.category_id]

    return items
