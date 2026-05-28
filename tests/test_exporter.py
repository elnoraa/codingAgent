"""Tests for chat export functionality."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator

import pytest

from src.exporter import export_as_markdown, export_as_json, _safe_filename


@pytest.fixture
def tmp_output() -> Iterator[str]:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def test_safe_filename_format() -> None:
    """Filename should match chat-export-YYYYMMDD-HHMMSS pattern."""
    name = _safe_filename()
    assert name.startswith("chat-export-")
    # Should have date-time suffix: YYYYMMDD-HHMMSS
    parts = name.split("chat-export-")
    assert len(parts) == 2
    suffix = parts[1]
    assert len(suffix) == 15  # 8 digits date + hyphen + 6 digits time
    assert suffix[8] == "-"  # hyphen between date and time


def test_export_as_markdown_creates_file(tmp_output: str) -> None:
    """Export should create a .md file."""
    messages: list[dict[str, object]] = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ]
    filepath = export_as_markdown(messages, mode="code", model="test-model", output_dir=tmp_output)
    assert os.path.isfile(filepath)
    assert filepath.endswith(".md")


def test_export_as_markdown_content(tmp_output: str) -> None:
    """Markdown output should contain mode, model, and messages."""
    messages: list[dict[str, object]] = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ]
    filepath = export_as_markdown(messages, mode="code", model="test-model", output_dir=tmp_output)
    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    assert "code" in content
    assert "test-model" in content
    assert "Hello" in content
    assert "Hi there" in content


def test_export_as_markdown_with_text_content(tmp_output: str) -> None:
    """String content should be rendered in the output."""
    messages: list[dict[str, object]] = [
        {"role": "user", "content": "Hello world"},
    ]
    filepath = export_as_markdown(messages, mode="code", model="m", output_dir=tmp_output)
    with open(filepath, encoding="utf-8") as f:
        content = f.read()
    assert "Hello world" in content


def test_export_as_markdown_with_tool_blocks(tmp_output: str) -> None:
    """Tool use and tool result blocks should be rendered."""
    messages: list[dict[str, object]] = [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Let me read the file."},
                {"type": "tool_use", "name": "read_file", "input": {"path": "test.py"}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "content": "file content here"},
            ],
        },
    ]
    filepath = export_as_markdown(messages, mode="code", model="m", output_dir=tmp_output)
    with open(filepath, encoding="utf-8") as f:
        content = f.read()
    assert "Let me read the file." in content
    assert "read_file" in content
    assert "file content here" in content


def test_export_as_json_creates_file(tmp_output: str) -> None:
    """Export should create a .json file."""
    messages: list[dict[str, object]] = [{"role": "user", "content": "Hello"}]
    filepath = export_as_json(messages, mode="code", model="test-model", output_dir=tmp_output)
    assert os.path.isfile(filepath)
    assert filepath.endswith(".json")


def test_export_as_json_content_structure(tmp_output: str) -> None:
    """JSON output should have expected top-level keys."""
    messages: list[dict[str, object]] = [{"role": "user", "content": "Hello"}]
    filepath = export_as_json(messages, mode="plan", model="m1", output_dir=tmp_output)
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    assert "exported_at" in data
    assert data["mode"] == "plan"
    assert data["model"] == "m1"
    assert data["message_count"] == 1
    assert len(data["messages"]) == 1


def test_export_as_json_truncates_long_results(tmp_output: str) -> None:
    """Tool results longer than 500 chars should be truncated."""
    long_content = "x" * 1000
    messages: list[dict[str, object]] = [
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "content": long_content},
            ],
        },
    ]
    filepath = export_as_json(messages, mode="code", model="m", output_dir=tmp_output)
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    result_content = data["messages"][0]["content"][0]["content"]
    assert len(result_content) < len(long_content)
    assert result_content.endswith("[truncated]")


def test_export_empty_conversation(tmp_output: str) -> None:
    """Export with empty messages list should still produce a valid file."""
    filepath = export_as_markdown([], mode="code", model="m", output_dir=tmp_output)
    assert os.path.isfile(filepath)

    filepath2 = export_as_json([], mode="plan", model="m", output_dir=tmp_output)
    assert os.path.isfile(filepath2)

    with open(filepath2, encoding="utf-8") as f:
        data = json.load(f)
    assert data["message_count"] == 0
    assert data["messages"] == []
