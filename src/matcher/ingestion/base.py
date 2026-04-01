from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator, Protocol


@dataclass
class RawCatalogItem:
    """Raw item from any ingestion source before transformation."""
    product_id: str | None = None
    onec_ref: str | None = None
    code: str | None = None
    article: str | None = None
    name: str = ""
    full_name: str | None = None
    brand: str | None = None
    manufacturer: str | None = None
    manufacturer_code: str | None = None
    category_id: str | None = None
    category_path: str | None = None
    unit: str | None = None
    packaging: str | None = None
    size_value: float | None = None
    size_unit: str | None = None
    weight_value: float | None = None
    weight_unit: str | None = None
    volume_value: float | None = None
    volume_unit: str | None = None
    attributes: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)


class IngestAdapter(Protocol):
    """Protocol for catalog data sources."""

    async def fetch_items(self) -> AsyncIterator[RawCatalogItem]:
        """Yield raw catalog items from the source."""
        ...

    async def health_check(self) -> bool:
        """Check if the data source is reachable."""
        ...
