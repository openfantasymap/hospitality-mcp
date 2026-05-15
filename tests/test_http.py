"""HTTP-mocked tests for representative tools.

Uses respx to intercept httpx calls — no real network traffic. The 13 search/
detail tools all share the same `_get` plumbing, so we cover one representative
of each pattern (post-processing, parameter normalization, escape hatch, error
propagation) rather than every endpoint individually.
"""
from __future__ import annotations

import httpx
import pytest
import respx

import server


BASE = "https://tourism.api.opendatahub.com"


class TestResolveLocation:
    """resolve_location has the most non-trivial post-processing in the codebase."""

    @respx.mock
    async def test_filters_by_substring_case_insensitively(self):
        respx.get(f"{BASE}/v1/Location").mock(
            return_value=httpx.Response(200, json=[
                {"id": "AAA", "typ": "tvs", "name": "Val Gardena"},
                {"id": "BBB", "typ": "mun", "name": "Selva di Val Gardena"},
                {"id": "CCC", "typ": "mun", "name": "Bolzano"},
            ])
        )
        result = await server.resolve_location("val gardena")
        names = [r["name"] for r in result]
        assert "Bolzano" not in names
        assert "Val Gardena" in names
        assert "Selva di Val Gardena" in names

    @respx.mock
    async def test_exact_match_sorted_first(self):
        respx.get(f"{BASE}/v1/Location").mock(
            return_value=httpx.Response(200, json=[
                {"id": "BBB", "typ": "mun", "name": "Selva di Val Gardena"},
                {"id": "AAA", "typ": "tvs", "name": "Val Gardena"},
            ])
        )
        result = await server.resolve_location("Val Gardena")
        assert result[0]["name"] == "Val Gardena"
        assert result[0]["locfilter_token"] == "tvsAAA"

    @respx.mock
    async def test_builds_locfilter_token_from_type_and_id(self):
        respx.get(f"{BASE}/v1/Location").mock(
            return_value=httpx.Response(200, json=[
                {"id": "XYZ123", "typ": "reg", "name": "Dolomites"},
            ])
        )
        result = await server.resolve_location("dolomites")
        assert result[0] == {
            "name": "Dolomites",
            "type": "reg",
            "id": "XYZ123",
            "locfilter_token": "regXYZ123",
        }

    @respx.mock
    async def test_passes_default_language(self):
        route = respx.get(f"{BASE}/v1/Location").mock(
            return_value=httpx.Response(200, json=[])
        )
        await server.resolve_location("anywhere")
        assert route.calls.last.request.url.params["language"] == "en"

    @respx.mock
    async def test_explicit_language_overrides_default(self):
        route = respx.get(f"{BASE}/v1/Location").mock(
            return_value=httpx.Response(200, json=[])
        )
        await server.resolve_location("anywhere", language="de")
        assert route.calls.last.request.url.params["language"] == "de"


class TestSearchAccommodations:
    """Representative search tool — verifies param-cleaning & projection plumbing."""

    @respx.mock
    async def test_passes_filters_and_normalizes_bool(self):
        route = respx.get(f"{BASE}/v1/Accommodation").mock(
            return_value=httpx.Response(200, json={"Items": [], "TotalResults": 0})
        )
        await server.search_accommodations(
            locfilter="tvsAAA",
            typefilter="1",
            bookable_only=True,
            pagenumber=2,
            pagesize=5,
        )
        qp = route.calls.last.request.url.params
        assert qp["locfilter"] == "tvsAAA"
        assert qp["typefilter"] == "1"
        assert qp["bookablefilter"] == "true"
        assert qp["pagenumber"] == "2"
        assert qp["pagesize"] == "5"
        assert qp["removenullvalues"] == "true"

    @respx.mock
    async def test_none_filters_are_dropped_from_query(self):
        route = respx.get(f"{BASE}/v1/Accommodation").mock(
            return_value=httpx.Response(200, json={"Items": []})
        )
        await server.search_accommodations(locfilter="tvsAAA")
        qp = route.calls.last.request.url.params
        # None-valued kwargs must not appear at all
        assert "categoryfilter" not in qp
        assert "themefilter" not in qp
        assert "latitude" not in qp
        assert "radius" not in qp
        # But the always-present ones do
        assert qp["locfilter"] == "tvsAAA"
        assert qp["language"] == "en"

    @respx.mock
    async def test_default_field_projection_is_applied(self):
        route = respx.get(f"{BASE}/v1/Accommodation").mock(
            return_value=httpx.Response(200, json={"Items": []})
        )
        await server.search_accommodations(locfilter="tvsAAA")
        fields = route.calls.last.request.url.params["fields"]
        assert "AccoDetail.en" in fields
        assert "{lang}" not in fields  # placeholder must be substituted

    @respx.mock
    async def test_explicit_empty_fields_drops_projection(self):
        # fields="" is the documented "return everything" signal.
        route = respx.get(f"{BASE}/v1/Accommodation").mock(
            return_value=httpx.Response(200, json={"Items": []})
        )
        await server.search_accommodations(locfilter="tvsAAA", fields="")
        assert "fields" not in route.calls.last.request.url.params


class TestGetDetail:
    @respx.mock
    async def test_routes_entity_type_to_right_endpoint(self):
        route = respx.get(f"{BASE}/v1/Accommodation/abc-123").mock(
            return_value=httpx.Response(200, json={"Id": "abc-123"})
        )
        result = await server.get_detail("accommodation", "abc-123")
        assert route.called
        assert result == {"Id": "abc-123"}

    @respx.mock
    async def test_poi_alias_resolves_to_activitypoi_endpoint(self):
        route = respx.get(f"{BASE}/v1/ODHActivityPoi/poi-1").mock(
            return_value=httpx.Response(200, json={"Id": "poi-1"})
        )
        result = await server.get_detail("poi", "poi-1")
        assert route.called
        assert result == {"Id": "poi-1"}


class TestRawApiCall:
    @respx.mock
    async def test_forwards_to_arbitrary_v1_path(self):
        route = respx.get(f"{BASE}/v1/SkiArea").mock(
            return_value=httpx.Response(200, json=[{"Id": "ski-1"}])
        )
        result = await server.raw_api_call("/v1/SkiArea", {"pagesize": 5})
        assert route.called
        assert result == [{"Id": "ski-1"}]
        assert route.calls.last.request.url.params["pagesize"] == "5"

    @respx.mock
    async def test_no_params_works(self):
        route = respx.get(f"{BASE}/v1/SkiArea").mock(
            return_value=httpx.Response(200, json=[])
        )
        result = await server.raw_api_call("/v1/SkiArea")
        assert route.called
        assert result == []


class TestErrorPropagation:
    @respx.mock
    async def test_http_error_status_raises(self):
        respx.get(f"{BASE}/v1/Accommodation").mock(
            return_value=httpx.Response(500, text="boom")
        )
        with pytest.raises(httpx.HTTPStatusError):
            await server.search_accommodations(locfilter="tvsAAA")

    @respx.mock
    async def test_empty_body_returns_none(self):
        respx.get(f"{BASE}/v1/Accommodation").mock(
            return_value=httpx.Response(200, content=b"")
        )
        result = await server.search_accommodations(locfilter="tvsAAA")
        assert result is None
