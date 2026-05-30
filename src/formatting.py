"""Terminal formatting and display utilities.

Provides ANSI color helpers, JSON colorization, an animated spinner,
diff display, table/panel printing utilities, a progress bar, a
confirmation prompt helper, and a long-output pager.

Following SOLID & DRY: each utility has a single responsibility,
all depend on stdlib abstractions (TextIO, shutil), and shared
patterns (confirmation prompts, terminal width) are extracted once.
"""

from __future__ import annotations

import difflib
import json
import shutil
import sys
import threading
import time
from typing import TextIO

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


# ── Terminal utilities ────────────────────────────────────────────────────────


def get_terminal_width(fallback: int = 80) -> int:
    """Get the current terminal width, with a fallback default."""
    try:
        return shutil.get_terminal_size().columns
    except Exception:
        return fallback


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
        except UnicodeEncodeError, UnicodeDecodeError:
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
        # Clear the spinner line entirely using dynamic terminal width
        self._stream.write("\r" + " " * get_terminal_width() + "\r")
        if final_message:
            self._stream.write(final_message)
            self._stream.flush()

    def __enter__(self) -> Spinner:
        self.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.stop()


# ── Progress Bar ──────────────────────────────────────────────────────────────


class ProgressBar:
    """A lightweight, single-line progress bar for terminal operations.

    Renders as::

        Indexing files...  [████████░░░░░░░░░░░░]  45%  (45/100 files)

    Usage::

        bar = ProgressBar(total=100, message="Processing...")
        for i in range(100):
            do_work(i)
            bar.update(i + 1)
        bar.finish("  Done!")

    Can also be used as a context manager::

        with ProgressBar(total=100, message="Working...") as bar:
            for i in range(100):
                do_work(i)
                bar.update(i + 1)
    """

    def __init__(
        self,
        total: int,
        message: str = "",
        *,
        stream: TextIO = sys.stdout,
        bar_width: int | None = None,
    ) -> None:
        self.total = max(total, 1)
        self.current = 0
        self._message = message
        self._stream = stream
        self._bar_width = bar_width or (get_terminal_width() - 20)
        self._start_time = time.time()
        self._finished = False

    def update(self, current: int, message: str = "") -> None:
        """Update progress to *current* (0-based or 1-based)."""
        self.current = min(current, self.total)
        pct = self.current / self.total
        filled = int(pct * self._bar_width)
        bar = "█" * filled + "░" * (self._bar_width - filled)
        elapsed = time.time() - self._start_time
        msg = message or self._message
        self._stream.write(f"\r  {msg} [{bar}] {pct * 100:3.0f}%  ({self.current}/{self.total})  {elapsed:.1f}s")
        self._stream.flush()

    def finish(self, final_message: str = "") -> None:
        """Complete the progress bar and optionally write a final message."""
        if self._finished:
            return
        self._finished = True
        self._stream.write("\r" + " " * get_terminal_width() + "\r")
        if final_message:
            self._stream.write(final_message)
            self._stream.flush()

    def __enter__(self) -> ProgressBar:
        return self

    def __exit__(self, *args: object) -> None:
        self.finish()


# ── Confirmation prompt ───────────────────────────────────────────────────────


def confirm(prompt: str = "Continue?", default_yes: bool = True) -> bool:
    """Display a [Y/n] or [y/N] confirmation prompt and return the result.

    Args:
        prompt: The question to display.
        default_yes: If True, pressing Enter defaults to yes; otherwise no.

    Returns:
        True if confirmed, False if rejected.
    """
    marker = "[Y/n]" if default_yes else "[y/N]"
    print(f"  {yellow('?')} {prompt} {dim(marker)} ", end="", flush=True)
    try:
        response = input().strip().lower()
    except EOFError, KeyboardInterrupt:
        print()
        return default_yes
    if not response:
        return default_yes
    return response in ("y", "yes")


# ── Pager for long output ────────────────────────────────────────────────────


def page_output(lines: list[str], *, stream: TextIO = sys.stdout) -> None:
    """Display long output one screenful at a time, pausing after each page.

    Falls back to printing all lines if the output fits on one screen.

    Args:
        lines: The lines to display.
        stream: The output stream (default: sys.stdout).
    """
    import contextlib

    from src.formatting import dim

    height = 24
    with contextlib.suppress(Exception):
        height = shutil.get_terminal_size().lines - 2

    if len(lines) <= height:
        for line in lines:
            stream.write(line + "\n")
        stream.flush()
        return

    for i in range(0, len(lines), height):
        chunk = lines[i : i + height]
        for line in chunk:
            stream.write(line + "\n")
        stream.flush()
        if i + height < len(lines):
            remaining = len(lines) - (i + height)
            try:
                input(f"  {dim(f'— {remaining} more lines. Press Enter to continue, q to quit —')}")
            except EOFError, KeyboardInterrupt:
                stream.write("\n")
                return


# ── Diff display ──────────────────────────────────────────────────────────


def show_diff_and_confirm(original: str, modified: str, filepath: str) -> bool:
    """Show a colored diff between original and modified content.

    Returns True if user confirms, False if user rejects.
    """
    diff_lines = list(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            modified.splitlines(keepends=True),
            fromfile=filepath,
            tofile=filepath,
        )
    )

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

    # Ask for confirmation using the shared helper (DRY)
    return confirm("Apply these changes?", default_yes=True)
