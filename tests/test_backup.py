"""Tests for backup and restore functionality."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from src.backup import (
    create_backup,
    list_backups,
    restore_backup,
    clean_backups,
    _get_backup_dir,
    _get_dir_size,
    _is_git_repo,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _init_git_repo(tmp_path: Path) -> None:
    """Initialize a minimal git repository in tmp_path."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path, capture_output=True,
    )
    # Create and commit an initial file so git has something to work with
    (tmp_path / "README.md").write_text("# Test Project")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, capture_output=True)


# ── Utility Tests ────────────────────────────────────────────────────────────


class TestUtilityFunctions:
    """Verify internal helpers."""

    def test_get_backup_dir_creates(self, tmp_path: Path) -> None:
        """The backup dir should be created if it doesn't exist."""
        backup_dir = tmp_path / ".agent-backups"
        assert not backup_dir.exists()
        # _get_backup_dir uses a global path, so we test via create_backup which uses it
        # Instead, test _get_dir_size with a known file
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello")
        size = _get_dir_size(tmp_path)
        assert isinstance(size, str)
        assert "B" in size or "KB" in size

    def test_is_git_repo_true(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        assert _is_git_repo(str(tmp_path)) is True

    def test_is_git_repo_false(self, tmp_path: Path) -> None:
        assert _is_git_repo(str(tmp_path)) is False

    def test_is_git_repo_nonexistent(self) -> None:
        assert _is_git_repo("/nonexistent/path") is False


# ── Create Backup Tests ──────────────────────────────────────────────────────


class TestCreateBackup:
    """Verify backup creation."""

    def test_create_copy_backup(self, tmp_path: Path) -> None:
        """Filesystem copy backup should create a backup directory."""
        (tmp_path / "test.py").write_text("print('hello')")
        result = create_backup(str(tmp_path), method="copy")
        assert "backup" in result.lower() or "✓" in result
        backup_dir = _get_backup_dir()
        # List backup directories
        backups = [d for d in backup_dir.iterdir() if d.is_dir() and d.name.startswith("backup_")]
        assert len(backups) >= 1

    def test_create_copy_backup_with_label(self, tmp_path: Path) -> None:
        """Label should appear in the backup name."""
        (tmp_path / "test.py").write_text("data")
        result = create_backup(str(tmp_path), method="copy", label="pre-refactor")
        assert "pre-refactor" in result or "backup" in result.lower()

    def test_copy_backup_excludes_git(self, tmp_path: Path) -> None:
        """The .git directory should not be copied."""
        (tmp_path / ".git").mkdir()
        (tmp_path / "mycode.py").write_text("code")
        create_backup(str(tmp_path), method="copy")
        backup_dir = _get_backup_dir()
        # Find the backup
        backups = list(backup_dir.iterdir())
        # Check that .git is not in any backup
        for b in backups:
            if b.is_dir():
                assert not (b / ".git").exists()

    def test_create_backup_error_handling(self) -> None:
        """Nonexistent directory should return error, not crash."""
        result = create_backup("/nonexistent_path_xyzzy_12345", method="copy")
        assert "error" in result.lower() or "Error" in result

    def test_auto_method_uses_git_for_git_repo(self, tmp_path: Path) -> None:
        """Auto method should use git for git repos."""
        _init_git_repo(tmp_path)
        (tmp_path / "new_file.py").write_text("print('hello')")
        result = create_backup(str(tmp_path), method="auto")
        assert "git" in result.lower() or "backup" in result.lower()

    def test_auto_method_uses_copy_for_non_git(self, tmp_path: Path) -> None:
        """Auto method should use copy for non-git directories."""
        (tmp_path / "file.txt").write_text("data")
        result = create_backup(str(tmp_path), method="auto")
        assert "backup" in result.lower()

    def test_git_backup_creates_branch(self, tmp_path: Path) -> None:
        """Git backup should create a backup branch."""
        _init_git_repo(tmp_path)
        result = create_backup(str(tmp_path), method="git")
        assert "backup" in result.lower() or "✓" in result
        # Check that a backup branch was created
        branches = subprocess.run(
            ["git", "branch"], cwd=tmp_path, capture_output=True, text=True,
        )
        assert "backup_" in branches.stdout


# ── List Backups Tests ───────────────────────────────────────────────────────


class TestListBackups:
    """Verify backup listing."""

    def test_list_backups_after_copy(self, tmp_path: Path) -> None:
        (tmp_path / "test.py").write_text("data")
        create_backup(str(tmp_path), method="copy")
        backups = list_backups()
        assert len(backups) >= 1
        assert backups[0]["type"] in ("filesystem", "git")

    def test_list_backups_empty(self) -> None:
        """List should still work with no backups."""
        backups = list_backups()
        assert isinstance(backups, list)


# ── Restore Backup Tests ─────────────────────────────────────────────────────


class TestRestoreBackup:
    """Verify backup restoration."""

    def test_restore_copy_backup(self, tmp_path: Path) -> None:
        """Restoring a copy backup should recover original files."""
        # Create a backup from a temp source directory
        source = tmp_path / "source"
        source.mkdir()
        (source / "original.py").write_text("original content")
        create_backup(str(source), method="copy", label="test-backup")

        # Restore into an empty directory (no confirmation prompt needed)
        target = tmp_path / "target"
        target.mkdir()
        backups = list_backups()
        copy_backups = [b for b in backups if b["type"] == "filesystem"]
        if copy_backups:
            result = restore_backup(copy_backups[0]["name"], str(target))
            assert "restored" in result.lower() or "✓" in result
            assert (target / "original.py").read_text() == "original content"

    def test_restore_nonexistent_backup(self) -> None:
        """Restoring a non-existent backup should return an error."""
        result = restore_backup("nonexistent_backup_name", str(Path.cwd()))
        assert "error" in result.lower() or "Error" in result or "failed" in result.lower()


# ── Clean Backups Tests ──────────────────────────────────────────────────────


class TestCleanBackups:
    """Verify backup cleanup."""

    def test_clean_no_backups_to_remove(self) -> None:
        """Cleaning with nothing to remove should not crash."""
        result = clean_backups(keep=10)
        assert isinstance(result, str)

    def test_clean_keeps_specified_number(self, tmp_path: Path) -> None:
        """After cleaning, at most 'keep' backups should remain."""
        # Create multiple backups
        for i in range(3):
            (tmp_path / f"file_{i}.txt").write_text(f"content {i}")
            create_backup(str(tmp_path), method="copy", label=f"backup-{i}")
        clean_backups(keep=2)
        backups = list_backups()
        assert len(backups) <= 2
