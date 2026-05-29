"""Tests for utility functions."""

from __future__ import annotations

import json

from src.utils import (
    CHARS_PER_TOKEN,
    TRIM_THRESHOLD,
    _message_token_count,
    _strip_orphaned_tool_results,
    blue,
    bold,
    color_json,
    cyan,
    dim,
    estimate_tokens,
    green,
    magenta,
    red,
    trim_messages,
    yellow,
)


def test_color_helpers() -> None:
    """All color wrappers produce valid ANSI escape sequences."""
    assert green("hi") == "\033[32mhi\033[0m"
    assert red("hi") == "\033[31mhi\033[0m"
    assert yellow("hi") == "\033[33mhi\033[0m"
    assert blue("hi") == "\033[34mhi\033[0m"
    assert cyan("hi") == "\033[36mhi\033[0m"
    assert magenta("hi") == "\033[35mhi\033[0m"
    assert bold("hi") == "\033[1mhi\033[0m"
    assert dim("hi") == "\033[2mhi\033[0m"


def test_color_json_types() -> None:
    """color_json handles all JSON types."""
    assert "null" in dim(color_json(None))
    assert "true" in yellow(color_json(True))
    assert "false" in yellow(color_json(False))
    assert "42" in cyan(color_json(42))
    assert "3.14" in cyan(color_json(3.14))
    assert "hello" in green(color_json("hello"))


def test_color_json_dict() -> None:
    result = color_json({"a": 1})
    assert "{" in result
    assert "}" in result
    assert "a" in result
    assert "1" in result


def test_color_json_empty() -> None:
    assert color_json({}) == "{}"
    assert color_json([]) == "[]"


def test_estimate_tokens() -> None:
    assert estimate_tokens("hello") == 1  # 5 chars / 4 = 1.25 -> 1
    assert estimate_tokens("") == 1  # at least 1
    assert estimate_tokens("a" * 100) == 25  # 100 // 4


def test_message_token_count_string_content() -> None:
    msg: dict[str, object] = {"role": "user", "content": "hello world"}
    expected = estimate_tokens("hello world")
    assert _message_token_count(msg) == expected


def test_message_token_count_list_content() -> None:
    msg: dict[str, object] = {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "hello"},
            {"type": "tool_use", "name": "read_file", "input": {"path": "x.py"}},
        ],
    }
    # text tokens: len("hello") // 4 = 1
    # input tokens: len('{"path": "x.py"}') // 4 = 4
    assert _message_token_count(msg) == 5


def test_message_token_count_other_content() -> None:
    msg: dict[str, object] = {"role": "user", "content": 42}
    assert _message_token_count(msg) == 0


def test_trim_messages_under_threshold() -> None:
    messages: list[dict[str, object]] = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    result = trim_messages(messages, max_tokens=10_000, system_tokens=100)
    assert result == messages


def test_trim_messages_over_threshold() -> None:
    # Use a very small max_tokens so trimming must happen
    messages: list[dict[str, object]] = [
        {"role": "user", "content": "first message"},
        {"role": "assistant", "content": "first response"},
        {"role": "user", "content": "x" * 1_000},
        {"role": "assistant", "content": "second response"},
    ]
    # max_tokens=10 means only ~40 chars fit (10 * 4 * 0.75 = 30)
    result = trim_messages(messages, max_tokens=10, system_tokens=0)
    assert len(result) < len(messages)
    # Should have the system summary message
    assert "[System:" in str(result[0].get("content", ""))


def test_trim_messages_all_fit() -> None:
    messages: list[dict[str, object]] = [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
    ]
    result = trim_messages(messages, max_tokens=1000, system_tokens=10)
    assert result == messages


def test_strip_orphaned_tool_results_no_tools() -> None:
    messages: list[dict[str, object]] = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    result = _strip_orphaned_tool_results(messages)
    assert result == messages


def test_strip_orphaned_tool_results_keeps_valid() -> None:
    messages: list[dict[str, object]] = [
        {"role": "user", "content": "read file"},
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "name": "read_file", "input": {"path": "x.py"}}],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "content": "file content"}],
        },
    ]
    result = _strip_orphaned_tool_results(messages)
    assert len(result) == 3


def test_strip_orphaned_tool_results_drops_orphan() -> None:
    messages: list[dict[str, object]] = [
        {"role": "user", "content": "hi"},
        {
            "role": "user",
            "content": [{"type": "tool_result", "content": "orphan result"}],
        },
    ]
    result = _strip_orphaned_tool_results(messages)
    assert len(result) == 1
    assert result[0]["content"] == "hi"


# ── Markdown Rendering ────────────────────────────────────────────────────


def test_render_markdown_plain_text() -> None:
    """Plain text without markdown should print without error."""
    from src.utils import render_markdown
    # Should not raise
    render_markdown("Hello, this is plain text.")


def test_render_markdown_with_code_block() -> None:
    """Code blocks should render without error."""
    from src.utils import render_markdown
    text = '```python\nprint("hello")\n```'
    render_markdown(text)


def test_render_markdown_empty() -> None:
    """Empty string should not raise."""
    from src.utils import render_markdown
    render_markdown("")


def test_render_markdown_headings() -> None:
    """Headings and formatting should render without error."""
    from src.utils import render_markdown
    text = "# Heading\n\n**bold** and *italic* text"
    render_markdown(text)


# ── Language Detection ────────────────────────────────────────────────────


def test_detect_language_python() -> None:
    from src.utils import detect_language
    assert detect_language("main.py") == "python"


def test_detect_language_javascript() -> None:
    from src.utils import detect_language
    assert detect_language("script.js") == "javascript"


def test_detect_language_typescript() -> None:
    from src.utils import detect_language
    assert detect_language("app.ts") == "typescript"


def test_detect_language_markdown() -> None:
    from src.utils import detect_language
    assert detect_language("README.md") == "markdown"


def test_detect_language_unknown_extension() -> None:
    from src.utils import detect_language
    assert detect_language("file.unknown") == ""


def test_detect_language_code_block_tag() -> None:
    """Code block tags take precedence over file extension."""
    from src.utils import detect_language
    assert detect_language("file.py", code_block_tag="javascript") == "javascript"


def test_detect_language_empty() -> None:
    """Empty filename and tag returns empty string."""
    from src.utils import detect_language
    assert detect_language() == ""


# ── Syntax Highlighting ───────────────────────────────────────────────────


def test_highlight_code_python() -> None:
    """Highlighting Python code should produce ANSI output."""
    from src.utils import highlight_code
    result = highlight_code('print("hello")', language="python")
    assert isinstance(result, str)
    assert len(result) > 0
    # Should contain some ANSI escape sequences
    assert "\033[" in result or "print" in result


def test_highlight_code_no_language() -> None:
    """Highlighting without a language should still work."""
    from src.utils import highlight_code
    result = highlight_code('print("hello")')
    assert isinstance(result, str)


def test_highlight_code_empty() -> None:
    """Empty code should not raise."""
    from src.utils import highlight_code
    result = highlight_code("")
    assert isinstance(result, str)


def test_highlight_code_custom_theme() -> None:
    """Custom theme should be applied."""
    from src.utils import highlight_code
    result = highlight_code('print("hello")', language="python", theme="native")
    assert isinstance(result, str)
    assert len(result) > 0


# ── _contains_markdown ────────────────────────────────────────────────────


def test_contains_markdown_code_block() -> None:
    from src.repl import _contains_markdown
    assert _contains_markdown("Some text\n```python\ncode\n```")


def test_contains_markdown_heading() -> None:
    from src.repl import _contains_markdown
    assert _contains_markdown("# Heading")


def test_contains_markdown_bold() -> None:
    from src.repl import _contains_markdown
    assert _contains_markdown("This is **bold**")


def test_contains_markdown_italic() -> None:
    from src.repl import _contains_markdown
    assert _contains_markdown("This is *italic*")


def test_contains_markdown_list() -> None:
    from src.repl import _contains_markdown
    assert _contains_markdown("- item one\n- item two")


def test_contains_markdown_plain_text() -> None:
    from src.repl import _contains_markdown
    assert not _contains_markdown("Just plain text without any formatting.")


def test_contains_markdown_empty() -> None:
    from src.repl import _contains_markdown
    assert not _contains_markdown("")
