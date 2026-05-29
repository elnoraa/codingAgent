from __future__ import annotations

import json
import os
import sys
import threading
import time
from typing import Any, Callable, TextIO, cast

from .logging_config import get_logger

logger = get_logger(__name__)

# ── Input size limits ─────────────────────────────────────────────────────────

MAX_CODE_LENGTH = 50_000        # 50KB for Python code execution
MAX_COMMAND_LENGTH = 10_000     # 10KB for shell commands
MAX_QUERY_LENGTH = 50_000       # 50KB for SQL queries
MAX_TEXT_LENGTH = 100_000       # 100KB for file content replacements
MAX_PATH_LENGTH = 4_096         # 4096 chars for file paths
MAX_FILE_CONTENT = 10_000_000   # 10MB for file write content
MAX_URL_LENGTH = 8_192          # 8KB for URLs


def validate_length(value: str | None, max_length: int, name: str) -> str | None:
    """Validate that a string value doesn't exceed *max_length*.

    Returns an error message if too long, ``None`` if valid.
    """
    if value is None:
        return None
    if len(value) > max_length:
        return (
            f"Error: {name} is too long ({len(value)} chars, max {max_length}). "
            f"Please reduce the input size."
        )
    return None

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


# ── ANSI Terminal Escape Sanitization ──────────────────────────────────────────

import re as _re_ansi

# Dangerous ANSI sequences that should be stripped from output before rendering.
# These can be used for terminal injection attacks (cursor positioning, screen
# clearing, title setting, keyboard remapping, etc.).
_DANGEROUS_ANSI_PATTERNS: list[Any] = [
    _re_ansi.compile(r'\x1b\[2J'),        # Clear entire screen
    _re_ansi.compile(r'\x1b\[3J'),        # Clear scrollback
    _re_ansi.compile(r'\x1b\[0J'),        # Clear from cursor to end of screen
    _re_ansi.compile(r'\x1b\[1J'),        # Clear from beginning to cursor
    _re_ansi.compile(r'\x1b\[\d*(?:;\d*)?[Hf]'),  # Cursor positioning
    _re_ansi.compile(r'\x1b\[\?25[lh]'),   # Hide/show cursor
    _re_ansi.compile(r'\x1b\]0;.+?\x07'),  # Set terminal title
    _re_ansi.compile(r'\x1b\]2;.+?\x07'),  # Set terminal title (alternative)
    _re_ansi.compile(r'\x1b\[\d*[n]'),    # Device status reports
    _re_ansi.compile(r'\x1b\[[0-9;]*[t]'),    # XTerm window ops
    _re_ansi.compile(r'\x1bc', _re_ansi.ASCII),      # RIS (Reset to Initial State)
    _re_ansi.compile(r'\x1b][\\_\[\]]'),  # String terminators
]


def strip_dangerous_ansi(text: str) -> str:
    """Strip dangerous ANSI escape sequences from text.

    Preserves common formatting sequences (colors, bold, dim) but removes
    sequences that could be used for terminal injection attacks.

    Args:
        text: The text to sanitize.

    Returns:
        Sanitized text with dangerous sequences removed.
    """
    if not text:
        return text
    result = text
    for pattern in _DANGEROUS_ANSI_PATTERNS:
        result = pattern.sub('', result)
    return result


def print_code(code: str, language: str = "", theme: str = "monokai") -> None:
    """Print syntax-highlighted code using rich if available."""
    try:
        from rich.console import Console
        from rich.syntax import Syntax
        syntax = Syntax(code, language, theme=theme, line_numbers=True)
        Console().print(syntax)
    except Exception:
        print(code)


import re as _re_sensitive

# Sensitive patterns to redact before sending message content to LLM
# for summarization. This prevents secrets from being transmitted to
# the LLM provider.
_SUMMARIZATION_REDACT_PATTERNS: list[tuple[str, str]] = [
    # Anthropic / OpenAI / generic API keys
    (r'(sk-[a-zA-Z0-9\-]{20,})', 'sk-***REDACTED***'),
    # AWS access keys
    (r'(AKIA[0-9A-Z]{16})', 'AKIA***REDACTED***'),
    # GitHub tokens
    (r'(ghp_[a-zA-Z0-9]{36})', 'ghp_***REDACTED***'),
    (r'(github_pat_[a-zA-Z0-9_]{80,})', 'github_pat_***REDACTED***'),
    # Password/secret assignments
    (r'(password\s*[:=]\s*["\x27]?)[^"\x27,;\s}]+', r'\1***REDACTED***'),
    (r'(passwd\s*[:=]\s*["\x27]?)[^"\x27,;\s}]+', r'\1***REDACTED***'),
    (r'(secret\s*[:=]\s*["\x27]?)[^"\x27,;\s}]+', r'\1***REDACTED***'),
    # Database connection strings with credentials
    (r'((?:mongodb(?:\+srv)?|postgres(?:ql)?|mysql|redis)://)[^@\s]+@', r'\1***USER***@'),
    # JWT tokens
    (r'(eyJ[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,})', 'eyJ***REDACTED***'),
    # Private key headers
    (r'-----BEGIN\s+(RSA|DSA|EC|OPENSSH|PGP)\s+PRIVATE\s+KEY-----', '-----BEGIN REDACTED PRIVATE KEY-----'),
    # Bearer tokens in headers
    (r'(Authorization:\s*Bearer\s+)[a-zA-Z0-9._\x2d]+', r'\1***REDACTED***'),
]


def redact_sensitive_content(text: str) -> str:
    """Redact known sensitive patterns from text content.

    This is used before sending message content to the LLM for
    summarization to prevent secrets from being transmitted to
    the LLM provider.

    Args:
        text: The text to redact.

    Returns:
        Redacted text with sensitive values replaced.
    """
    if not text:
        return text

    result = text
    for pattern, replacement in _SUMMARIZATION_REDACT_PATTERNS:
        result = _re_sensitive.sub(pattern, replacement, result, flags=_re_sensitive.IGNORECASE)
    return result


# ── Conversation Summarization ──────────────────────────────────────────


def summarize_conversation(
    messages: list[dict[str, object]],
    client: Any,  # LlmClient instance
) -> str:
    """Summarize a list of messages into a condensed form using the LLM.

    Returns a summary string that can replace the original messages.

    Note: Sensitive content (API keys, passwords, etc.) is automatically
    redacted from the messages before sending to the LLM.
    """
    # Build a condensed version of the messages for the summarizer prompt
    text_parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, str):
            # Redact sensitive content before summarization
            redacted = redact_sensitive_content(content[:500])
            text_parts.append(f"[{role}]: {redacted}")
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    t = block.get("text") or block.get("content", "")
                    if isinstance(t, str):
                        redacted = redact_sensitive_content(t[:500])
                        text_parts.append(f"[{role}]: {redacted}")

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
    # Sanitize dangerous ANSI sequences before rendering
    text = strip_dangerous_ansi(text)
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
    # Sanitize dangerous ANSI sequences before rendering
    code = strip_dangerous_ansi(code)
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


import time as _time
from collections import defaultdict as _defaultdict
from threading import Lock as _Lock


class RateLimiter:
    """Simple sliding-window rate limiter for tool calls.

    Tracks the number of tool calls within a configurable time window
    and returns an error if the limit is exceeded.

    Supports different limits for different categories of tools
    (read, write, exec, network).

    Usage::

        limiter = RateLimiter()
        error = limiter.check_limit("bash", category="exec")
        if error:
            return error
    """

    DEFAULT_LIMITS: dict[str, tuple[int, float]] = {
        "read":    (60,  60.0),    # 60 read calls per minute
        "write":   (20,  60.0),    # 20 write calls per minute
        "exec":    (30,  60.0),    # 30 subprocess calls per minute
        "network": (15,  60.0),    # 15 network calls per minute
        "default": (50,  60.0),    # 50 calls per minute (fallback)
    }

    def __init__(self, limits: dict[str, tuple[int, float]] | None = None) -> None:
        self._limits = {**self.DEFAULT_LIMITS, **(limits or {})}
        self._history: dict[str, list[float]] = _defaultdict(list)
        self._lock = _Lock()

    def check_limit(self, tool_name: str, category: str = "default") -> str | None:
        """Check if the tool is within its rate limit.

        Args:
            tool_name: Name of the tool (for logging).
            category: Category of the tool (read, write, exec, network, default).

        Returns:
            ``None`` if within limit, or an error message if rate limited.
        """
        if category not in self._limits:
            category = "default"

        max_calls, window_seconds = self._limits[category]
        now = _time.time()
        cutoff = now - window_seconds

        with self._lock:
            history = self._history[category]
            while history and history[0] < cutoff:
                history.pop(0)

            if len(history) >= max_calls:
                oldest = history[0] if history else now
                retry_after = max(0, window_seconds - (now - oldest))
                logger.warning(
                    "Rate limit exceeded for '%s' (tool: %s): "
                    "%d calls in %ds window. Retry after %.1fs.",
                    category, tool_name, len(history), window_seconds, retry_after,
                )
                return (
                    f"Error: Rate limit exceeded for {category} operations "
                    f"(tool: {tool_name}). Maximum {max_calls} calls per "
                    f"{window_seconds:.0f}s. Please wait {retry_after:.1f}s "
                    f"before retrying."
                )

            history.append(now)

        return None

    def get_remaining(self, category: str = "default") -> int:
        """Get the number of remaining calls allowed in the current window."""
        if category not in self._limits:
            category = "default"
        max_calls, window_seconds = self._limits[category]
        now = _time.time()
        cutoff = now - window_seconds

        with self._lock:
            history = self._history[category]
            while history and history[0] < cutoff:
                history.pop(0)
            return max(0, max_calls - len(history))

    def reset(self, category: str | None = None) -> None:
        """Reset rate limit counters for a category (or all if ``None``)."""
        with self._lock:
            if category:
                self._history[category].clear()
            else:
                self._history.clear()


def validate_write_path(path: str, working_directory: str) -> str | None:
    """Validate that a write path is within the working directory.

    Resolves both paths to their real absolute forms and checks that
    *path* resolves to a location inside *working_directory*.

    Also checks for symlink-based escapes — if any component of the
    path is a symlink pointing outside the working directory, it is
    rejected even if the final resolved path is inside.

    Returns ``None`` if the path is valid, or an error message string
    if it is outside the working directory.

    On Windows, comparison is case-insensitive (handled by Path.resolve()).
    """
    from pathlib import Path

    resolved_path = Path(path).resolve()
    resolved_wd = Path(working_directory).resolve()

    # Step 1: Check that the final resolved path is within the working directory
    try:
        resolved_path.relative_to(resolved_wd)
    except ValueError:
        return (
            f"Error: Path '{path}' resolves to '{resolved_path}' "
            f"which is outside the working directory '{resolved_wd}'. "
            f"All file operations must be within the working directory."
        )

    # Step 2: Check for symlink-based escapes
    # Walk the path from root to leaf checking each component.
    # If any component is a symlink pointing outside the working directory,
    # reject the path (an attacker could create a symlink inside WD -> outside).
    try:
        # Build the absolute path to walk
        if os.path.isabs(path):
            original_abs = Path(path)
        else:
            original_abs = Path(working_directory) / path

        # Normalize the path to remove ".." and "." components for walking
        original_abs = original_abs.resolve()

        # Walk all parent directories checking for symlinks
        for parent in original_abs.parents:
            try:
                if parent.is_symlink():
                    resolved_link = parent.resolve()
                    try:
                        resolved_link.relative_to(resolved_wd)
                    except ValueError:
                        return (
                            f"Error: Path '{path}' contains symlink '{parent}' "
                            f"which points to '{resolved_link}' outside the working "
                            f"directory. Symlinks to outside paths are not allowed."
                        )
            except (OSError, RuntimeError):
                pass  # Can't check — path may not exist yet, skip

        # Also check the leaf if it exists
        try:
            if original_abs.is_symlink():
                resolved_link = original_abs.resolve()
                try:
                    resolved_link.relative_to(resolved_wd)
                except ValueError:
                    return (
                        f"Error: Path '{path}' is a symlink pointing to "
                        f"'{resolved_link}' outside the working directory. "
                        f"Symlinks to outside paths are not allowed."
                    )
        except (OSError, RuntimeError):
            pass
    except (OSError, ValueError, RuntimeError):
        pass  # If we can't fully check, don't block (path may not exist yet)

    return None


def validate_write_path_atomic(path: str, working_directory: str) -> str | None:
    """Validate that a path is within the working directory, performing the
    check as close to the actual write as possible.

    This function:
    1. Resolves the path to its real (canonical) form
    2. Checks that the real path is within the working directory
    3. Does NOT do a full symlink parent walk (that's done at tool-call time)

    Call this function IMMEDIATELY before opening a file for writing,
    inside the try block.

    Returns ``None`` if the path is valid, or an error message string
    if it is outside the working directory.
    """
    from pathlib import Path

    try:
        resolved_path = Path(path).resolve()
        resolved_wd = Path(working_directory).resolve()
        resolved_path.relative_to(resolved_wd)
    except (ValueError, RuntimeError, OSError):
        return (
            f"Error: Path '{path}' resolves to outside the working directory "
            f"'{working_directory}'. All file operations must be within the "
            f"working directory."
        )
    return None


def validate_walk_path(path: str, working_directory: str) -> str | None:
    """Validate that a path discovered during directory walking is within the
    working directory after resolving all symlinks.

    This is a lightweight check for paths found during ``os.walk`` or
    ``os.scandir`` traversal. Unlike ``validate_write_path``, it does not
    perform a full component-by-component symlink audit, but it does reject
    paths whose resolved (real) location is outside the working directory.

    Returns ``None`` if the path is valid, or an error message string if the
    path escapes the working directory via symlinks.
    """
    from pathlib import Path

    try:
        resolved = Path(path).resolve()
        resolved_wd = Path(working_directory).resolve()
        resolved.relative_to(resolved_wd)
    except (ValueError, RuntimeError, OSError):
        return (
            f"Error: Path '{path}' resolves to outside the working directory "
            f"'{working_directory}' (possible symlink escape). Skipping."
        )
    return None


# ── Data exfiltration detection constants ──────────────────────────────────────

# Files that should never be read and sent over the network
_EXFIL_SENSITIVE_FILES: frozenset = frozenset({
    ".env", ".env.example", ".env.local", ".env.production",
    "config.json",  # may contain credentials
    ".git-credentials", ".gitconfig",
    ".ssh/id_rsa", ".ssh/id_rsa.pub", ".ssh/id_ed25519", ".ssh/id_ed25519.pub",
    ".ssh/config", ".ssh/authorized_keys",
    "id_rsa", "id_ed25519",
    "credentials.json", "credentials.yml", "credentials.yaml",
    "service-account.json", "service-account-key.json",
    ".npmrc", ".netrc",
})

# Commands that can send data to remote servers (exfiltration vectors)
_EXFIL_NETWORK_COMMANDS: frozenset = frozenset({
    "curl", "wget", "nc", "ncat", "netcat", "socat",
    "ftp", "sftp", "scp", "rsync",
    "telnet",
})

# Script interpreters that can execute inline code and bypass the command scanner
# Format: (interpreter_binary, flag_that_takes_inline_code, description)
_SCRIPT_INTERPRETERS: list[tuple[str, str, str]] = [
    ("python", "-c", "Python inline code execution"),
    ("python3", "-c", "Python 3 inline code execution"),
    ("node", "-e", "Node.js inline code execution"),
    ("node", "-p", "Node.js inline print execution"),
    ("ruby", "-e", "Ruby inline code execution"),
    ("perl", "-e", "Perl inline code execution"),
    ("php", "-r", "PHP inline code execution"),
    ("php", "-R", "PHP inline code processing"),
]

# Dangerous function/module calls that indicate file operations in script code
_SCRIPT_FILE_READ_INDICATORS: frozenset = frozenset({
    "open(", ".read(", ".read_text(", ".read_bytes(",
    "readFile(", "readFileSync(", "readFileSync (",
    "createReadStream(", "createReadStream (",
    "File.read(", "File.open(",
    "fread(", "file_get_contents(",
})

# Dangerous function/module calls that indicate network operations in script code
_SCRIPT_NETWORK_INDICATORS: frozenset = frozenset({
    "urllib.request.urlopen(", "urllib.request.Request(",
    "requests.get(", "requests.post(", "requests.put(", "requests.delete(",
    "urlopen(", "urlretrieve(",
    "fetch(", "http.", "https.",
    "net/http", "net::HTTP",
    "curl ", "wget ",
})


# ── SSRF protection ─────────────────────────────────────────────────────────

import ipaddress as _ipaddress
import socket as _socket
from urllib.parse import urlparse as _urlparse

# Private/reserved IP ranges that should be blocked for SSRF prevention
_PRIVATE_NETWORKS: list[Any] = [
    # IPv4 private/reserved
    _ipaddress.ip_network("0.0.0.0/8"),          # Current network (RFC 1122)
    _ipaddress.ip_network("10.0.0.0/8"),         # Private (RFC 1918)
    _ipaddress.ip_network("100.64.0.0/10"),      # Carrier-grade NAT (RFC 6598)
    _ipaddress.ip_network("127.0.0.0/8"),        # Loopback (RFC 1122)
    _ipaddress.ip_network("169.254.0.0/16"),     # Link-local (RFC 3927)
    _ipaddress.ip_network("172.16.0.0/12"),      # Private (RFC 1918)
    _ipaddress.ip_network("192.0.0.0/24"),       # IETF Protocol Assignments (RFC 6890)
    _ipaddress.ip_network("192.0.2.0/24"),       # TEST-NET-1 (RFC 5737)
    _ipaddress.ip_network("192.88.99.0/24"),     # 6to4 Relay Anycast (RFC 7526)
    _ipaddress.ip_network("192.168.0.0/16"),     # Private (RFC 1918)
    _ipaddress.ip_network("198.18.0.0/15"),      # Benchmarking (RFC 2544)
    _ipaddress.ip_network("198.51.100.0/24"),    # TEST-NET-2 (RFC 5737)
    _ipaddress.ip_network("203.0.113.0/24"),     # TEST-NET-3 (RFC 5737)
    _ipaddress.ip_network("224.0.0.0/4"),        # Multicast (RFC 5771)
    _ipaddress.ip_network("240.0.0.0/4"),        # Reserved (RFC 1112)
    _ipaddress.ip_network("255.255.255.255/32"), # Limited Broadcast

    # IPv6 private/reserved
    _ipaddress.ip_network("::1/128"),            # Loopback
    _ipaddress.ip_network("::/96"),              # IPv4-compatible (deprecated)
    _ipaddress.ip_network("::ffff:0:0/96"),      # IPv4-mapped addresses
    _ipaddress.ip_network("64:ff9b::/96"),       # IPv4/IPv6 translation (RFC 6052)
    _ipaddress.ip_network("100::/64"),           # Discard-only (RFC 6666)
    _ipaddress.ip_network("2001:db8::/32"),      # Documentation (RFC 3849)
    _ipaddress.ip_network("2002::/16"),          # 6to4 (RFC 3056)
    _ipaddress.ip_network("fc00::/7"),           # Unique local (RFC 4193)
    _ipaddress.ip_network("fe80::/10"),          # Link-local (RFC 4291)
    _ipaddress.ip_network("ff00::/8"),           # Multicast (RFC 4291)
]


def _default_resolver(hostname: str) -> list[str]:
    """Default DNS resolver: get all IP addresses for a hostname."""
    result: list[str] = []
    addrinfo = _socket.getaddrinfo(hostname, None)
    for family, _, _, _, sockaddr in addrinfo:
        ip = sockaddr[0]
        if isinstance(ip, str) and ip not in result:
            result.append(ip)
    return result


def _is_private_ip(ip_str: str) -> bool:
    """Check if an IP string is in any private/reserved network."""
    try:
        ip = _ipaddress.ip_address(ip_str)
        for net in _PRIVATE_NETWORKS:
            if ip in net:
                return True
    except ValueError:
        pass
    return False


def _check_ips_against_blocklist(hostname: str, url: str, ips: list[str]) -> str | None:
    """Check a list of IPs against the private network blocklist.

    Returns an error message if any IP is blocked, None otherwise.
    """
    for ip_str in ips:
        try:
            ip = _ipaddress.ip_address(ip_str)
            for private_net in _PRIVATE_NETWORKS:
                if ip in private_net:
                    return (
                        f"Error: URL '{url}' resolves to private IP {ip}. "
                        f"Requests to private/internal networks are blocked "
                        f"for security (SSRF protection)."
                    )
        except ValueError:
            continue
    return None


def _detect_dns_rebinding(
    hostname: str,
    first_ips: list[str],
    resolver: Callable[[str], list[str]],
) -> tuple[list[str], str | None]:
    """Detect DNS rebinding by double-resolving the hostname.

    Only flags as rebinding if one resolution set contains a private IP
    and the other contains a public IP. Round-robin DNS (all public IPs
    that differ between resolutions) is allowed.

    Returns (second_ips, error_message_or_None).
    """
    try:
        second_ips = resolver(hostname)
    except (_socket.gaierror, OSError):
        return first_ips, None

    if not second_ips:
        return first_ips, None

    if second_ips == first_ips:
        return second_ips, None

    # IPs differ — check if either set contains a private IP
    first_has_private = any(_is_private_ip(ip) for ip in first_ips)
    second_has_private = any(_is_private_ip(ip) for ip in second_ips)

    if first_has_private != second_has_private:
        # One resolution had a private IP, the other didn't — possible rebinding
        return second_ips, (
            f"Error: URL '{hostname}' resolved to different IPs on consecutive "
            f"lookups, and one set included a private/internal IP "
            f"(possible DNS rebinding attack). Blocking for safety."
        )

    # Both are public or both are private — allow (round-robin or consistent)
    return second_ips, None


def validate_url_target(
    url: str,
    *,
    _resolver: Callable[[str], list[str]] | None = None,
) -> str | None:
    """Validate that a URL target does not point to a private/internal IP.

    Protects against:
    - Direct requests to private/internal IPs
    - DNS rebinding attacks (by double-resolving the hostname)
    - IPv4-mapped IPv6 address bypasses

    Args:
        url: The URL to validate.
        _resolver: Optional custom resolver for testing (default: socket.getaddrinfo).

    Returns ``None`` if the URL is safe, or an error message string if blocked.
    """
    parsed = _urlparse(url)
    if not parsed.scheme:
        return "Error: URL must have a scheme (http:// or https://)"
    if parsed.scheme not in ("http", "https"):
        return f"Error: Unsupported URL scheme '{parsed.scheme}'. Only http/https allowed."

    hostname = parsed.hostname
    if not hostname:
        return "Error: URL has no valid hostname"

    resolver = _resolver or _default_resolver

    # ── First resolution ────────────────────────────────────────────────
    try:
        first_ips = resolver(hostname)
    except (_socket.gaierror, OSError):
        return None  # Can't resolve — let the request proceed

    if not first_ips:
        return None

    # Check first resolution against private ranges
    first_blocked = _check_ips_against_blocklist(hostname, url, first_ips)
    if first_blocked:
        return first_blocked

    # ── Second resolution (DNS rebinding detection) ──────────────────────
    second_ips, rebind_error = _detect_dns_rebinding(hostname, first_ips, resolver)
    if rebind_error:
        logger.warning(
            "DNS rebinding detected for '%s': first=%s, second=%s",
            hostname, first_ips, second_ips,
        )
        return rebind_error

    # Check second resolution against private ranges (redundant but safe)
    if second_ips:
        second_blocked = _check_ips_against_blocklist(hostname, url, second_ips)
        if second_blocked:
            return second_blocked

    return None
