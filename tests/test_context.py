"""Tests for the inter-step context and its placeholder resolution."""

from opencompute.core.runtime import _resolve


def test_resolve_bare_capability_uses_primary_field():
    memory = {"research": {"summary": "here is the finding", "sources": []}}
    assert _resolve("$research", memory) == "here is the finding"


def test_resolve_nested_field():
    memory = {"http": {"text": "<html></html>", "status_code": 200}}
    assert _resolve("$http.status_code", memory) == 200
    assert _resolve("$http.text", memory) == "<html></html>"


def test_resolve_inside_dict():
    memory = {"research": {"summary": "finding text"}}
    inputs = {"path": "out.md", "content": "$research"}
    out = _resolve(inputs, memory)
    assert out["content"] == "finding text"
    assert out["path"] == "out.md"


def test_resolve_leaves_unknown_reference_untouched():
    assert _resolve("$doesnotexist", {}) == "$doesnotexist"
    assert _resolve("$research.missing", {"research": {}}) == "$research.missing"


def test_resolve_handles_lists_and_plain_values():
    memory = {"research": {"summary": "s"}}
    assert _resolve(["a", "$research", 3], memory) == ["a", "s", 3]
    assert _resolve(42, memory) == 42
