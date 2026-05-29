"""Tests for the diagram rendering module."""

from __future__ import annotations

import pytest

from src.diagrams import (
    extract_mermaid_blocks,
    get_mermaid_url,
    render_diagram_ascii,
    process_mermaid_blocks,
    MERMAID_BLOCK_RE,
)


class TestExtractMermaidBlocks:
    def test_single_block(self) -> None:
        text = "Some text\n```mermaid\ngraph TD\nA-->B\n```\nmore text"
        blocks = extract_mermaid_blocks(text)
        assert len(blocks) == 1
        assert blocks[0]["code"] == "graph TD\nA-->B"

    def test_no_block(self) -> None:
        text = "Just plain text with no mermaid blocks."
        blocks = extract_mermaid_blocks(text)
        assert blocks == []

    def test_multiple_blocks(self) -> None:
        text = (
            "```mermaid\ngraph LR\nA-->B\n```\n"
            "text\n"
            "```mermaid\nsequenceDiagram\nA->>B: Hi\n```"
        )
        blocks = extract_mermaid_blocks(text)
        assert len(blocks) == 2
        assert "graph LR" in blocks[0]["code"]
        assert "sequenceDiagram" in blocks[1]["code"]

    def test_empty_block(self) -> None:
        text = "```mermaid\n```"
        blocks = extract_mermaid_blocks(text)
        assert len(blocks) == 1
        assert blocks[0]["code"] == ""

    def test_block_positions(self) -> None:
        text = "prefix\n```mermaid\ngraph TD\nA-->B\n```\nsuffix"
        blocks = extract_mermaid_blocks(text)
        assert len(blocks) == 1
        # Verify positions
        assert text[blocks[0]["start"]:blocks[0]["end"]] == "```mermaid\ngraph TD\nA-->B\n```"


class TestGetMermaidUrl:
    def test_returns_string(self) -> None:
        url = get_mermaid_url("graph TD; A-->B;")
        assert isinstance(url, str)
        assert url.startswith("https://mermaid.ink/img/")
        assert len(url) > 30

    def test_url_encodes_diagram(self) -> None:
        code = "graph LR; A-->B;"
        url = get_mermaid_url(code)
        # URL should contain a base64-like component after the base URL
        query_part = url[len("https://mermaid.ink/img/"):]
        assert len(query_part) > 5

    def test_different_inputs_produce_different_urls(self) -> None:
        url1 = get_mermaid_url("graph TD; A-->B;")
        url2 = get_mermaid_url("graph TD; C-->D;")
        assert url1 != url2


class TestRenderDiagramAscii:
    def test_flowchart(self) -> None:
        code = "graph TD\nA-->B\nB-->C"
        result = render_diagram_ascii(code)
        assert "FLOWCHART DIAGRAM" in result
        assert "[A]" in result
        assert "[B]" in result

    def test_simple_arrow(self) -> None:
        code = "A-->B"
        result = render_diagram_ascii(code)
        assert "[A]" in result
        assert "[B]" in result
        assert "──▶" in result

    def test_empty_lines_skipped(self) -> None:
        code = "\n\nA-->B\n\n"
        result = render_diagram_ascii(code)
        assert "[A]" in result

    def test_class_def_skipped(self) -> None:
        code = "classDef someClass fill:#f96;\nA-->B"
        result = render_diagram_ascii(code)
        # classDef lines are skipped in ASCII rendering
        assert "someClass" not in result


class TestProcessMermaidBlocks:
    def test_no_mermaid_blocks(self) -> None:
        text = "Just plain text."
        result = process_mermaid_blocks(text)
        assert result == text

    def test_replaces_mermaid_block(self) -> None:
        text = "Here is a diagram:\n```mermaid\ngraph TD\nA-->B\n```\nDone."
        result = process_mermaid_blocks(text)
        assert "Mermaid Diagram" in result
        assert "mermaid.ink" in result
        assert "```mermaid" not in result

    def test_preserves_surrounding_text(self) -> None:
        prefix = "Before."
        diagram = "```mermaid\ngraph TD\nA-->B\n```"
        suffix = "After."
        text = f"{prefix}\n{diagram}\n{suffix}"
        result = process_mermaid_blocks(text)
        assert "Before." in result
        assert "After." in result

    def test_ascii_rendering_appears(self) -> None:
        text = "```mermaid\ngraph TD\nA-->B\n```"
        result = process_mermaid_blocks(text)
        assert "[A]" in result or "FLOWCHART" in result


def test_regex_pattern() -> None:
    """Verify the regex pattern matches various mermaid block formats."""
    assert MERMAID_BLOCK_RE.search("```mermaid\ngraph TD\n```")
    assert MERMAID_BLOCK_RE.search("text\n```mermaid\nsequenceDiagram\nA->B\n```\nmore")
    assert not MERMAID_BLOCK_RE.search("```mermaid```")  # No newline content
    assert not MERMAID_BLOCK_RE.search("```python\nprint('hello')\n```")
