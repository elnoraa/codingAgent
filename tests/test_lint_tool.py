"""Tests for the lint integration module."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from tools.lint_tool import detect_linter, run_linter, _lint_post_edit_hook


class TestDetectLinter:
    """Verify linter detection."""

    def test_no_linter_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = detect_linter(tmp)
            assert result is None

    def test_detects_ruff_via_ruff_toml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "ruff.toml").write_text("", encoding="utf-8")
            result = detect_linter(tmp)
            assert result == "ruff"

    def test_detects_ruff_via_pyproject(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "pyproject.toml").write_text(
                '[tool.ruff]\nline-length = 100\n', encoding="utf-8"
            )
            result = detect_linter(tmp)
            assert result == "ruff"

    def test_pyproject_without_ruff_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "pyproject.toml").write_text(
                '[tool.black]\nline-length = 100\n', encoding="utf-8"
            )
            result = detect_linter(tmp)
            assert result is None

    def test_detects_flake8(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".flake8").write_text("", encoding="utf-8")
            result = detect_linter(tmp)
            assert result == "flake8"

    def test_detects_eslint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".eslintrc.json").write_text("{}", encoding="utf-8")
            result = detect_linter(tmp)
            assert result == "eslint"


class TestRunLinter:
    """Verify linter execution."""

    def test_no_linter_returns_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = run_linter(["test.py"], tmp)
            assert "No linter detected" in result

    def test_linter_not_installed(self) -> None:
        """When linter is detected but not installed, return a helpful message."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "ruff.toml").write_text("", encoding="utf-8")
            with patch("subprocess.run", side_effect=FileNotFoundError):
                result = run_linter(["test.py"], tmp)
                assert "not installed" in result
                assert "ruff" in result


class TestLintPostEditHook:
    """Verify the post-edit hook."""

    def test_skips_non_code_files(self) -> None:
        result = _lint_post_edit_hook("readme.md", "File saved")
        assert result == "File saved"

    def test_processes_py_files(self) -> None:
        result = _lint_post_edit_hook("test.py", "File saved")
        assert "File saved" in result
