"""Regression tests for OFM_REGION_NAME / OFM_TOURISM_BASE_URL parametrization."""
from __future__ import annotations

import importlib

import server


def _instructions_text() -> str:
    """Return the FastMCP instructions string, regardless of attribute shape."""
    instr = getattr(server.mcp, "instructions", None)
    if instr is None:
        # Some FastMCP versions stash it on a settings object.
        settings = getattr(server.mcp, "settings", None)
        instr = getattr(settings, "instructions", None) if settings else None
    assert instr is not None, "could not locate FastMCP instructions on server.mcp"
    return instr


class TestRegionName:
    def test_defaults_to_south_tyrol(self):
        assert server.REGION_NAME == "South Tyrol"
        assert "South Tyrol" in _instructions_text()

    def test_env_var_override_takes_effect(self, monkeypatch):
        monkeypatch.setenv("OFM_REGION_NAME", "Trentino")
        importlib.reload(server)
        assert server.REGION_NAME == "Trentino"
        instr = _instructions_text()
        assert "Trentino" in instr
        assert "South Tyrol" not in instr

    def test_supports_multi_word_regions(self, monkeypatch):
        monkeypatch.setenv("OFM_REGION_NAME", "Province of Bolzano")
        importlib.reload(server)
        assert server.REGION_NAME == "Province of Bolzano"
        assert "Province of Bolzano" in _instructions_text()


class TestBaseUrl:
    def test_defaults_to_opendatahub(self):
        assert server.BASE_URL == "https://tourism.api.opendatahub.com"

    def test_env_var_override_takes_effect(self, monkeypatch):
        monkeypatch.setenv("OFM_TOURISM_BASE_URL", "https://example.test/api")
        importlib.reload(server)
        assert server.BASE_URL == "https://example.test/api"

    def test_trailing_slash_is_stripped(self, monkeypatch):
        monkeypatch.setenv("OFM_TOURISM_BASE_URL", "https://example.test/")
        importlib.reload(server)
        assert server.BASE_URL == "https://example.test"


class TestDefaultLanguage:
    def test_defaults_to_english(self):
        assert server.DEFAULT_LANGUAGE == "en"

    def test_env_var_override_takes_effect(self, monkeypatch):
        monkeypatch.setenv("OFM_DEFAULT_LANGUAGE", "de")
        importlib.reload(server)
        assert server.DEFAULT_LANGUAGE == "de"
