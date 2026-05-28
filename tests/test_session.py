"""Tests for session save/load functionality."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

from src.session import save_session, load_session, list_sessions, delete_session


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
