"""Backup and restore functionality for the Coding Agent.

Provides two backup methods:
1. git-based: Uses git stash or git branch for fast, space-efficient backups
2. filesystem copy: Copies the entire project directory (robust, works without git)
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .logging_config import get_logger

logger = get_logger(__name__)

# Backup storage directory
BACKUP_DIR = Path(".agent-backups")


def _get_backup_dir() -> Path:
    """Get the backup directory, creating it if needed."""
    backup_dir = BACKUP_DIR.resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def _is_git_repo(working_dir: str) -> bool:
    """Check if working directory is a git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True, text=True, cwd=working_dir,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def create_backup(working_dir: str, method: str = "auto", label: str = "") -> str:
    """Create a backup of the project.

    Args:
        working_dir: Project directory to backup
        method: 'git', 'copy', or 'auto' (try git first, fall back to copy)
        label: Optional label for the backup

    Returns:
        Success or error message
    """
    from .utils import green

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"backup_{timestamp}"
    if label:
        backup_name += f"_{label.replace(' ', '_')}"

    if method == "auto":
        method = "git" if _is_git_repo(working_dir) else "copy"

    try:
        if method == "git":
            return _git_backup(working_dir, backup_name)
        else:
            return _copy_backup(working_dir, backup_name)
    except Exception as e:
        return f"Error creating backup: {e}"


def _git_backup(working_dir: str, backup_name: str) -> str:
    """Create a git branch-based backup."""
    from .utils import green

    # Check for uncommitted changes
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, cwd=working_dir, timeout=5,
    )

    if result.stdout.strip():
        # There are uncommitted changes — stash them first
        subprocess.run(
            ["git", "stash", "push", "-m", f"auto-backup {backup_name}"],
            capture_output=True, cwd=working_dir, timeout=10,
        )

    # Create a backup branch
    branch_result = subprocess.run(
        ["git", "branch", backup_name],
        capture_output=True, text=True, cwd=working_dir, timeout=10,
    )

    if branch_result.returncode != 0:
        return f"Git backup failed: {branch_result.stderr.strip()}"

    # Pop stash if we stashed
    if result.stdout.strip():
        subprocess.run(
            ["git", "stash", "pop"],
            capture_output=True, cwd=working_dir, timeout=10,
        )

    logger.info("Created git backup: %s", backup_name)
    return f"{green('✓')} Git backup created: {backup_name}"


def _copy_backup(working_dir: str, backup_name: str) -> str:
    """Create a filesystem copy backup."""
    from .utils import green

    backup_dir = _get_backup_dir() / backup_name
    source = Path(working_dir).resolve()

    # Define exclusions
    exclude_dirs = {
        ".git", "__pycache__", ".venv", "node_modules", ".mypy_cache",
        ".pytest_cache", ".agent-backups", ".claude",
    }

    def _ignore_pattern(path: str, names: list[str]) -> list[str]:
        return [n for n in names if n in exclude_dirs or n.endswith(".pyc")]

    shutil.copytree(source, backup_dir, ignore=_ignore_pattern)

    size = _get_dir_size(backup_dir)
    logger.info("Created filesystem backup: %s (%s)", backup_name, size)

    return f"{green('✓')} Filesystem backup created: {backup_name} ({size})"


def _get_dir_size(path: Path) -> str:
    """Get human-readable directory size."""
    total = sum(
        f.stat().st_size for f in path.rglob("*") if f.is_file()
    )
    for unit in ("B", "KB", "MB", "GB"):
        if total < 1024:
            return f"{total:.1f}{unit}"
        total /= 1024
    return f"{total:.1f}TB"


def list_backups() -> list[dict[str, Any]]:
    """List all available backups."""
    backups: list[dict[str, Any]] = []

    # Check filesystem backups
    backup_dir = _get_backup_dir()
    for d in backup_dir.iterdir():
        if d.is_dir() and d.name.startswith("backup_"):
            size = _get_dir_size(d)
            backups.append({
                "name": d.name,
                "type": "filesystem",
                "size": size,
                "created": datetime.fromtimestamp(d.stat().st_mtime),
            })

    # Check git backups (branches starting with backup_)
    try:
        result = subprocess.run(
            ["git", "branch", "--list", "backup_*"],
            capture_output=True, text=True, timeout=5,
        )
        for branch in result.stdout.strip().split("\n"):
            branch = branch.strip().lstrip("* ")
            if branch:
                backups.append({
                    "name": branch,
                    "type": "git",
                    "size": "-",
                    "created": None,
                })
    except Exception:
        pass

    return sorted(backups, key=lambda b: b.get("created") or datetime.min, reverse=True)


def restore_backup(name: str, working_dir: str) -> str:
    """Restore a backup by name."""
    from .utils import green, yellow

    backup_dir = _get_backup_dir() / name

    # Try filesystem restore first
    if backup_dir.exists():
        return _restore_copy(backup_dir, working_dir)

    # Try git restore
    return _restore_git(name, working_dir)


def _restore_copy(backup_dir: Path, working_dir: str) -> str:
    """Restore from a filesystem backup."""
    from .utils import green, yellow

    target = Path(working_dir).resolve()

    # Warn if target is not empty
    if any(target.iterdir()):
        confirm = input(f"  {yellow('Target directory is not empty. Continue?')} [y/N] ")
        if confirm.lower() not in ("y", "yes"):
            return "Restore cancelled."

    # Remove all contents of target
    for item in target.iterdir():
        if item.name != ".agent-backups":
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

    # Copy backup contents
    for item in backup_dir.iterdir():
        if item.is_dir():
            shutil.copytree(item, target / item.name)
        else:
            shutil.copy2(item, target / item.name)

    return f"{green('✓')} Restored from backup: {backup_dir.name}"


def _restore_git(name: str, working_dir: str) -> str:
    """Restore from a git backup branch."""
    from .utils import green

    try:
        # Checkout the backup branch (detached HEAD)
        result = subprocess.run(
            ["git", "checkout", name],
            capture_output=True, text=True, cwd=working_dir, timeout=10,
        )
        if result.returncode == 0:
            return f"{green('✓')} Restored git backup: {name} (detached HEAD — use 'git checkout main' to return)"
        return f"Error: {result.stderr.strip()}"
    except Exception as e:
        return f"Error restoring git backup: {e}"


def clean_backups(keep: int = 5) -> str:
    """Remove old backups, keeping the most recent N."""
    backups = list_backups()
    if len(backups) <= keep:
        return "No backups to clean."

    to_remove = backups[keep:]
    removed = 0

    for backup in to_remove:
        name = backup["name"]
        # Remove filesystem
        backup_dir = _get_backup_dir() / name
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
            removed += 1

        # Remove git branch
        try:
            subprocess.run(
                ["git", "branch", "-D", name],
                capture_output=True, timeout=5,
            )
        except Exception:
            pass

    return f"Cleaned {removed} old backup(s). Kept {keep} most recent."
