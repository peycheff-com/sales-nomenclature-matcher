from __future__ import annotations

import pytest

from matcher.pipeline.overrides import OverrideResult, check_supplier_override


class _Result:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _Session:
    def __init__(self, row=None) -> None:
        self.row = row
        self.calls = []

    async def execute(self, statement, params):
        self.calls.append((str(statement), params))
        return _Result(self.row)


@pytest.mark.asyncio
async def test_check_supplier_override_returns_none_without_supplier_id():
    session = _Session(row=("p1", "exact", 1.0))

    result = await check_supplier_override(None, "raw", "norm", "A-1", session)

    assert result is None
    assert session.calls == []


@pytest.mark.asyncio
async def test_check_supplier_override_maps_row_and_defaults_missing_confidence():
    session = _Session(row=("p1", "approved", None))

    result = await check_supplier_override("s1", "raw", "norm", None, session)

    assert result == OverrideResult(product_id="p1", mapping_type="approved", confidence=0.995)
    _, params = session.calls[0]
    assert params == {
        "supplier_id": "s1",
        "raw_text": "raw",
        "article_hint": "",
        "normalized_text": "norm",
    }


@pytest.mark.asyncio
async def test_check_supplier_override_returns_none_without_row():
    session = _Session(row=None)

    assert await check_supplier_override("s1", "raw", "norm", "A-1", session) is None
