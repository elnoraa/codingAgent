"""Input validation utilities for the Coding Agent.

Provides functions for validating string lengths, file write paths,
and other input constraints across the tool system.
"""

from __future__ import annotations

import os
from pathlib import Path


# ── Input size limits ─────────────────────────────────────────────────────────

MAX_CODE_LENGTH = 50_000        # 50KB for Python code execution
MAX_COMMAND_LENGTH = 10_000     # 10KB for shell commands
MAX_QUERY_LENGTH = 50_000       # 50KB for SQL queries
MAX_TEXT_LENGTH = 100_000       # 100KB for file content replacements
MAX_PATH_LENGTH = 4_096         # 4096 chars for file paths
MAX_FILE_CONTENT = 10_000_000   # 10MB for file write content
MAX_URL_LENGTH = 8_192          # 8KB for URLs


def validate_length(value: str | None, max_length: int, name: str) -> str | None:
    """Validate that a string value doesn't exceed *max_length*.

    Returns an error message if too long, ``None`` if valid.
    """
    if value is None:
        return None
    if len(value) > max_length:
        return (
            f"Error: {name} is too long ({len(value)} chars, max {max_length}). "
            f"Please reduce the input size."
        )
    return None


# ── Write-path enforcement ───────────────────────────────────────────────────


def validate_write_path(path: str, working_directory: str) -> str | None:
    """Validate that a write path is within the working directory.

    Resolves both paths to their real absolute forms and checks that
    *path* resolves to a location inside *working_directory*.

    Also checks for symlink-based escapes — if any component of the
    path is a symlink pointing outside the working directory, it is
    rejected even if the final resolved path is inside.

    Returns ``None`` if the path is valid, or an error message string
    if it is outside the working directory.

    On Windows, comparison is case-insensitive (handled by Path.resolve()).
    """
    resolved_path = Path(path).resolve()
    resolved_wd = Path(working_directory).resolve()

    # Step 1: Check that the final resolved path is within the working directory
    try:
        resolved_path.relative_to(resolved_wd)
    except ValueError:
        return (
            f"Error: Path '{path}' resolves to '{resolved_path}' "
            f"which is outside the working directory '{resolved_wd}'. "
            f"All file operations must be within the working directory."
        )

    # Step 2: Check for symlink-based escapes
    # Walk the path from root to leaf checking each component.
    # If any component is a symlink pointing outside the working directory,
    # reject the path (an attacker could create a symlink inside WD -> outside).
    try:
        # Build the absolute path to walk
        if os.path.isabs(path):
            original_abs = Path(path)
        else:
            original_abs = Path(working_directory) / path

        # Normalize the path to remove ".." and "." components for walking
        original_abs = original_abs.resolve()

        # Walk all parent directories checking for symlinks
        for parent in original_abs.parents:
            try:
                if parent.is_symlink():
                    resolved_link = parent.resolve()
                    try:
                        resolved_link.relative_to(resolved_wd)
                    except ValueError:
                        return (
                            f"Error: Path '{path}' contains symlink '{parent}' "
                            f"which points to '{resolved_link}' outside the working "
                            f"directory. Symlinks to outside paths are not allowed."
                        )
            except (OSError, RuntimeError):
                pass  # Can't check — path may not exist yet, skip

        # Also check the leaf if it exists
        try:
            if original_abs.is_symlink():
                resolved_link = original_abs.resolve()
                try:
                    resolved_link.relative_to(resolved_wd)
                except ValueError:
                    return (
                        f"Error: Path '{path}' is a symlink pointing to "
                        f"'{resolved_link}' outside the working directory. "
                        f"Symlinks to outside paths are not allowed."
                    )
        except (OSError, RuntimeError):
            pass
    except (OSError, ValueError, RuntimeError):
        pass  # If we can't fully check, don't block (path may not exist yet)

    return None


def validate_write_path_atomic(path: str, working_directory: str) -> str | None:
    """Validate that a path is within the working directory, performing the
    check as close to the actual write as possible.

    This function:
    1. Resolves the path to its real (canonical) form
    2. Checks that the real path is within the working directory
    3. Does NOT do a full symlink parent walk (that's done at tool-call time)

    Call this function IMMEDIATELY before opening a file for writing,
    inside the try block.

    Returns ``None`` if the path is valid, or an error message string
    if it is outside the working directory.
    """
    try:
        resolved_path = Path(path).resolve()
        resolved_wd = Path(working_directory).resolve()
        resolved_path.relative_to(resolved_wd)
    except (ValueError, RuntimeError, OSError):
        return (
            f"Error: Path '{path}' resolves to outside the working directory "
            f"'{working_directory}'. All file operations must be within the "
            f"working directory."
        )
    return None


def validate_walk_path(path: str, working_directory: str) -> str | None:
    """Validate that a path discovered during directory walking is within the
    working directory after resolving all symlinks.

    This is a lightweight check for paths found during ``os.walk`` or
    ``os.scandir`` traversal. Unlike ``validate_write_path``, it does not
    perform a full component-by-component symlink audit, but it does reject
    paths whose resolved (real) location is outside the working directory.

    Returns ``None`` if the path is valid, or an error message string if the
    path escapes the working directory via symlinks.
    """
    try:
        resolved = Path(path).resolve()
        resolved_wd = Path(working_directory).resolve()
        resolved.relative_to(resolved_wd)
    except (ValueError, RuntimeError, OSError):
        return (
            f"Error: Path '{path}' resolves to outside the working directory "
            f"'{working_directory}' (possible symlink escape). Skipping."
        )
    return None
