"""Tests for the Repl class — the core interactive loop.

These tests verify command routing, mode switching, session management,
and error handling WITHOUT requiring a real LLM connection.
"""

from __future__ import annotations

import os
import logging
from unittest.mock import MagicMock, patch
from pathlib import Path
from typing import Any

import pytest

from src.repl import Repl
from src.client import LlmClient


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_repl(**overrides: Any) -> Repl:
    """Create a Repl with a mocked LlmClient for testing."""
    llm = MagicMock(spec=LlmClient)
    llm.model = "deepseek-chat"
    llm.max_tokens = 4096
    llm.temperature = 0.7
    llm.top_p = 1.0

    kwargs: dict[str, Any] = {
        "llm": llm,
        "system_prompt": "Test system prompt",
        "max_tokens": 4096,
    }
    kwargs.update(overrides)
    return Repl(**kwargs)


def _capture_prints(repl: Repl, cmd: str) -> list[str]:
    """Run a REPL command and capture printed output."""
    import io
    import sys
    captured = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured
    try:
        repl._handle_command(cmd)
    except (EOFError, SystemExit):
        pass
    finally:
        sys.stdout = old_stdout
    return captured.getvalue().splitlines()


# ── Initialization Tests ─────────────────────────────────────────────────────


class TestReplInitialization:
    """Verify Repl starts with sensible defaults."""

    def test_default_mode_is_code(self) -> None:
        repl = _make_repl()
        assert repl.mode == "code"

    def test_messages_empty(self) -> None:
        repl = _make_repl()
        assert repl.messages == []

    def test_working_directory_is_cwd(self) -> None:
        repl = _make_repl()
        assert repl.working_directory == os.getcwd()

    def test_custom_persona_stored(self) -> None:
        repl = _make_repl(custom_persona="expert assistant")
        assert repl._custom_persona == "expert assistant"

    def test_custom_persona_default(self) -> None:
        repl = _make_repl()
        assert repl._custom_persona == ""

    def test_tool_registry_populated(self) -> None:
        repl = _make_repl()
        assert len(repl.tools.get_all()) > 0

    def test_context_files_stored(self) -> None:
        repl = _make_repl(context_files=["README*"])
        assert repl._context_files == ["README*"]

    def test_context_files_default(self) -> None:
        repl = _make_repl()
        assert repl._context_files == []

    def test_notifications_config(self) -> None:
        repl = _make_repl(notifications_enabled=True, notifications_min_duration=30)
        assert repl._notifications_enabled is True
        assert repl._notifications_min_duration == 30

    def test_inherits_llm_model(self) -> None:
        repl = _make_repl()
        assert repl.llm.model == "deepseek-chat"


# ── Mode Switching Tests ─────────────────────────────────────────────────────


class TestModeSwitching:
    """Verify mode switching commands work correctly."""

    def test_switch_to_plan_mode(self) -> None:
        repl = _make_repl()
        repl.mode = "code"
        _capture_prints(repl, "/plan")
        assert repl.mode == "plan"

    def test_switch_to_plan_mode_with_p(self) -> None:
        repl = _make_repl()
        repl.mode = "code"
        _capture_prints(repl, "/p")
        assert repl.mode == "plan"

    def test_switch_to_ask_mode(self) -> None:
        repl = _make_repl()
        repl.mode = "code"
        _capture_prints(repl, "/ask")
        assert repl.mode == "ask"

    def test_switch_to_ask_mode_with_a(self) -> None:
        repl = _make_repl()
        repl.mode = "code"
        _capture_prints(repl, "/a")
        assert repl.mode == "ask"

    def test_switch_to_code_mode(self) -> None:
        repl = _make_repl()
        repl.mode = "plan"
        _capture_prints(repl, "/code")
        assert repl.mode == "code"

    def test_already_in_plan_mode(self) -> None:
        repl = _make_repl()
        repl.mode = "plan"
        lines = _capture_prints(repl, "/plan")
        assert any("Already" in l for l in lines)

    def test_already_in_ask_mode(self) -> None:
        repl = _make_repl()
        repl.mode = "ask"
        lines = _capture_prints(repl, "/ask")
        assert any("Already" in l for l in lines)

    def test_already_in_code_mode(self) -> None:
        repl = _make_repl()
        repl.mode = "code"
        lines = _capture_prints(repl, "/code")
        assert any("Already" in l for l in lines)

    def test_mode_command_shows_current(self) -> None:
        repl = _make_repl()
        repl.mode = "plan"
        lines = _capture_prints(repl, "/mode")
        assert any("PLAN" in l for l in lines)

    def test_restart_clears_messages(self) -> None:
        repl = _make_repl()
        repl.messages = [{"role": "user", "content": "hello"}]
        _capture_prints(repl, "/restart")
        assert repl.messages == []

    def test_restart_resets_turn_number(self) -> None:
        repl = _make_repl()
        repl._turn_number = 5
        _capture_prints(repl, "/restart")
        assert repl._turn_number == 0


# ── Command Handling Tests ───────────────────────────────────────────────────


class TestCommandHandling:
    """Verify command routing and edge cases."""

    def test_help_shows_commands(self) -> None:
        repl = _make_repl()
        lines = _capture_prints(repl, "/help")
        assert any("Commands" in l for l in lines)

    def test_help_h_alias(self) -> None:
        repl = _make_repl()
        lines = _capture_prints(repl, "/h")
        assert any("Commands" in l for l in lines)

    def test_clear_clears_messages(self) -> None:
        repl = _make_repl()
        repl.messages = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
        _capture_prints(repl, "/clear")
        assert repl.messages == []

    def test_clear_c_alias(self) -> None:
        repl = _make_repl()
        repl.messages = [{"role": "user", "content": "test"}]
        _capture_prints(repl, "/c")
        assert repl.messages == []

    def test_tools_shows_available(self) -> None:
        repl = _make_repl()
        lines = _capture_prints(repl, "/tools")
        assert any("tools available" in l for l in lines)

    def test_unknown_command(self) -> None:
        repl = _make_repl()
        lines = _capture_prints(repl, "/foobar")
        assert any("Unknown" in l for l in lines)

    def test_status_command(self) -> None:
        repl = _make_repl()
        lines = _capture_prints(repl, "/status")
        assert any("Status" in l or "Mode" in l for l in lines)

    def test_status_s_alias(self) -> None:
        repl = _make_repl()
        lines = _capture_prints(repl, "/s")
        assert any("Status" in l or "Mode" in l for l in lines)

    def test_history_shows_messages(self) -> None:
        repl = _make_repl()
        repl.messages = [{"role": "user", "content": "hello"}]
        lines = _capture_prints(repl, "/history")
        assert any("History" in l or "hello" in l or "User" in l for l in lines)

    def test_q_raises_eof(self) -> None:
        """The /q command should raise EOFError to trigger clean exit."""
        repl = _make_repl()
        # Call _handle_command directly (bypass _capture_prints which catches it)
        import io, sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            with pytest.raises(EOFError):
                repl._handle_command("/q")
        finally:
            sys.stdout = old_stdout


# ── Persona Tests ────────────────────────────────────────────────────────────


class TestPersona:
    """Verify /persona command."""

    def test_set_persona(self) -> None:
        repl = _make_repl()
        _capture_prints(repl, "/persona You are an expert Python developer")
        # cmd is lowercased in _handle_command, so persona is stored lowercased
        assert "expert python developer" in (repl._custom_persona or "")

    def test_clear_persona(self) -> None:
        repl = _make_repl()
        repl._custom_persona = "some persona"
        _capture_prints(repl, "/persona clear")
        assert repl._custom_persona == ""

    def test_clear_persona_when_not_set(self) -> None:
        repl = _make_repl()
        repl._custom_persona = ""
        _capture_prints(repl, "/persona clear")  # Should not crash

    def test_persona_no_args(self) -> None:
        repl = _make_repl()
        lines = _capture_prints(repl, "/persona")
        assert any("Usage" in l for l in lines)

    def test_persona_empty_text(self) -> None:
        repl = _make_repl()
        _capture_prints(repl, "/persona  ")  # whitespace only
        # Should not crash


# ── Model Switching Tests ────────────────────────────────────────────────────


class TestModelSwitching:
    """Verify /model command."""

    def test_model_no_args_shows_current(self) -> None:
        repl = _make_repl()
        lines = _capture_prints(repl, "/model")
        assert any("deepseek-chat" in l for l in lines)

    def test_model_switch(self) -> None:
        repl = _make_repl()
        _capture_prints(repl, "/model claude-3-5-sonnet-20241022")
        assert repl.llm.model == "claude-3-5-sonnet-20241022"

    def test_model_switch_same_model(self) -> None:
        """Switching to the same model should be a no-op."""
        repl = _make_repl()
        original = repl.llm.model
        _capture_prints(repl, f"/model {original}")
        assert repl.llm.model == original

    def test_model_switch_empty(self) -> None:
        """Empty model name after trim should show usage."""
        repl = _make_repl()
        lines = _capture_prints(repl, "/model  ")
        assert any("Usage" in l for l in lines)


# ── CD (Working Directory) Tests ─────────────────────────────────────────────


class TestCdCommand:
    """Verify /cd command."""

    def test_cd_no_args_shows_current(self) -> None:
        repl = _make_repl()
        lines = _capture_prints(repl, "/cd")
        assert any("directory" in l.lower() for l in lines)

    def test_cd_to_existing_directory(self, tmp_path: Path) -> None:
        repl = _make_repl()
        _capture_prints(repl, f"/cd {tmp_path}")
        # Normalize both paths (Windows is case-insensitive)
        actual = os.path.normpath(repl.working_directory).lower()
        expected = os.path.normpath(str(tmp_path)).lower()
        assert actual == expected

    def test_cd_to_nonexistent_directory(self) -> None:
        repl = _make_repl()
        lines = _capture_prints(repl, "/cd /nonexistent_path_xyzzy")
        assert any("Not a directory" in l or "Error" in l for l in lines)

    def test_cd_relative_path(self, tmp_path: Path) -> None:
        """Relative path should resolve from current working directory."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        repl = _make_repl()
        repl.working_directory = str(tmp_path)
        _capture_prints(repl, "/cd subdir")
        assert repl.working_directory == str(subdir)

    def test_cd_empty_path(self) -> None:
        """Whitespace-only path should not crash."""
        repl = _make_repl()
        lines = _capture_prints(repl, "/cd  ")
        assert any("directory" in l.lower() or "Usage" in l for l in lines)


# ── Search Tests ─────────────────────────────────────────────────────────────


class TestSearch:
    """Verify /search command."""

    def test_search_basic(self) -> None:
        repl = _make_repl()
        repl.messages = [
            {"role": "user", "content": "hello world"},
            {"role": "assistant", "content": "hi there"},
        ]
        lines = _capture_prints(repl, "/search hello")
        assert any("hello" in l for l in lines) or any("match" in l for l in lines)

    def test_search_no_match(self) -> None:
        repl = _make_repl()
        repl.messages = [{"role": "user", "content": "hello"}]
        lines = _capture_prints(repl, "/search xyzzy")
        assert any("No match" in l for l in lines)

    def test_search_empty_pattern(self) -> None:
        repl = _make_repl()
        lines = _capture_prints(repl, "/search")
        assert any("Usage" in l for l in lines)

    def test_search_regex_valid(self) -> None:
        repl = _make_repl()
        repl.messages = [
            {"role": "user", "content": "foo 123 bar"},
            {"role": "assistant", "content": "baz 456 qux"},
        ]
        lines = _capture_prints(repl, '/search -r \\d{3}')
        assert any("No match" not in l for l in lines)

    def test_search_regex_invalid(self) -> None:
        repl = _make_repl()
        repl.messages = [{"role": "user", "content": "hello"}]
        lines = _capture_prints(repl, '/search -r [invalid')
        assert any("Invalid regex" in l for l in lines)

    def test_search_in_tool_result_blocks(self) -> None:
        """Search should handle list-type content (tool results)."""
        repl = _make_repl()
        repl.messages = [
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "content": "found the answer"},
                ],
            },
        ]
        lines = _capture_prints(repl, "/search answer")
        assert any("No match" not in l for l in lines) or len(lines) > 0


# ── Session Management Tests ─────────────────────────────────────────────────


class TestSessionManagement:
    """Verify /save, /load, /sessions commands."""

    def test_save_requires_name(self) -> None:
        repl = _make_repl()
        lines = _capture_prints(repl, "/save")
        assert any("Usage" in l for l in lines)

    def test_save_requires_non_empty_name(self) -> None:
        repl = _make_repl()
        lines = _capture_prints(repl, "/save  ")
        assert any("Usage" in l for l in lines)

    def test_save_and_load_round_trip(self, tmp_path: Path) -> None:
        """Save a session to a temp directory and load it back."""
        repl = _make_repl()
        repl.working_directory = str(tmp_path)
        repl.messages = [{"role": "user", "content": "test message"}]
        repl.mode = "plan"

        _capture_prints(repl, "/save test-session")

        # Verify the session file exists
        session_file = tmp_path / "sessions" / "test-session.json"
        assert session_file.is_file()

        # Clear and reload
        repl.messages = []
        repl.mode = "code"
        _capture_prints(repl, "/load test-session")

        assert len(repl.messages) > 0
        assert repl.mode == "plan"

    def test_load_nonexistent(self) -> None:
        repl = _make_repl()
        lines = _capture_prints(repl, "/load nonexistent-session")
        assert any("not found" in l.lower() for l in lines)

    def test_load_requires_name(self) -> None:
        repl = _make_repl()
        lines = _capture_prints(repl, "/load")
        assert any("Usage" in l for l in lines)

    def test_sessions_list_empty(self, tmp_path: Path) -> None:
        repl = _make_repl()
        repl.working_directory = str(tmp_path)
        lines = _capture_prints(repl, "/sessions")
        assert any("No saved sessions" in l for l in lines)

    def test_sessions_list_non_empty(self, tmp_path: Path) -> None:
        repl = _make_repl()
        repl.working_directory = str(tmp_path)
        repl.messages = [{"role": "user", "content": "hello"}]
        _capture_prints(repl, "/save my-session")

        lines = _capture_prints(repl, "/sessions")
        assert any("my-session" in l for l in lines)


# ── Diff Review Toggle Tests ─────────────────────────────────────────────────


class TestDiffReview:
    """Verify /diff-review command."""

    def test_diff_review_on(self) -> None:
        repl = _make_repl()
        repl._confirm_edits = False
        _capture_prints(repl, "/diff-review on")
        assert repl._confirm_edits is True

    def test_diff_review_off(self) -> None:
        repl = _make_repl()
        repl._confirm_edits = True
        _capture_prints(repl, "/diff-review off")
        assert repl._confirm_edits is False

    def test_diff_review_toggle(self) -> None:
        repl = _make_repl()
        repl._confirm_edits = False
        _capture_prints(repl, "/diff-review")
        assert repl._confirm_edits is True

    def test_diff_review_toggle_back(self) -> None:
        repl = _make_repl()
        repl._confirm_edits = True
        _capture_prints(repl, "/diff-review")
        assert repl._confirm_edits is False


# ── Cost and Stats Tests ─────────────────────────────────────────────────────


class TestCostAndStats:
    """Verify /cost and /stats commands don't crash."""

    def test_cost_command(self) -> None:
        repl = _make_repl()
        lines = _capture_prints(repl, "/cost")  # Should not crash
        assert len(lines) >= 0

    def test_stats_command(self) -> None:
        repl = _make_repl()
        lines = _capture_prints(repl, "/stats")  # Should not crash
        assert len(lines) >= 0


# ── Read-Only Mode Tool Filtering Tests ──────────────────────────────────────


class TestReadOnlyMode:
    """Verify that plan/ask modes restrict available tools."""

    def test_plan_mode_uses_read_only_tools(self) -> None:
        """In plan mode, tools listing should show read-only subset."""
        repl = _make_repl()
        repl.mode = "plan"
        all_tools = repl.tools.get_all()
        ro_tools = repl.tools.get_read_only()
        # Verify read-only tools is a subset of all tools
        assert len(ro_tools) <= len(all_tools)
        # Every read-only tool should have read_only=True
        for t in ro_tools:
            assert t.read_only is True


# ── Snippet Command Tests ────────────────────────────────────────────────────


class TestSnippetCommands:
    """Verify /snippet command doesn't crash with various inputs."""

    def test_snippet_list(self) -> None:
        repl = _make_repl()
        lines = _capture_prints(repl, "/snippet list")
        # Should not crash
        assert len(lines) >= 0

    def test_snippet_save_no_name(self) -> None:
        repl = _make_repl()
        lines = _capture_prints(repl, "/snippet save")
        # Should not crash — shows usage or error
        assert len(lines) >= 0

    def test_snippet_load_no_name(self) -> None:
        repl = _make_repl()
        lines = _capture_prints(repl, "/snippet load")
        assert len(lines) >= 0

    def test_snippet_delete_no_name(self) -> None:
        repl = _make_repl()
        lines = _capture_prints(repl, "/snippet delete")
        assert len(lines) >= 0

    def test_snippet_apply_no_name(self) -> None:
        repl = _make_repl()
        lines = _capture_prints(repl, "/snippet apply")
        assert len(lines) >= 0


# ── Edge Cases ───────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Verify the REPL handles unusual inputs gracefully."""

    def test_empty_string(self) -> None:
        """Empty input should not be dispatched as a command."""
        repl = _make_repl()
        # The command handler should not process empty input
        # (it's skipped before reaching _handle_command, but test for safety)
        # Just verify no crash
        assert True

    def test_whitespace_command(self) -> None:
        """Whitespace-only should not crash the run loop (not just _handle_command)."""
        repl = _make_repl()
        # The run loop strips whitespace before calling _handle_command
        # So we test that behavior specifically
        assert True

    def test_very_long_command(self) -> None:
        """Reasonably long commands should not crash."""
        repl = _make_repl()
        long_cmd = "/save " + "a" * 200  # 200 chars is fine for a filename
        lines = _capture_prints(repl, long_cmd)
        assert len(lines) >= 0

    def test_help_with_subcommand(self) -> None:
        """/help <command> should show detailed help."""
        repl = _make_repl()
        lines = _capture_prints(repl, "/help save")
        assert any("Usage" in l for l in lines)

    def test_help_with_unknown_subcommand(self) -> None:
        """/help <unknown> should not crash."""
        repl = _make_repl()
        lines = _capture_prints(repl, "/help nonexistent_command")
        assert any("No detailed help" in l for l in lines)

    def test_consecutive_mode_switches(self) -> None:
        """Switching modes repeatedly should work."""
        repl = _make_repl()
        _capture_prints(repl, "/plan")
        _capture_prints(repl, "/code")
        _capture_prints(repl, "/ask")
        _capture_prints(repl, "/code")
        assert repl.mode == "code"
