"""Pure-logic tests for the server's helper functions."""
from __future__ import annotations

import server


# -------------------- _clean ---------------------------------------------
class TestClean:
    def test_drops_none_values(self):
        assert server._clean({"a": 1, "b": None, "c": "x"}) == {"a": 1, "c": "x"}

    def test_normalizes_booleans(self):
        assert server._clean({"x": True, "y": False}) == {"x": "true", "y": "false"}

    def test_joins_lists_with_commas(self):
        assert server._clean({"x": [1, 2, 3]}) == {"x": "1,2,3"}

    def test_joins_tuples_with_commas(self):
        assert server._clean({"x": ("a", "b")}) == {"x": "a,b"}

    def test_drops_empty_lists_and_tuples(self):
        assert server._clean({"x": [], "y": (), "z": 1}) == {"z": 1}

    def test_passes_through_scalars(self):
        assert server._clean({"s": "hi", "n": 7, "f": 1.5}) == {
            "s": "hi", "n": 7, "f": 1.5,
        }

    def test_empty_input_returns_empty(self):
        assert server._clean({}) == {}


# -------------------- _fields --------------------------------------------
class TestFields:
    def test_uses_default_when_override_is_none(self):
        assert server._fields("Id,Name.{lang}", None, "en") == "Id,Name.en"

    def test_empty_string_override_means_all_fields(self):
        # An override of "" is the documented signal for "return all fields",
        # which translates to dropping the `fields` query param entirely.
        assert server._fields("Id,Name.{lang}", "", "en") is None

    def test_non_empty_override_replaces_default(self):
        assert server._fields("Id,Name.{lang}", "Custom,Field", "en") == "Custom,Field"

    def test_lang_placeholder_is_substituted_in_override(self):
        assert server._fields("Id", "Detail.{lang}", "de") == "Detail.de"

    def test_lang_placeholder_is_substituted_in_default(self):
        assert server._fields("Detail.{lang},Loc.{lang}", None, "it") == "Detail.it,Loc.it"
