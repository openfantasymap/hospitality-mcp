"""Shared fixtures for the hospitality-mcp test suite.

Every test starts with `server` freshly reloaded from default-env state and
with the pooled httpx client reset, so env-var-override and HTTP-mocked tests
cannot leak state into each other.
"""
from __future__ import annotations

import importlib

import pytest

import server


_OFM_ENV_VARS = (
    "OFM_REGION_NAME",
    "OFM_TOURISM_BASE_URL",
    "OFM_DEFAULT_LANGUAGE",
)


@pytest.fixture(autouse=True)
def fresh_server(monkeypatch):
    for var in _OFM_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    importlib.reload(server)
    server._client = None
    yield
    server._client = None
