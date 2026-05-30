"""ANSI terminal escape sequence sanitization.

Provides protection against ANSI escape code injection attacks by stripping
dangerous sequences (cursor positioning, screen clearing, title setting, etc.)
while preserving common formatting sequences (colors, bold, dim).

Extracted from ``src/security.py`` to give ANSI sanitization its own module
(Single Responsibility Principle).
"""

from __future__ import annotations

import re as _re_module
from typing import Any

# Dangerous ANSI sequences that should be stripped from output before rendering.
# These can be used for terminal injection attacks (cursor positioning, screen
# clearing, title setting, keyboard remapping, etc.).
_DANGEROUS_ANSI_PATTERNS: list[Any] = [
    _re_module.compile(r"\x1b\[2J"),  # Clear entire screen
    _re_module.compile(r"\x1b\[3J"),  # Clear scrollback
    _re_module.compile(r"\x1b\[0J"),  # Clear from cursor to end of screen
    _re_module.compile(r"\x1b\[1J"),  # Clear from beginning to cursor
    _re_module.compile(r"\x1b\[\d*(?:;\d*)?[Hf]"),  # Cursor positioning
    _re_module.compile(r"\x1b\[\?25[lh]"),  # Hide/show cursor
    _re_module.compile(r"\x1b\]0;.+?\x07"),  # Set terminal title
    _re_module.compile(r"\x1b\]2;.+?\x07"),  # Set terminal title (alternative)
    _re_module.compile(r"\x1b\[\d*[n]"),  # Device status reports
    _re_module.compile(r"\x1b\[[0-9;]*[t]"),  # XTerm window ops
    _re_module.compile(r"\x1bc", _re_module.ASCII),  # RIS (Reset to Initial State)
    _re_module.compile(r"\x1b][\\_\[\]]"),  # String terminators
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
        result = pattern.sub("", result)
    return result
