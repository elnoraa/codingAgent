"""Tests for configuration profiles."""

from __future__ import annotations

import json
import os
import tempfile

from src.profiles import delete_profile, list_profiles, load_profile, save_profile


def test_save_and_load_profile() -> None:
    """Save a profile, verify file exists, load it back."""
    with tempfile.TemporaryDirectory() as tmpdir:
        data = {
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": 8192,
            "temperature": 0.5,
            "top_p": 0.9,
        }
        filepath = save_profile("test-profile", data, tmpdir)
        assert os.path.isfile(filepath)
        assert "test-profile" in filepath

        loaded = load_profile("test-profile", tmpdir)
        assert loaded is not None
        assert loaded.name == "test-profile"
        assert loaded.model == "claude-3-5-sonnet-20241022"
        assert loaded.max_tokens == 8192
        assert loaded.temperature == 0.5
        assert loaded.top_p == 0.9
        assert loaded.system_prompt == ""
        assert loaded.custom_persona == ""


def test_load_nonexistent_returns_none() -> None:
    """Loading a profile that doesn't exist should return None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = load_profile("nonexistent", tmpdir)
        assert result is None


def test_list_profiles() -> None:
    """List profiles should return all saved profiles."""
    with tempfile.TemporaryDirectory() as tmpdir:
        save_profile("profile-a", {"model": "deepseek-chat"}, tmpdir)
        save_profile("profile-b", {"model": "claude-3-haiku", "temperature": 0.3}, tmpdir)
        profiles = list_profiles(tmpdir)
        assert len(profiles) == 2
        names = {p.name for p in profiles}
        assert names == {"profile-a", "profile-b"}
        # Verify sorting
        assert profiles[0].name == "profile-a"


def test_delete_profile() -> None:
    """Delete a profile, verify it's removed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        save_profile("delete-me", {"model": "test-model"}, tmpdir)
        assert os.path.isfile(os.path.join(tmpdir, "profiles", "delete-me.json"))

        result = delete_profile("delete-me", tmpdir)
        assert result is True
        assert not os.path.isfile(os.path.join(tmpdir, "profiles", "delete-me.json"))

        # Deleting non-existent returns False
        result = delete_profile("does-not-exist", tmpdir)
        assert result is False


def test_profile_empty_list() -> None:
    """List profiles when none saved should return empty list."""
    with tempfile.TemporaryDirectory() as tmpdir:
        profiles = list_profiles(tmpdir)
        assert profiles == []


def test_profile_json_format() -> None:
    """Verify saved profile JSON has correct structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        data = {
            "model": "test-model",
            "max_tokens": 4096,
            "temperature": 0.7,
            "top_p": 0.95,
            "system_prompt": "Custom system prompt",
            "custom_persona": "Friendly assistant",
        }
        filepath = save_profile("full-profile", data, tmpdir)
        with open(filepath, encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["name"] == "full-profile"
        assert saved["model"] == "test-model"
        assert saved["max_tokens"] == 4096
        assert saved["temperature"] == 0.7
        assert saved["top_p"] == 0.95
        assert saved["system_prompt"] == "Custom system prompt"
        assert saved["custom_persona"] == "Friendly assistant"
