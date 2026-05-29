from __future__ import annotations

import json
import os
import sys
import threading
import time
from typing import Any, TextIO, cast

from .logging_config import get_logger

logger = get_logger(__name__)

# ── ANSI color helpers ─────────────────────────────────────────────────────


def _code(n: int) -> str:
    return f"\033[{n}m"


R = _code(0)  # reset


def dim(s: str) -> str:
    return f"{_code(2)}{s}{R}"


def green(s: str) -> str:
    return f"{_code(32)}{s}{R}"


def yellow(s: str) -> str:
    return f"{_code(33)}{s}{R}"


def bold(s: str) -> str:
    return f"{_code(1)}{s}{R}"


def cyan(s: str) -> str:
    return f"{_code(36)}{s}{R}"


def blue(s: str) -> str:
    return f"{_code(34)}{s}{R}"


def magenta(s: str) -> str:
    return f"{_code(35)}{s}{R}"


def red(s: str) -> str:
    return f"{_code(31)}{s}{R}"


def color_json(obj: object, indent: int = 2) -> str:
    """Return a syntax-highlighted JSON string using ANSI colors."""
    if isinstance(obj, str):
        return f"{green(json.dumps(obj))}"
    if isinstance(obj, bool):
        return yellow("true") if obj else yellow("false")
    if isinstance(obj, (int, float)):
        return cyan(str(obj))
    if obj is None:
        return dim("null")
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        items: list[str] = []
        inner_indent = indent + 2
        for k, v in obj.items():
            k_str = blue(json.dumps(k))
            v_str = color_json(v, inner_indent)
            items.append(f"{' ' * inner_indent}{k_str}: {v_str}")
        return "{\n" + ",\n".join(items) + "\n" + " " * indent + "}"
    if isinstance(obj, list):
        if not obj:
            return "[]"
        inner_indent = indent + 2
        items = [f"{' ' * inner_indent}{color_json(v, inner_indent)}" for v in obj]
        return "[\n" + ",\n".join(items) + "\n" + " " * indent + "]"
    return json.dumps(obj, indent=indent)


# ── Context management ─────────────────────────────────────────────────────

CHARS_PER_TOKEN = 4
TRIM_THRESHOLD = 0.75


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def _message_token_count(msg: dict[str, object]) -> int:
    content = msg.get("content", "")
    if isinstance(content, str):
        return estimate_tokens(content)
    if not isinstance(content, list):
        return 0
    content = cast("list[dict[str, object]]", content)
    total = 0
    for block in content:
        t = block.get("text")
        if isinstance(t, str):
            total += estimate_tokens(t)
        c = block.get("content")
        if isinstance(c, str):
            total += estimate_tokens(c)
        i = block.get("input")
        if i is not None:
            total += estimate_tokens(json.dumps(i))
    return total


def trim_messages(
    messages: list[dict[str, object]],
    max_tokens: int,
    system_tokens: int,
    client: Any | None = None,  # NEW: for summarization
    summarization_threshold: float = 0.9,  # NEW: summarize at 90% capacity
) -> list[dict[str, object]]:
    """Trim messages to fit within context window, optionally summarizing."""
    threshold = int(max_tokens * TRIM_THRESHOLD)
    available = threshold - system_tokens
    if available <= 0:
        return messages

    total = sum(_message_token_count(m) for m in messages)
    if total <= available:
        return messages

    # Optionally summarize oldest messages instead of dropping them
    if client is not None and total > int(max_tokens * summarization_threshold):
        # Try summarizing the earliest 50% of messages
        mid = len(messages) // 2
        early_msgs = messages[:mid]
        late_msgs = messages[mid:]

        summary = summarize_conversation(early_msgs, client)
        if summary:
            summary_msg: dict[str, object] = {
                "role": "user",
                "content": f"[Summary of earlier conversation: {summary}]",
            }
            combined: list[dict[str, object]] = [summary_msg] + late_msgs  # type: ignore[operator]
            return _strip_orphaned_tool_results(combined)

    # Fall back to standard trimming
    kept: list[dict[str, object]] = []
    budget = available

    for msg in reversed(messages):
        cost = _message_token_count(msg)
        if budget - cost >= 0 or not kept:
            kept.insert(0, msg)
            budget -= cost
        else:
            break

    if len(kept) < len(messages):
        dropped = len(messages) - len(kept)
        kept.insert(
            0,
            {
                "role": "user",
                "content": (
                    f"[System: {dropped} earlier message{' was' if dropped == 1 else 's were'}"
                    " removed to stay within context limits.]"
                ),
            },
        )

    return _strip_orphaned_tool_results(kept)


def _strip_orphaned_tool_results(
    messages: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Remove tool_result messages whose preceding tool_use was dropped by trimming."""
    cleaned: list[dict[str, object]] = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            blocks = cast("list[dict[str, object]]", content)
            is_tool_result = any(
                b.get("type") == "tool_result"
                for b in blocks
            )
            if is_tool_result and (not cleaned or cleaned[-1].get("role") != "assistant"):
                continue
        cleaned.append(msg)
    return cleaned


# ── Animated Spinner ────────────────────────────────────────────────────────


class Spinner:
    """An animated terminal spinner that runs in a background thread.

    Displays a rotating animation with a message while work is in progress.
    Automatically cleans up its display line on stop.

    Usage:
        spinner = Spinner("thinking...")
        spinner.start()
        # ... do work ...
        spinner.stop("  ✓ Done!")

    Can also be used as a context manager:
        with Spinner("working...") as spinner:
            # ... do work ...
            spinner.stop("  ✓ Done!")
    """

    # Braille dots (smooth animation) — preferred when terminal supports UTF-8
    SPINNER_CHARS_BRAILLE = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    # Classic ASCII fallback for terminals that don't support Unicode
    SPINNER_CHARS_ASCII = "|/-\\"

    def __init__(
        self,
        message: str = "",
        *,
        stream: TextIO = sys.stdout,
        delay: float = 0.1,
    ) -> None:
        self._message = message
        self._stream = stream
        self._delay = delay
        self._running = False
        self._thread: threading.Thread | None = None

        # Auto-detect best spinner characters based on stream encoding
        try:
            encoding = stream.encoding or "utf-8"
            # Test if the terminal supports braille characters
            "⠋".encode(encoding)
            self._chars = self.SPINNER_CHARS_BRAILLE
        except (UnicodeEncodeError, UnicodeDecodeError):
            self._chars = self.SPINNER_CHARS_ASCII

    @property
    def running(self) -> bool:
        """Whether the spinner is currently animating."""
        return self._running

    def start(self) -> None:
        """Start the spinner animation in a daemon background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def _spin(self) -> None:
        i = 0
        while self._running:
            char = self._chars[i % len(self._chars)]
            self._stream.write(f"\r  {bold(char)} {dim(self._message)}")
            self._stream.flush()
            time.sleep(self._delay)
            i += 1

    def stop(self, final_message: str = "") -> None:
        """Stop the spinner and clear its line. Optionally write a final message."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.5)
        # Clear the spinner line entirely
        self._stream.write("\r" + " " * 80 + "\r")
        if final_message:
            self._stream.write(final_message)
            self._stream.flush()

    def __enter__(self) -> Spinner:
        self.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.stop()


# ── Retry / backoff utilities ─────────────────────────────────────────────

import random as _random

DEFAULT_MAX_RETRIES = 5
DEFAULT_BASE_DELAY = 1.0
DEFAULT_MAX_DELAY = 60.0


def compute_backoff(
    attempt: int,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    jitter: bool = True,
) -> float:
    """Compute exponential backoff delay using full jitter.

    delay = random(0, min(base_delay * 2^attempt, max_delay))

    Full jitter (AWS recommended) is used when jitter=True:
    delay = random_uniform(0, cap)

    This spreads retries more evenly than additive jitter.
    """
    cap = min(base_delay * (2 ** attempt), max_delay)
    if jitter:
        return _random.uniform(0, cap)
    return cap


def is_transient_error(error: Exception) -> bool:
    """Return True if the error is likely transient and retryable."""
    from anthropic import (
        APIConnectionError,
        APIStatusError,
        InternalServerError,
        RateLimitError,
    )
    if isinstance(error, (APIConnectionError, RateLimitError, InternalServerError)):
        return True
    if isinstance(error, APIStatusError) and error.status_code in (429, 502, 503, 504):
        return True
    return False


# ── Markdown Rendering & Syntax Highlighting ──────────────────────────────


# ── Rich Terminal Rendering Utilities ───────────────────────────────────


def print_info(message: str) -> None:
    """Print an info message with a dim style."""
    print(f"  {message}")


def print_success(message: str) -> None:
    """Print a success message in green."""
    print(f"  ✓ {message}")


def print_warning(message: str) -> None:
    """Print a warning message in yellow."""
    print(f"  ⚠ {message}")


def print_error(message: str) -> None:
    """Print an error message in red."""
    print(f"  ✗ {message}")


def print_panel(title: str, content: str, style: str = "cyan") -> None:
    """Print content inside a bordered panel using rich if available."""
    try:
        from rich.console import Console
        from rich.panel import Panel
        console = Console()
        console.print(Panel(content, title=title, border_style=style))
    except ImportError:
        print(f"\n  {title}")
        print(f"  {'─' * 40}")
        for line in content.split("\n"):
            print(f"  {line}")
        print(f"  {'─' * 40}")


def print_table(title: str, columns: list[str], rows: list[list[str]]) -> None:
    """Print a table with columns and rows using rich if available."""
    try:
        from rich.console import Console
        from rich.table import Table
        table = Table(title=title, title_style="bold")
        for col in columns:
            table.add_column(col)
        for row in rows:
            table.add_row(*row)
        console = Console()
        console.print(table)
    except ImportError:
        print(f"\n  {title}")
        print(f"  {'─' * 60}")
        header = "  " + " | ".join(columns)
        print(header)
        print(f"  {'─' * 60}")
        for row in rows:
            print("  " + " | ".join(str(c) for c in row))
        print(f"  {'─' * 60}")


def print_separator(style: str = "dim") -> None:
    """Print a horizontal rule/separator using rich if available."""
    try:
        from rich.console import Console
        from rich.rule import Rule
        Console().print(Rule(style=style))
    except ImportError:
        print(f"  {'─' * 60}")


def print_code(code: str, language: str = "", theme: str = "monokai") -> None:
    """Print syntax-highlighted code using rich if available."""
    try:
        from rich.console import Console
        from rich.syntax import Syntax
        syntax = Syntax(code, language, theme=theme, line_numbers=True)
        Console().print(syntax)
    except Exception:
        print(code)


# ── Conversation Summarization ──────────────────────────────────────────


def summarize_conversation(
    messages: list[dict[str, object]],
    client: Any,  # LlmClient instance
) -> str:
    """Summarize a list of messages into a condensed form using the LLM.

    Returns a summary string that can replace the original messages.
    """
    # Build a condensed version of the messages for the summarizer prompt
    text_parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, str):
            text_parts.append(f"[{role}]: {content[:200]}")
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    t = block.get("text") or block.get("content", "")
                    if isinstance(t, str):
                        text_parts.append(f"[{role}]: {t[:200]}")

    conversation_text = "\n".join(text_parts)

    prompt = (
        "Summarize the following conversation between a user and an AI coding assistant. "
        "Focus on: the user's goals, what files have been discussed or modified, "
        "key decisions made, and what the current state of work is. "
        "Keep the summary concise but informative (2-3 paragraphs).\n\n"
        f"{conversation_text}"
    )

    try:
        # Use a separate non-streaming call for summarization
        summary = client.chat_sync(prompt, max_tokens=500)
        return summary.strip()
    except Exception as e:
        logger.warning("Summarization failed: %s", e)
        return ""


def show_diff_and_confirm(original: str, modified: str, filepath: str) -> bool:
    """Show a colored diff between original and modified content.

    Returns True if user confirms, False if user rejects.
    """
    import difflib

    diff_lines = list(difflib.unified_diff(
        original.splitlines(keepends=True),
        modified.splitlines(keepends=True),
        fromfile=filepath,
        tofile=filepath,
    ))

    if not diff_lines:
        return True  # No changes

    # Colorize the diff
    for line in diff_lines:
        if line.startswith("+"):
            print(green(line.rstrip()))
        elif line.startswith("-"):
            print(red(line.rstrip()))
        elif line.startswith("@@"):
            print(cyan(line.rstrip()))
        else:
            print(dim(line.rstrip()))

    # Ask for confirmation
    print(f"\n  {yellow('Apply these changes?')} [Y/n] ", end="", flush=True)
    try:
        response = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        response = "n"
    return response in ("", "y", "yes")


def render_markdown(text: str, syntax_theme: str = "monokai") -> None:
    """Render Markdown text to the terminal using rich.

    Applies syntax highlighting to code blocks within the Markdown.
    Falls back to plain print() if Markdown parsing fails.
    """
    try:
        from rich.markdown import Markdown as RichMarkdown
        from rich import print as rich_print

        md = RichMarkdown(text, code_theme=syntax_theme)
        rich_print(md)
    except Exception:
        # Fallback to plain text if Markdown parsing fails
        print(text)


EXTENSION_LANG_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "jsx",
    ".html": "html",
    ".css": "css",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".sh": "bash",
    ".bash": "bash",
    ".sql": "sql",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".rb": "ruby",
    ".php": "php",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".xml": "xml",
    ".svg": "xml",
}


def detect_language(filename: str = "", code_block_tag: str = "") -> str:
    """Detect programming language from filename or code block tag."""
    if code_block_tag:
        return code_block_tag
    _, ext = os.path.splitext(filename)
    return EXTENSION_LANG_MAP.get(ext, "")


def highlight_code(code: str, language: str = "", theme: str = "monokai") -> str:
    """Apply syntax highlighting to a code string.

    Args:
        code: The source code to highlight
        language: Programming language (auto-detected if empty via extension)
        theme: Pygments theme name (default: "monokai")

    Returns:
        Syntax-highlighted string (rich renderable), or original code on failure.
    """
    try:
        from rich.syntax import Syntax
        from rich.ansi import AnsiDecoder

        syntax = Syntax(code, language, theme=theme, line_numbers=False)
        # Convert the rich renderable to an ANSI string
        from io import StringIO
        from rich.console import Console

        buf = StringIO()
        console = Console(file=buf, force_terminal=True, width=100)
        console.print(syntax, end="")
        return buf.getvalue()
    except Exception:
        return code


# ── Write-path enforcement ───────────────────────────────────────────────────


def validate_write_path(path: str, working_directory: str) -> str | None:
    """Validate that a write path is within the working directory.

    Resolves both paths to their real absolute forms and checks that
    *path* resolves to a location inside *working_directory*.

    Returns ``None`` if the path is valid, or an error message string
    if it is outside the working directory.

    On Windows, comparison is case-insensitive (handled by Path.resolve()).
    """
    from pathlib import Path

    resolved_path = Path(path).resolve()
    resolved_wd = Path(working_directory).resolve()

    try:
        resolved_path.relative_to(resolved_wd)
        return None
    except ValueError:
        return (
            f"Error: Path '{path}' resolves to '{resolved_path}' "
            f"which is outside the working directory '{resolved_wd}'. "
            f"All file operations must be within the working directory."
        )
