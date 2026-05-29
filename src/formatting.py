"""Terminal formatting and display utilities.

Provides ANSI color helpers, JSON colorization, an animated spinner,
diff display, and table/panel printing utilities.
"""

from __future__ import annotations

import difflib
import json
import os
import sys
import threading
import time
from typing import Any, TextIO


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


# ── Diff display ──────────────────────────────────────────────────────────


def show_diff_and_confirm(original: str, modified: str, filepath: str) -> bool:
    """Show a colored diff between original and modified content.

    Returns True if user confirms, False if user rejects.
    """
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
