"""Markdown rendering and syntax highlighting utilities.

Provides functions for rendering Markdown to the terminal,
syntax-highlighting code blocks, and detecting programming languages
from file extensions.
"""

from __future__ import annotations

import os

from .formatting import dim


# ── Markdown Rendering & Syntax Highlighting ──────────────────────────────


def render_markdown(text: str, syntax_theme: str = "monokai") -> None:
    """Render Markdown text to the terminal using rich.

    Applies syntax highlighting to code blocks within the Markdown.
    Falls back to plain print() if Markdown parsing fails.
    """
    # Sanitize dangerous ANSI sequences before rendering
    from .security import strip_dangerous_ansi

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
    from .security import strip_dangerous_ansi

    code = strip_dangerous_ansi(code)
    try:
        from rich.syntax import Syntax
        from io import StringIO
        from rich.console import Console

        syntax = Syntax(code, language, theme=theme, line_numbers=False)
        # Convert the rich renderable to an ANSI string
        buf = StringIO()
        console = Console(file=buf, force_terminal=True, width=100)
        console.print(syntax, end="")
        return buf.getvalue()
    except Exception:
        return code
