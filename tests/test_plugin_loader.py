"""Tests for plugin allowlist HMAC signing."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

import pytest

from src.plugin_loader import (
    _sign_allowlist,
    _verify_allowlist,
    _get_signing_key,
    PluginLoader,
)


class TestAllowlistSigning:
    """Verify HMAC signing of plugin allowlist."""

    def test_sign_and_verify(self) -> None:
        """A signed allowlist should verify successfully."""
        allowlist = {"my-plugin": "abc123", "other-plugin": "def456"}
        key = b"test-key-12345"
        signature = _sign_allowlist(allowlist, key)
        assert _verify_allowlist(allowlist, signature, key) is True

    def test_verify_with_wrong_key(self) -> None:
        """Verifying with a different key should fail."""
        allowlist = {"my-plugin": "abc123"}
        signature = _sign_allowlist(allowlist, b"correct-key")
        assert _verify_allowlist(allowlist, signature, b"wrong-key") is False

    def test_verify_tampered_data(self) -> None:
        """If the allowlist data is modified after signing, verification fails."""
        allowlist = {"my-plugin": "abc123"}
        key = b"test-key"
        signature = _sign_allowlist(allowlist, key)

        tampered = dict(allowlist)
        tampered["my-plugin"] = "xyz999"

        assert _verify_allowlist(tampered, signature, key) is False

    def test_sign_deterministic(self) -> None:
        """Same data and same key should produce the same signature."""
        allowlist = {"a": "1", "b": "2"}
        key = b"key"
        sig1 = _sign_allowlist(allowlist, key)
        sig2 = _sign_allowlist(allowlist, key)
        assert sig1 == sig2

    def test_sign_order_independent(self) -> None:
        """Signature should be order-independent (keys sorted)."""
        allowlist1 = {"a": "1", "b": "2"}
        allowlist2 = {"b": "2", "a": "1"}
        key = b"key"
        assert _sign_allowlist(allowlist1, key) == _sign_allowlist(allowlist2, key)

    def test_get_signing_key_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Signing key should be read from environment."""
        monkeypatch.setenv("CODING_AGENT_PLUGIN_KEY", "my-secret-key")
        key = _get_signing_key()
        assert key is not None
        assert key == b"my-secret-key"

    def test_get_signing_key_not_set(self) -> None:
        """If env var is not set, get_signing_key should return None."""
        if "CODING_AGENT_PLUGIN_KEY" in os.environ:
            del os.environ["CODING_AGENT_PLUGIN_KEY"]
        assert _get_signing_key() is None


class TestPluginAllowlistWithSignature:
    """Integration tests for signed allowlist behavior."""

    def test_unsigned_allowlist_still_works_without_key(self, tmp_path: Path) -> None:
        """Without a signing key, legacy unsigned allowlists should load."""
        loader = PluginLoader(plugins_dir=tmp_path)

        allowlist_path = tmp_path / ".plugin-allowlist.json"
        allowlist_path.write_text(json.dumps({"my-plugin": "hash123"}), encoding="utf-8")

        result = loader._get_allowlist()
        assert result == {"my-plugin": "hash123"}

    def test_signed_allowlist_loads_with_correct_key(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Signed allowlist with correct key should load."""
        monkeypatch.setenv("CODING_AGENT_PLUGIN_KEY", "secret")
        from src.plugin_loader import _sign_allowlist

        loader = PluginLoader(plugins_dir=tmp_path)

        allowlist_data = {"my-plugin": "hash123"}
        signature = _sign_allowlist(allowlist_data, b"secret")

        allowlist_path = tmp_path / ".plugin-allowlist.json"
        allowlist_path.write_text(
            json.dumps({"allowed": allowlist_data, "signature": signature}),
            encoding="utf-8",
        )

        result = loader._get_allowlist()
        assert result == {"my-plugin": "hash123"}

    def test_tampered_allowlist_returns_empty_with_key(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tampered allowlist with signing key configured should return empty."""
        monkeypatch.setenv("CODING_AGENT_PLUGIN_KEY", "secret")
        from src.plugin_loader import _sign_allowlist

        loader = PluginLoader(plugins_dir=tmp_path)

        allowlist_data = {"my-plugin": "hash123"}
        signature = _sign_allowlist(allowlist_data, b"secret")

        allowlist_path = tmp_path / ".plugin-allowlist.json"
        # Tamper the data but keep the old signature
        allowlist_path.write_text(
            json.dumps({"allowed": {"my-plugin": "tampered-hash"}, "signature": signature}),
            encoding="utf-8",
        )

        result = loader._get_allowlist()
        assert result == {}

    def test_update_allowlist_includes_signature(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """When signing key is set, _update_allowlist should include a signature."""
        monkeypatch.setenv("CODING_AGENT_PLUGIN_KEY", "secret-key")

        loader = PluginLoader(plugins_dir=tmp_path)
        loader._update_allowlist("test-plugin", "abcdef123")

        allowlist_path = tmp_path / ".plugin-allowlist.json"
        data = json.loads(allowlist_path.read_text(encoding="utf-8"))

        assert "signature" in data
        assert data["allowed"] == {"test-plugin": "abcdef123"}

    def test_update_allowlist_without_key_no_signature(self, tmp_path: Path) -> None:
        """Without a signing key, _update_allowlist should not add a signature."""
        if "CODING_AGENT_PLUGIN_KEY" in os.environ:
            del os.environ["CODING_AGENT_PLUGIN_KEY"]

        loader = PluginLoader(plugins_dir=tmp_path)
        loader._update_allowlist("test-plugin", "abcdef123")

        allowlist_path = tmp_path / ".plugin-allowlist.json"
        data = json.loads(allowlist_path.read_text(encoding="utf-8"))

        assert "signature" not in data
        assert data["allowed"] == {"test-plugin": "abcdef123"}


# ── Plugin injection prevention tests ──────────────────────────────


class TestPluginInjectionPrevention:
    """Verify that plugin loading detects session-modified files."""

    def test_detect_session_modified_plugin(self) -> None:
        """A plugin file modified during the session should be detected."""
        from tools import record_session_start, was_file_modified_during_session

        with tempfile.TemporaryDirectory() as tmpdir:
            record_session_start()

            # Create a plugin file
            plugin_file = Path(tmpdir) / "plugin.py"
            plugin_file.write_text("__version__ = '1.0.0'\n__author__ = 'test'\n")

            # Record timestamp as if it was there at session start
            from tools import record_file_timestamp
            record_file_timestamp(str(plugin_file))

            # "Modify" it during the session
            time.sleep(0.2)  # Ensure different mtime
            plugin_file.write_text("__version__ = '2.0.0'\nimport os\nos.system('rm -rf /')\n")

            # Check detection
            assert was_file_modified_during_session(str(plugin_file)) is True

    def test_unmodified_plugin_not_detected(self) -> None:
        """A plugin file NOT modified during the session should not trigger."""
        from tools import record_session_start, was_file_modified_during_session

        with tempfile.TemporaryDirectory() as tmpdir:
            record_session_start()

            # Create a plugin file BEFORE session start (simulate)
            plugin_file = Path(tmpdir) / "plugin.py"
            plugin_file.write_text("__version__ = '1.0.0'\n")

            from tools import record_file_timestamp
            record_file_timestamp(str(plugin_file))

            # Don't modify it — check should be clean
            assert was_file_modified_during_session(str(plugin_file)) is False

    def test_nonexistent_file_not_detected(self) -> None:
        """A file that doesn't exist should not be flagged as modified."""
        from tools import record_session_start, was_file_modified_during_session

        with tempfile.TemporaryDirectory() as tmpdir:
            record_session_start()
            nonexistent = os.path.join(tmpdir, "nonexistent.json")
            assert was_file_modified_during_session(nonexistent) is False

    def test_new_file_after_session_start_detected(self) -> None:
        """A file created after session start should be detected."""
        from tools import record_session_start, was_file_modified_during_session

        with tempfile.TemporaryDirectory() as tmpdir:
            record_session_start()

            time.sleep(0.2)
            # Create a file AFTER session start
            new_file = Path(tmpdir) / "new_file.json"
            new_file.write_text("{}")

            assert was_file_modified_during_session(str(new_file)) is True
