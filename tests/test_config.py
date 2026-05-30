"""Tests for configuration loading."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from unittest.mock import patch

import pytest

from src.main import DEFAULT_SYSTEM_PROMPT, load_config


@pytest.fixture
def temp_config() -> Iterator[str]:
    """Create a temporary config.json and return its directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def test_load_config_requires_api_key() -> None:
    """Should exit when ANTHROPIC_API_KEY is missing."""
    with patch.dict(os.environ, {}, clear=True), pytest.raises(SystemExit):
        load_config()


def test_load_config_defaults() -> None:
    """Should return defaults when only API key is set."""
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-key"}, clear=True):
        config = load_config()
        assert config["api_key"] == "sk-test-key"
        assert config["model"] == "deepseek-chat"
        assert config["max_tokens"] == 4096
        assert config["system_prompt"] == DEFAULT_SYSTEM_PROMPT
        assert config["temperature"] == 0.7
        assert config["top_p"] == 1.0
        assert config["custom_persona"] == ""


def test_load_config_from_env() -> None:
    """Should read model and max_tokens from environment."""
    with patch.dict(
        os.environ,
        {
            "ANTHROPIC_API_KEY": "sk-test",
            "ANTHROPIC_MODEL": "claude-3-5-sonnet-20241022",
            "MAX_TOKENS": "8192",
        },
        clear=True,
    ):
        config = load_config()
        assert config["model"] == "claude-3-5-sonnet-20241022"
        assert config["max_tokens"] == 8192


def test_load_config_from_config_json(temp_config: str) -> None:
    """Should read settings from config.json."""
    config_data = {
        "model": "claude-3-opus-20240229",
        "maxTokens": 16384,
        "temperature": 0.3,
        "topP": 0.9,
        "customPersona": "You are a code reviewer.",
    }
    config_path = os.path.join(temp_config, "config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config_data, f)

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}, clear=True):
        # Temporarily change working directory to temp_config
        orig_cwd = os.getcwd()
        try:
            os.chdir(temp_config)
            config = load_config()
            assert config["model"] == "claude-3-opus-20240229"
            assert config["max_tokens"] == 16384
            assert config["temperature"] == 0.3
            assert config["top_p"] == 0.9
            assert config["custom_persona"] == "You are a code reviewer."
        finally:
            os.chdir(orig_cwd)


def test_load_config_custom_system_prompt() -> None:
    """Should load custom system prompt from config.json."""
    custom_prompt = "You are a specialized agent."
    config_data = {"systemPrompt": custom_prompt}

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "config.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}, clear=True):
            orig_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                config = load_config()
                assert config["system_prompt"] == custom_prompt
            finally:
                os.chdir(orig_cwd)


def test_load_config_corrupted_json() -> None:
    """Should handle corrupted config.json gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "config.json")
        with open(config_path, "w", encoding="utf-8") as f:
            f.write("this is not json")

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}, clear=True):
            orig_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                config = load_config()
                # Should fall back to defaults
                assert config["model"] == "deepseek-chat"
                assert config["max_tokens"] == 4096
            finally:
                os.chdir(orig_cwd)
