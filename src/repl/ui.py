"""UI utilities for the REPL — input handling, display helpers, file preview."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import TYPE_CHECKING

from src.formatting import bold, cyan, dim, green, red, yellow

if TYPE_CHECKING:
    from src.repl.repl import Repl


# ── Readline (command history with arrow keys) ──────────────────────────
_readline_available = False
try:
    import readline  # noqa: F401

    _readline_available = True
except ImportError:
    try:
        import pyreadline3  # type: ignore[import-untyped]  # noqa: F401

        _readline_available = True
    except ImportError:
        pass


def setup_tab_completion(repl: Repl) -> None:
    """Set up tab completion for commands using readline."""
    if not _readline_available:
        return

    import readline as _readline  # type: ignore[import-untyped]

    # List of all available commands
    commands = [
        "/help",
        "/h",
        "/clear",
        "/c",
        "/tools",
        "/history",
        "/status",
        "/s",
        "/mode",
        "/plan",
        "/p",
        "/ask",
        "/a",
        "/code",
        "/plan",
        "/edit",
        "/retry",
        "/r",
        "/retry-auto",
        "/ra",
        "/save",
        "/load",
        "/sessions",
        "/persona",
        "/reload",
        "/restart",
        "/cost",
        "/export",
        "/search",
        "/model",
        "/cd",
        "/rollback",
        "/config",
        "/prompt",
        "/profile",
        "/changes",
        "/open",
        "/python",
        "/reset-python",
        "/deps",
        "/impact",
        "/q",
        "/exit",
    ]

    def _completer(text: str, state: int) -> str | None:
        """Readline completer function."""
        if not text.startswith("/"):
            return None
        # Filter commands by prefix
        candidates = [c for c in commands if c.startswith(text)]
        if state < len(candidates):
            return candidates[state] + " "
        return None

    _readline.set_completer(_completer)  # type: ignore[attr-defined]
    _readline.parse_and_bind("tab: complete")  # type: ignore[attr-defined]
    _readline.set_completer_delims(" \t\n")  # type: ignore[attr-defined]


def read_multiline(repl: Repl, mode_tag: str, wd_display: str) -> str:
    """Read a potentially multi-line input from the user.
    Lines ending with \\ continue to the next line.
    Returns the joined input with trailing backslash-newlines resolved.
    """
    lines: list[str] = []
    while True:
        prompt = f"  {bold(mode_tag)} {cyan(wd_display)} {green('❯')} "
        if lines:
            # Continuation prompt (no prompt symbol)
            prompt = f"  {bold(mode_tag)} {cyan(wd_display)} {dim('│')} "
        try:
            raw = input(prompt)
        except EOFError, KeyboardInterrupt:
            return ""  # signal cancellation

        if not raw and not lines:
            # Empty line with no prior input — skip
            return ""

        # Check for /editor trigger at empty prompt
        if not lines and raw.strip().lower() == "/editor":
            return open_external_editor()

        if raw.endswith("\\"):
            # Line continuation: strip trailing \ and collect
            lines.append(raw[:-1])
            continue

        lines.append(raw)
        break

    return "".join(lines)


def open_external_editor() -> str:
    """Open an external text editor for composing long messages.

    Uses $EDITOR or $VISUAL environment variable (Unix convention).
    Falls back to normal input if no editor is configured.
    Returns the edited content or '' if cancelled/empty.

    Temp files are created in a dedicated temp directory that is
    cleaned up entirely in the ``finally`` block, catching any
    editor backup files (``.swp``, ``~``, etc.) that may be created.
    """
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if not editor:
        print(f"  {yellow('⚠')} {dim('No editor configured. Set $EDITOR or $VISUAL environment variable.')}")
        print(f"  {dim('Falling back to multi-line input (use \\ to continue lines).')}")
        return ""

    temp_dir: str | None = None
    try:
        # Create a dedicated temp directory so editor backup files
        # (e.g. .swp, .swo, file~) are confined and cleaned up together
        temp_dir = tempfile.mkdtemp(prefix="agent_editor_")
        temp_path = os.path.join(temp_dir, "message.md")

        # Write instructions
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write("# Write your message below. Lines starting with # are ignored.\n")
            f.write("# Save and exit the editor when done.\n")
            f.write("# Close without saving to cancel.\n")

        # Launch the editor
        try:
            result = subprocess.call([editor, temp_path])
        except (OSError, FileNotFoundError) as exc:
            print(f"  {yellow('⚠')} {dim(f'Could not launch editor "{editor}": {exc}')}")
            return ""

        if result != 0:
            print(f"  {yellow('⚠')} {dim('Editor exited with non-zero status. Cancelled.')}")
            return ""

        # Read the file back
        try:
            with open(temp_path, encoding="utf-8") as f:
                content = f.read()
        except OSError as exc:
            print(f"  {yellow('⚠')} {dim(f'Could not read editor output: {exc}')}")
            return ""

        # Strip comment lines and blank content
        result_lines: list[str] = []
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            result_lines.append(line)

        result_text = "\n".join(result_lines).strip()
        if not result_text:
            print(f"  {dim('Editor content was empty. Message cancelled.')}")
            return ""

        print(f"  {dim(f'✓ Content captured from editor ({len(result_text)} chars).')}")
        return result_text

    finally:
        # Clean up entire temp directory (catches editor backup files)
        if temp_dir is not None:
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass


def get_file_icon(filepath: str) -> str:
    """Get an emoji icon for a file based on its extension."""
    _, ext = os.path.splitext(filepath)
    icons = {
        ".py": "🐍",
        ".js": "📜",
        ".ts": "📘",
        ".tsx": "⚛️",
        ".jsx": "⚛️",
        ".json": "📋",
        ".md": "📝",
        ".yaml": "⚙️",
        ".yml": "⚙️",
        ".html": "🌐",
        ".css": "🎨",
        ".sh": "💻",
        ".sql": "🗃️",
        ".toml": "⚙️",
        ".ini": "⚙️",
    }
    return icons.get(ext.lower(), "📄")


def format_size(bytes_size: int) -> str:
    """Format file size in human-readable format."""
    size = float(bytes_size)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def preview_file(filepath: str) -> None:
    """Show a file preview with line numbers and metadata."""
    print(f"\n  {bold(f'File: {filepath}')}")
    print(f"  {'─' * 60}")

    try:
        with open(filepath, encoding="utf-8") as f:
            lines = f.readlines()

        max_preview = 30
        for i, line in enumerate(lines[:max_preview], 1):
            line_num = dim(f"{i:4d}")
            print(f"  {line_num}│{line.rstrip()}")

        if len(lines) > max_preview:
            remaining = len(lines) - max_preview
            print(f"  {dim(f'... and {remaining} more lines')}")

        # Show file metadata
        try:
            size = os.path.getsize(filepath)
            print(f"\n  {dim(f'{len(lines)} lines, {format_size(size)}')}")
        except OSError:
            pass

    except Exception as e:
        print(f"  {red(f'Error reading file: {e}')}")


def search_preview(text: str, pattern: str, use_regex: bool) -> str:
    """Extract ~120 chars around the match for a preview."""
    import re as regex_module

    if use_regex:
        match = regex_module.search(pattern, text)
        if not match:
            return text[:120]
        start = max(0, match.start() - 40)
        end = min(len(text), match.end() + 80)
    else:
        lower_text = text.lower()
        lower_pattern = pattern.lower()
        idx = lower_text.find(lower_pattern)
        if idx == -1:
            return text[:120]
        start = max(0, idx - 40)
        end = min(len(text), idx + len(pattern) + 80)

    preview = text[start:end]
    if start > 0:
        preview = "..." + preview
    if end < len(text):
        preview = preview + "..."
    # Replace newlines with spaces for single-line display
    preview = preview.replace("\n", " ").strip()
    if len(preview) > 120:
        preview = preview[:117] + "..."
    return dim(preview)
