"""Tests for the prompt library."""

from __future__ import annotations

import os
import tempfile

from src.prompts import BUILTIN_PROMPTS, list_prompts, load_prompt, save_prompt


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


def test_build_system_prompt_includes_communication_protocol() -> None:
    """The built system prompt must include the Communication Protocol section."""
    from unittest.mock import MagicMock

    from src.repl.system_prompt import build_system_prompt

    # Create a minimal mock REPL
    repl = MagicMock()
    repl.mode = "code"
    repl.working_directory = os.getcwd()
    repl.system_prompt = "Test system prompt"
    repl._custom_persona = ""
    repl._context_files = []

    result = build_system_prompt(repl)

    # The Communication Protocol must be present and at the top (early in the prompt)
    assert "## Communication Protocol (MANDATORY)" in result, (
        "Communication Protocol heading missing from built system prompt"
    )
    assert "**🧠 Think out loud first**" in result, "Think out loud step missing from built system prompt"
    assert "**📋 Show the plan step-by-step**" in result, "Show plan step missing from built system prompt"
    assert "**🔧 Execute step-by-step**" in result, "Execute step-by-step missing from built system prompt"
    assert "**✅ Summarize after**" in result, "Summarize after step missing from built system prompt"

    # Verify it appears before the base prompt text
    comm_pos = result.index("## Communication Protocol (MANDATORY)")
    base_pos = result.index("Test system prompt")
    assert comm_pos < base_pos, "Communication Protocol should appear before the base system prompt"


def test_build_system_prompt_includes_protocol_in_plan_mode() -> None:
    """The protocol should also appear in PLAN mode."""
    from unittest.mock import MagicMock

    from src.repl.system_prompt import build_system_prompt

    repl = MagicMock()
    repl.mode = "plan"
    repl.working_directory = os.getcwd()
    repl.system_prompt = "CODE prompt"
    repl._custom_persona = ""
    repl._context_files = []

    result = build_system_prompt(repl)
    assert "## Communication Protocol (MANDATORY)" in result


def test_build_system_prompt_includes_protocol_in_ask_mode() -> None:
    """The protocol should also appear in ASK mode."""
    from unittest.mock import MagicMock

    from src.repl.system_prompt import build_system_prompt

    repl = MagicMock()
    repl.mode = "ask"
    repl.working_directory = os.getcwd()
    repl.system_prompt = "CODE prompt"
    repl._custom_persona = ""
    repl._context_files = []

    result = build_system_prompt(repl)
    assert "## Communication Protocol (MANDATORY)" in result
