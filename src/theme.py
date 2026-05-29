"""Theme support for the Coding Agent.

Provides user-configurable color schemes via config.json.
Customize the ANSI colors used for prompts, modes, separators,
and status indicators throughout the UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _code(n: int) -> str:
    return f"\033[{n}m"


R = _code(0)  # reset


@dataclass
class Theme:
    """Color theme for the Coding Agent UI.

    Each attribute is an ANSI color code (string like "\033[36m").
    Set to empty string to use the terminal's default color.
    """

    # Primary UI elements
    prompt: str = _code(36)  # cyan
    separator: str = _code(2)  # dim
    input_symbol: str = _code(32)  # green

    # Mode indicators
    code_mode: str = _code(36)  # cyan
    plan_mode: str = _code(33)  # yellow
    ask_mode: str = _code(35)  # magenta

    # Status / feedback
    success: str = _code(32)  # green
    warning: str = _code(33)  # yellow
    error: str = _code(31)  # red
    info: str = _code(2)  # dim
    highlight: str = _code(1)  # bold

    # Syntax highlighting (Pygments theme name for rich/rich.markdown)
    syntax_theme: str = "monokai"

    # ANSI-based syntax highlighting
    keyword: str = _code(34)  # blue
    string_val: str = _code(32)  # green
    number_val: str = _code(36)  # cyan
    boolean_val: str = _code(33)  # yellow
    null_val: str = _code(2)  # dim

    def wrap(self, color_code: str, text: str) -> str:
        """Wrap text in a color code, with reset."""
        if not color_code:
            return text
        return f"{color_code}{text}{R}"

    def primary(self, text: str) -> str:
        return self.wrap(self.prompt, text)

    def dim(self, text: str) -> str:
        return self.wrap(self.info, text)

    def success_text(self, text: str) -> str:
        return self.wrap(self.success, text)

    def warning_text(self, text: str) -> str:
        return self.wrap(self.warning, text)

    def error_text(self, text: str) -> str:
        return self.wrap(self.error, text)

    def bold(self, text: str) -> str:
        return self.wrap(self.highlight, text)

    def mode_color(self, mode: str) -> str:
        """Return the color code for a given mode."""
        if mode == "plan":
            return self.plan_mode
        if mode == "ask":
            return self.ask_mode
        return self.code_mode


# Color name to ANSI code mapping
COLOR_NAMES: dict[str, str] = {
    "black": _code(30),
    "red": _code(31),
    "green": _code(32),
    "yellow": _code(33),
    "blue": _code(34),
    "magenta": _code(35),
    "cyan": _code(36),
    "white": _code(37),
    "bright-black": _code(90),
    "bright-red": _code(91),
    "bright-green": _code(92),
    "bright-yellow": _code(93),
    "bright-blue": _code(94),
    "bright-magenta": _code(95),
    "bright-cyan": _code(96),
    "bright-white": _code(97),
    "dim": _code(2),
    "bold": _code(1),
    "none": "",
    "default": "",
}

# Map old attribute names to new theme field names
_ATTR_MAP: dict[str, str] = {
    "primary": "prompt",
    "success": "success",
    "warning": "warning",
    "error": "error",
    "info": "info",
    "highlight": "highlight",
    "syntax_theme": "syntax_theme",
    "keyword": "keyword",
    "string": "string_val",
    "number": "number_val",
    "boolean": "boolean_val",
    "null": "null_val",
    "input": "input_symbol",
    "separator": "separator",
}


def _resolve_color(value: Any) -> str:
    """Resolve a color config value to an ANSI code."""
    if isinstance(value, str):
        # Check if it's a named color
        lower_val = value.lower().strip()
        if lower_val in COLOR_NAMES:
            return COLOR_NAMES[lower_val]
        # Check if it's a direct ANSI code like "36"
        if value.isdigit() or (value.startswith("0") and value[1:].isdigit()):
            return _code(int(value))
        # Try as hex or raw
        if value.startswith("\\033") or value.startswith("\033"):
            return value
    return value if isinstance(value, str) else ""


def from_dict(data: dict[str, Any]) -> Theme:
    """Create a Theme from a configuration dictionary.

    Example config:
    {
        "theme": {
            "primary": "cyan",
            "success": "green",
            "warning": "yellow",
            "error": "red",
            "info": "dim",
        }
    }
    """
    theme = Theme()
    for key, value in data.items():
        mapped_key = _ATTR_MAP.get(key, key)
        if hasattr(theme, mapped_key):
            resolved = _resolve_color(value)
            if resolved is not None:
                setattr(theme, mapped_key, resolved)
    return theme


# Default theme instance
DEFAULT_THEME = Theme()
