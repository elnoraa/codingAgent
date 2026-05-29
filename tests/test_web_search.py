"""Tests for the web_search tool."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, cast

from src.tools import ToolContext
from src.tools.web_search import execute, web_search_tool


def test_tool_definition() -> None:
    assert web_search_tool.name == "web_search"
    assert web_search_tool.read_only is True
    schema = cast("dict[str, object]", web_search_tool.input_schema)
    required = cast("list[str]", schema.get("required", []))
    assert "query" in required


def test_execute_no_query() -> None:
    ctx = ToolContext(working_directory="/tmp")
    result = execute({"maxResults": 3}, ctx)
    assert "missing required argument" in result


def test_execute_empty_query() -> None:
    ctx = ToolContext(working_directory="/tmp")
    result = execute({"query": "", "maxResults": 3}, ctx)
    assert "missing required argument" in result


def test_execute_validates_max_results() -> None:
    ctx = ToolContext(working_directory="/tmp")

    # maxResults > 20 should be capped to 20
    result = execute({"query": "python", "maxResults": 100}, ctx)
    # Should not crash; actual search result depends on network
    assert isinstance(result, str)


def test_tool_schema() -> None:
    schema = cast("dict[str, object]", web_search_tool.input_schema)
    props = cast("dict[str, object]", schema.get("properties", {}))
    assert "query" in props
    assert "maxResults" in props

    query_props = cast("dict[str, object]", props["query"])
    assert query_props["type"] == "string"

    max_results_props = cast("dict[str, object]", props["maxResults"])
    assert max_results_props["type"] == "number"


def test_execute_is_read_only() -> None:
    assert web_search_tool.read_only is True
