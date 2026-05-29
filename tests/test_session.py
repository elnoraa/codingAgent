"""Tests for session save/load functionality."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

from src.session import save_session, load_session, list_sessions, delete_session, _redact_text, _redact_messages


@pytest.fixture
def temp_working_dir() -> Iterator[str]:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def test_save_session_creates_file(temp_working_dir: str) -> None:
    messages: list[dict[str, object]] = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]
    path = save_session(
        name="test-session",
        messages=messages,
        mode="code",
        working_directory=temp_working_dir,
        model="deepseek-chat",
    )
    assert os.path.isfile(path)
    assert path.endswith("test-session.json")

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert data["name"] == "test-session"
    assert data["mode"] == "code"
    assert data["model"] == "deepseek-chat"
    assert len(data["messages"]) == 2


def test_save_session_sanitizes_name(temp_working_dir: str) -> None:
    path = save_session(
        name="My Session!!!",
        messages=[],
        mode="plan",
        working_directory=temp_working_dir,
        model="claude-3-5-sonnet",
    )
    assert "My-Session" in path
    assert "!!!" not in path


def test_save_session_invalid_name(temp_working_dir: str) -> None:
    result = save_session(
        name="",
        messages=[],
        mode="code",
        working_directory=temp_working_dir,
        model="test",
    )
    assert result.startswith("Error:")


def test_load_session_returns_data(temp_working_dir: str) -> None:
    save_session(
        name="my-session",
        messages=[{"role": "user", "content": "test"}],
        mode="code",
        working_directory=temp_working_dir,
        model="test-model",
    )

    data = load_session("my-session", temp_working_dir)
    assert data is not None
    assert data["name"] == "my-session"
    assert data["mode"] == "code"
    assert data["model"] == "test-model"


def test_load_session_not_found(temp_working_dir: str) -> None:
    data = load_session("nonexistent", temp_working_dir)
    assert data is None


def test_load_session_empty_name(temp_working_dir: str) -> None:
    data = load_session("", temp_working_dir)
    assert data is None


def test_list_sessions_empty(temp_working_dir: str) -> None:
    sessions = list_sessions(temp_working_dir)
    assert sessions == []


def test_list_sessions_returns_sorted(temp_working_dir: str) -> None:
    save_session(
        name="alpha", messages=[], mode="code",
        working_directory=temp_working_dir, model="m1",
    )
    save_session(
        name="beta", messages=[{"role": "user", "content": "x"}], mode="plan",
        working_directory=temp_working_dir, model="m2",
    )

    sessions = list_sessions(temp_working_dir)
    assert len(sessions) == 2

    names = [s["name"] for s in sessions]
    assert "alpha" in names
    assert "beta" in names


def test_list_sessions_ignores_non_json(temp_working_dir: str) -> None:
    # Create a non-JSON file in sessions dir
    s_dir = Path(temp_working_dir) / "sessions"
    s_dir.mkdir(exist_ok=True)
    (s_dir / "readme.txt").write_text("not a session", encoding="utf-8")

    save_session(
        name="valid", messages=[], mode="code",
        working_directory=temp_working_dir, model="m",
    )

    sessions = list_sessions(temp_working_dir)
    assert len(sessions) == 1
    assert sessions[0]["name"] == "valid"


def test_delete_session_removes_file(temp_working_dir: str) -> None:
    save_session(
        name="temp", messages=[], mode="code",
        working_directory=temp_working_dir, model="m",
    )
    assert delete_session("temp", temp_working_dir) is True
    assert load_session("temp", temp_working_dir) is None


def test_delete_session_not_found(temp_working_dir: str) -> None:
    assert delete_session("nonexistent", temp_working_dir) is False


def test_round_trip_preserves_data(temp_working_dir: str) -> None:
    original_messages: list[dict[str, object]] = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "response"},
    ]
    save_session(
        name="roundtrip", messages=original_messages, mode="plan",
        working_directory=temp_working_dir, model="deepseek-chat",
    )

    data = load_session("roundtrip", temp_working_dir)
    assert data is not None
    loaded_msgs = cast("list[dict[str, object]]", data.get("messages", []))
    assert len(loaded_msgs) == 2
    assert loaded_msgs[0]["content"] == "first"
    assert loaded_msgs[1]["content"] == "response"
    assert cast("str", data["mode"]) == "plan"


# ── Redaction tests ────────────────────────────────────────────────────────────


class TestSessionRedaction:
    """Verify sensitive data redaction in session files."""

    def test_redact_text_api_key(self) -> None:
        """API keys in text should be redacted."""
        result = _redact_text("sk-test-key-abcdefghijklmnopqrstuvwx")
        assert "sk-***REDACTED***" in result
        assert "sk-test-key-abcdefghijklmnopqrstuvwx" not in result

    def test_redact_text_password(self) -> None:
        """Password assignments in text should be redacted."""
        result = _redact_text('password = "mysecret123"')
        assert "***REDACTED***" in result
        assert "mysecret123" not in result

    def test_redact_text_normal(self) -> None:
        """Normal text should be unchanged."""
        text = "Hello, this is a normal conversation about Python."
        assert _redact_text(text) == text

    def test_redact_text_empty(self) -> None:
        """Empty string should return empty."""
        assert _redact_text("") == ""

    def test_redact_messages_string_content(self) -> None:
        """String message content should be redacted."""
        messages: list[dict[str, object]] = [
            {"role": "user", "content": "My key is sk-test-key-abcdefghijklmnopqrstuvwx"},
        ]
        redacted = _redact_messages(messages)
        # Verify original is not modified
        orig_content = cast("str", messages[0]["content"])
        assert "sk-test-key-abcdefghijklmnopqrstuvwx" in orig_content
        # Verify redacted has the marker
        content = cast("str", redacted[0].get("content", ""))
        assert isinstance(content, str)
        assert "sk-***REDACTED***" in content
        assert "sk-test-key-abcdefghijklmnopqrstuvwx" not in content

    def test_redact_messages_list_content(self) -> None:
        """List-type message content (tool results) should be redacted."""
        messages: list[dict[str, object]] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "password = hunter2"},
                ],
            },
        ]
        redacted = _redact_messages(messages)
        content = redacted[0].get("content", [])
        assert isinstance(content, list)
        assert len(content) == 1
        assert "hunter2" not in str(content)

    def test_session_save_redacts_api_keys(self, temp_working_dir: str) -> None:
        """Saving a session should redact API keys from stored data."""
        messages: list[dict[str, object]] = [
            {"role": "user", "content": "My API key: sk-test-key-abcdefghijklmnopqrstuvwx"},
        ]
        path = save_session(
            name="redact-test",
            messages=messages,
            mode="code",
            working_directory=temp_working_dir,
            model="test-model",
        )
        assert os.path.isfile(path)

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        stored_content = data["messages"][0]["content"]
        assert "sk-***REDACTED***" in stored_content
        assert "sk-test-key-abcdefghijklmnopqrstuvwx" not in stored_content

    def test_session_save_does_not_modify_original(self, temp_working_dir: str) -> None:
        """The original messages list should not be modified by save_session."""
        original_key = "sk-test-key-abcdefghijklmnopqrstuvwx"
        messages: list[dict[str, object]] = [
            {"role": "user", "content": f"My API key: {original_key}"},
        ]

        save_session(
            name="no-modify-test",
            messages=messages,
            mode="code",
            working_directory=temp_working_dir,
            model="test-model",
        )

        # Original should still have the plaintext key
        orig_content = cast("str", messages[0]["content"])
        assert original_key in orig_content

    def test_session_round_trip_redacted(self, temp_working_dir: str) -> None:
        """Saving and loading should preserve the redacted state."""
        messages: list[dict[str, object]] = [
            {"role": "user", "content": "password = 'supersecret'"},
        ]
        save_session(
            name="roundtrip-redact",
            messages=messages,
            mode="code",
            working_directory=temp_working_dir,
            model="test",
        )

        data = load_session("roundtrip-redact", temp_working_dir)
        assert data is not None
        loaded_msgs = cast("list[dict[str, object]]", data.get("messages", []))
        content: str = cast("str", loaded_msgs[0].get("content", "")) if loaded_msgs else ""
        assert "supersecret" not in content
        assert "***REDACTED***" in content
