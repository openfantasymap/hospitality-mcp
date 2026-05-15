"""Tests for input-validation errors that must trigger before any HTTP call."""
from __future__ import annotations

import pytest

import server


class TestGetDetail:
    async def test_rejects_unknown_entity_type(self):
        with pytest.raises(ValueError, match="Unknown entity_type"):
            await server.get_detail("not_an_entity", "abc")

    async def test_error_message_lists_valid_entities(self):
        with pytest.raises(ValueError) as exc:
            await server.get_detail("wat", "abc")
        msg = str(exc.value)
        for valid in ("accommodation", "event", "trip", "venue", "skiarea"):
            assert valid in msg


class TestListFilterOptions:
    async def test_rejects_unknown_kind(self):
        with pytest.raises(ValueError, match="Unknown kind"):
            await server.list_filter_options("not_a_kind")

    async def test_error_message_lists_valid_kinds(self):
        with pytest.raises(ValueError) as exc:
            await server.list_filter_options("wat")
        msg = str(exc.value)
        for valid in ("accommodation_types", "event_topics", "venue_types"):
            assert valid in msg


class TestRawApiCall:
    async def test_rejects_path_without_v1_prefix(self):
        with pytest.raises(ValueError, match="must start with"):
            await server.raw_api_call("/v2/Accommodation")

    async def test_rejects_relative_path(self):
        with pytest.raises(ValueError, match="must start with"):
            await server.raw_api_call("Accommodation")

    async def test_rejects_empty_path(self):
        with pytest.raises(ValueError, match="must start with"):
            await server.raw_api_call("")


class TestRegisteredToolSurface:
    """Sanity-check that every documented tool is present on the module.

    The README and the slide deck both promise '13 curated planning tools';
    if a tool gets renamed or accidentally removed, this test fails fast.
    """

    EXPECTED = (
        "resolve_location",
        "search_accommodations",
        "check_accommodation_availability",
        "search_activities_and_pois",
        "search_events",
        "search_trips",
        "search_articles",
        "search_venues",
        "get_weather_forecast",
        "get_detail",
        "list_filter_options",
        "list_tags",
        "raw_api_call",
    )

    def test_all_thirteen_tools_present(self):
        assert len(self.EXPECTED) == 13
        for name in self.EXPECTED:
            assert hasattr(server, name), f"missing tool: {name}"
            assert callable(getattr(server, name)), f"{name} is not callable"
