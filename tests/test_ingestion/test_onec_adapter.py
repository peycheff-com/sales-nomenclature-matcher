from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from matcher.ingestion import onec_adapter
from matcher.ingestion.base import RawCatalogItem
from matcher.ingestion.onec_adapter import OneCODataClient


class _FakeHttpClient:
    responses: list[object] = []
    error: Exception | None = None
    calls: list[dict] = []

    def __init__(self, *args, **kwargs) -> None:
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url: str, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if self.error:
            raise self.error
        return self.responses.pop(0)


def _response(
    *,
    status_code: int = 200,
    text: str = "",
    json_data: object | None = None,
    raise_error: Exception | None = None,
):
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    response.json.return_value = json_data if json_data is not None else {}
    response.raise_for_status = MagicMock()
    if raise_error:
        response.raise_for_status.side_effect = raise_error
    return response


@pytest.fixture(autouse=True)
def reset_fake_client():
    _FakeHttpClient.responses = []
    _FakeHttpClient.error = None
    _FakeHttpClient.calls = []
    yield


class TestOneCODataClient:
    def test_init_builds_service_root_auth_and_resource_url(self):
        client = OneCODataClient(
            base_url="http://onec.local/base/",
            username="user",
            password="pass",
            endpoint="/odata/",
            resource="Catalog_Items",
            page_size=2,
            timeout=3.0,
            select_fields=["Code"],
            filter_expr=None,
        )

        assert client.service_root == "http://onec.local/base/odata/"
        assert client.auth == ("user", "pass")
        assert client._resource_url() == "http://onec.local/base/odata/Catalog_Items"
        assert client.filter_expr == "DeletionMark eq false and IsFolder eq false"

    @pytest.mark.asyncio
    async def test_health_check_success_and_error_paths(self):
        client = OneCODataClient("http://onec.local", endpoint="/odata/")
        _FakeHttpClient.responses = [
            _response(status_code=200),
            _response(json_data={"value": [{"Code": "1"}]}),
        ]

        with patch("matcher.ingestion.onec_adapter.httpx.AsyncClient", _FakeHttpClient):
            result = await client.health_check()

        assert result == {"status": "ok", "metadata_ok": True, "sample_records": 1}
        assert _FakeHttpClient.calls[0]["url"] == "http://onec.local/odata/$metadata"

        _FakeHttpClient.error = RuntimeError("offline")
        with patch("matcher.ingestion.onec_adapter.httpx.AsyncClient", _FakeHttpClient):
            result = await client.health_check()
        assert result["status"] == "error"
        assert "Metadata unreachable" in result["detail"]

        _FakeHttpClient.error = None
        _FakeHttpClient.responses = [
            _response(status_code=500),
            _response(
                raise_error=httpx.HTTPStatusError(
                    "bad", request=MagicMock(), response=MagicMock()
                )
            ),
        ]
        with patch("matcher.ingestion.onec_adapter.httpx.AsyncClient", _FakeHttpClient):
            result = await client.health_check()
        assert result["status"] == "error"
        assert result["metadata_ok"] is False
        assert "Catalog query failed" in result["detail"]

    @pytest.mark.asyncio
    async def test_metadata_count_and_page_fetching(self):
        xml = """<?xml version="1.0"?>
        <edmx:Edmx xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
          <edmx:DataServices>
            <Schema xmlns="http://schemas.microsoft.com/ado/2008/09/edm">
              <EntityType Name="Catalog_НоменклатураType">
                <Property Name="Code" />
                <Property Name="Description" />
              </EntityType>
            </Schema>
          </edmx:DataServices>
        </edmx:Edmx>
        """
        client = OneCODataClient("http://onec.local", endpoint="/odata/", page_size=2)
        _FakeHttpClient.responses = [_response(text=xml)]
        with patch("matcher.ingestion.onec_adapter.httpx.AsyncClient", _FakeHttpClient):
            assert await client.get_metadata_fields() == ["Code", "Description"]

        _FakeHttpClient.responses = [_response(text=" 42 ")]
        with patch("matcher.ingestion.onec_adapter.httpx.AsyncClient", _FakeHttpClient):
            assert await client.get_total_count() == 42
        assert _FakeHttpClient.calls[-1]["params"]["$filter"] == client.filter_expr

        _FakeHttpClient.responses = [_response(json_data={"value": [{"Code": "1"}]})]
        with patch("matcher.ingestion.onec_adapter.httpx.AsyncClient", _FakeHttpClient):
            assert await client.fetch_page(skip=5) == [{"Code": "1"}]
        params = _FakeHttpClient.calls[-1]["params"]
        assert params["$top"] == "2"
        assert params["$skip"] == "5"
        assert "$select" in params

        _FakeHttpClient.responses = [_response(json_data={"d": {"results": [{"Code": "2"}]}})]
        with patch("matcher.ingestion.onec_adapter.httpx.AsyncClient", _FakeHttpClient):
            assert await client.fetch_page() == [{"Code": "2"}]

        _FakeHttpClient.responses = [_response(json_data=[{"Code": "3"}])]
        with patch("matcher.ingestion.onec_adapter.httpx.AsyncClient", _FakeHttpClient):
            assert await client.fetch_page() == [{"Code": "3"}]

        _FakeHttpClient.responses = [_response(json_data="unexpected")]
        with patch("matcher.ingestion.onec_adapter.httpx.AsyncClient", _FakeHttpClient):
            assert await client.fetch_page() == []

    @pytest.mark.asyncio
    async def test_fetch_all_and_iterate_pages(self):
        client = OneCODataClient("http://onec.local", page_size=2)
        client.get_total_count = AsyncMock(return_value=3)
        client.fetch_page = AsyncMock(
            side_effect=[
                [
                    {"Ref_Key": "r1", "Code": "1", "Description": "Item 1"},
                    {"Ref_Key": "folder", "Description": "Folder", "IsFolder": True},
                ],
                [{"Ref_Key": "r2", "Code": "2", "Description": "Item 2"}],
            ]
        )
        progress = MagicMock()

        items = await client.fetch_all(progress_callback=progress)

        assert [item.name for item in items] == ["Item 1", "Item 2"]
        progress.assert_any_call(fetched=2, total=3)
        progress.assert_any_call(fetched=3, total=3)

        client.get_total_count = AsyncMock(return_value=5)
        client.fetch_page = AsyncMock(side_effect=[[{"Description": "Item"}], []])

        items = [item async for item in client.fetch_iter()]

        assert [item.name for item in items] == ["Item"]

        client.get_total_count = AsyncMock(return_value=2)
        client.fetch_page = AsyncMock(return_value=[])

        assert await client.fetch_all() == []

    @pytest.mark.asyncio
    async def test_fetch_category_map_resolves_nested_paths(self):
        _FakeHttpClient.responses = [
            _response(
                json_data={
                    "value": [
                        {
                            "Ref_Key": "root",
                            "Description": "Root",
                            "Родитель_Key": "00000000-0000-0000-0000-000000000000",
                        },
                        {"Ref_Key": "child", "Description": "Child", "Родитель_Key": "root"},
                    ]
                }
            )
        ]

        with patch("matcher.ingestion.onec_adapter.httpx.AsyncClient", _FakeHttpClient):
            result = await onec_adapter.fetch_category_map(
                "http://onec.local", username="u", password="p", endpoint="/odata/"
            )

        assert result == {"root": "Root", "child": "Root/Child"}
        assert _FakeHttpClient.calls[0]["auth"] == ("u", "p")


class TestOneCMapping:
    def test_field_helpers(self):
        assert onec_adapter._get_field({"a": "", "b": "value"}, ["a", "b"]) == "value"
        assert onec_adapter._get_field({"a": ""}, ["a"]) is None
        assert onec_adapter._resolve_ref_field({"Brand": {"Description": "SKF"}}, "Brand") == "SKF"
        assert onec_adapter._resolve_ref_field({"BrandName": "SKF"}, "Brand", "BrandName") == "SKF"
        assert onec_adapter._resolve_ref_field({"Brand": "guid"}, "Brand") is None
        assert onec_adapter._parse_float("1,25") == 1.25
        assert onec_adapter._parse_float("bad") is None
        assert onec_adapter._parse_float(None) is None

    def test_map_onec_odata_item_skips_non_products_and_maps_variants(self):
        assert (
            onec_adapter.map_onec_odata_item({"Description": "Deleted", "DeletionMark": True})
            is None
        )
        assert onec_adapter.map_onec_odata_item({"Description": "Folder", "IsFolder": True}) is None
        assert onec_adapter.map_onec_odata_item({"Description": "   "}) is None

        item = onec_adapter.map_onec_odata_item(
            {
                "Ref_Key": "r1",
                "Code": " C1 ",
                "Description": " Bearing ",
                "НаименованиеПолное": " Bearing full ",
                "Артикул": " 6205 ",
                "Бренд": {"Description": "SKF"},
                "Производитель": {"Description": "SKF Group"},
                "КодПроизводителя": " M6205 ",
                "ЕдиницаИзмерения": {"Наименование": "pcs"},
                "Родитель_Key": "cat_1",
                "Упаковка": "box",
                "Вес": "1,2",
                "Объем": "bad",
                "CustomField": "kept",
                "DataVersion": "ignored",
            },
            category_map={"cat_1": "Root/Bearings"},
        )

        assert item == RawCatalogItem(
            product_id="r1",
            onec_ref="r1",
            code="C1",
            article="6205",
            name="Bearing",
            full_name="Bearing full",
            brand="SKF",
            manufacturer="SKF Group",
            manufacturer_code="M6205",
            category_id="cat_1",
            category_path="Root/Bearings",
            unit="pcs",
            packaging="box",
            weight_value=1.2,
            volume_value=None,
            extra={"CustomField": "kept"},
        )

    def test_map_onec_odata_item_uses_category_id_when_map_absent_or_empty_guid(self):
        item = onec_adapter.map_onec_odata_item(
            {"id": "r2", "Name": "Item", "Parent_Key": "cat_2", "Brand": "Brand"}
        )
        assert item is not None
        assert item.category_path == "cat_2"
        assert item.brand == "Brand"

        empty_guid = "00000000-0000-0000-0000-000000000000"
        item = onec_adapter.map_onec_odata_item(
            {"id": "r3", "Name": "Item", "Parent_Key": empty_guid}
        )
        assert item is not None
        assert item.category_path is None


class TestFetchOneCCatalog:
    @pytest.mark.asyncio
    async def test_fetch_onec_catalog_requires_enabled_settings(self):
        with patch("matcher.api.v1.settings._onec_settings") as onec_settings:
            onec_settings.enabled = False
            onec_settings.base_url = ""
            with pytest.raises(ValueError, match="not enabled"):
                await onec_adapter.fetch_onec_catalog()

    @pytest.mark.asyncio
    async def test_fetch_onec_catalog_reads_runtime_settings_when_base_url_omitted(self):
        item = RawCatalogItem(name="Item")
        client = SimpleNamespace(fetch_all=AsyncMock(return_value=[item]))
        onec_settings = SimpleNamespace(
            enabled=True,
            base_url="http://settings-onec.local",
            username="settings-user",
            password="settings-pass",
            catalog_endpoint="/settings-odata/",
        )

        with (
            patch("matcher.api.v1.settings._onec_settings", onec_settings),
            patch("matcher.ingestion.onec_adapter.OneCODataClient", return_value=client) as ctor,
            patch(
                "matcher.ingestion.onec_adapter.fetch_category_map", new_callable=AsyncMock
            ) as cats,
        ):
            cats.return_value = {}
            result = await onec_adapter.fetch_onec_catalog()

        assert result == [item]
        assert ctor.call_args.kwargs["base_url"] == "http://settings-onec.local"
        assert ctor.call_args.kwargs["username"] == "settings-user"
        assert ctor.call_args.kwargs["password"] == "settings-pass"
        assert ctor.call_args.kwargs["endpoint"] == "/settings-odata/"

    @pytest.mark.asyncio
    async def test_fetch_onec_catalog_dry_run_returns_count_marker(self):
        client = SimpleNamespace(get_total_count=AsyncMock(return_value=17))

        with patch("matcher.ingestion.onec_adapter.OneCODataClient", return_value=client):
            result = await onec_adapter.fetch_onec_catalog(
                base_url="http://onec.local", endpoint="/odata/", dry_run=True
            )

        assert result == [RawCatalogItem(name="[dry-run] 17 items available")]

    @pytest.mark.asyncio
    async def test_fetch_onec_catalog_resolves_category_paths_from_map(self):
        item = RawCatalogItem(name="Item", category_id="cat_1")
        client = SimpleNamespace(fetch_all=AsyncMock(return_value=[item]))

        with (
            patch("matcher.ingestion.onec_adapter.OneCODataClient", return_value=client),
            patch(
                "matcher.ingestion.onec_adapter.fetch_category_map", new_callable=AsyncMock
            ) as cats,
        ):
            cats.return_value = {"cat_1": "Root/Bearings"}
            result = await onec_adapter.fetch_onec_catalog(
                base_url="http://onec.local",
                username="u",
                password="p",
                endpoint="/odata/",
                resource="Catalog_Items",
                page_size=10,
            )

        assert result == [item]
        assert item.category_path == "Root/Bearings"
        cats.assert_awaited_once_with(
            base_url="http://onec.local",
            username="u",
            password="p",
            resource="Catalog_Items",
            endpoint="/odata/",
        )
