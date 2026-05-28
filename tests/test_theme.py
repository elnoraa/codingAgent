"""Tests for theme support."""
from __future__ import annotations

from src.theme import Theme, from_dict


def test_default_theme() -> None:
    """Default theme should have all attributes."""
    theme = Theme()
    assert theme.prompt is not None
    assert theme.success is not None
    assert theme.warning is not None
    assert theme.error is not None
    assert theme.info is not None


def test_wrap_text() -> None:
    """Wrap should add ANSI codes around text."""
    theme = Theme()
    result = theme.wrap("\033[31m", "hello")
    assert result == "\033[31mhello\033[0m"
    assert result.endswith("\033[0m")


def test_primary_method() -> None:
    """Primary method should wrap text in prompt color."""
    theme = Theme()
    result = theme.primary("test")
    assert result.startswith("\033[")
    assert result.endswith("\033[0m")
    assert "test" in result


def test_from_dict_with_named_colors() -> None:
    """Create theme from dict with named colors."""
    theme = from_dict({
        "primary": "cyan",
        "success": "green",
        "error": "red",
        "warning": "yellow",
    })
    assert "\033[36m" in theme.primary("x")  # cyan
    assert "\033[32m" in theme.success_text("x")  # green
    assert "\033[31m" in theme.error_text("x")  # red
    assert "\033[33m" in theme.warning_text("x")  # yellow


def test_from_dict_partial() -> None:
    """Partial config should only override specified colors."""
    theme = from_dict({"primary": "bright-magenta"})
    assert "\033[95m" in theme.primary("x")  # bright magenta
    # Other colors should remain default
    assert "\033[32m" in theme.success_text("x")  # green (default)


def test_mode_color() -> None:
    """Mode color should return correct color per mode."""
    theme = Theme()
    assert theme.mode_color("code") == theme.code_mode
    assert theme.mode_color("plan") == theme.plan_mode
    assert theme.mode_color("ask") == theme.ask_mode


def test_dim_and_bold() -> None:
    """Dim and bold helper methods."""
    theme = Theme()
    assert theme.dim("text").startswith("\033[2m")
    assert theme.bold("text").startswith("\033[1m")


def test_empty_theme_no_wrap() -> None:
    """Empty color code should return text unchanged."""
    theme = Theme()
    result = theme.wrap("", "hello")
    assert result == "hello"
