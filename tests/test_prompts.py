"""Tests for the prompt library."""
from __future__ import annotations

import os
import tempfile

from src.prompts import BUILTIN_PROMPTS, PromptTemplate, list_prompts, load_prompt, save_prompt


def test_list_prompts_includes_builtins() -> None:
    """Listing prompts should include all built-in templates."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prompts = list_prompts(tmpdir)
        names = {p.name for p in prompts}
        for builtin_name in BUILTIN_PROMPTS:
            assert builtin_name in names, f"Built-in prompt '{builtin_name}' missing from list"
        # Verify at least one built-in is marked correctly
        refactor = next(p for p in prompts if p.name == "refactor")
        assert refactor.is_builtin is True


def test_save_and_load_custom_prompt() -> None:
    """Saving a custom prompt, then loading it should return the same content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = save_prompt("my-test-prompt", "Hello world", tmpdir)
        assert os.path.isfile(filepath)
        assert "my-test-prompt" in filepath

        loaded = load_prompt("my-test-prompt", tmpdir)
        assert loaded is not None
        assert loaded.name == "my-test-prompt"
        assert loaded.content == "Hello world"
        assert loaded.is_builtin is False
        assert loaded.filepath is not None
        assert os.path.isfile(loaded.filepath)


def test_load_nonexistent_prompt_returns_none() -> None:
    """Loading a prompt that doesn't exist should return None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = load_prompt("nonexistent-prompt-xyz", tmpdir)
        assert result is None


def test_custom_prompt_takes_priority() -> None:
    """Custom prompts should take priority over built-in prompts with the same name."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Save a custom prompt with the same name as a built-in
        save_prompt("refactor", "Custom refactor instructions", tmpdir)
        loaded = load_prompt("refactor", tmpdir)
        assert loaded is not None
        assert loaded.content == "Custom refactor instructions"
        assert loaded.is_builtin is False


def test_list_prompts_shows_custom_and_builtin() -> None:
    """Listing should show both built-in and custom prompts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        save_prompt("my-custom", "Custom content", tmpdir)
        prompts = list_prompts(tmpdir)
        names = {p.name for p in prompts}
        assert "my-custom" in names
        assert "refactor" in names
        # Count: builtins + 1 custom
        assert len(prompts) == len(BUILTIN_PROMPTS) + 1
