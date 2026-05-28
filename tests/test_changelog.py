"""Tests for the change log / audit trail module."""

from __future__ import annotations

from src.changelog import ChangeEntry, format_changelog


def test_change_entry_creation() -> None:
    """ChangeEntry should store all fields correctly."""
    entry = ChangeEntry(
        timestamp="2025-05-28T12:00:00",
        tool="write_file",
        path="src/main.py",
        summary="Created main.py",
        args={"content": "test"},
    )
    assert entry.timestamp == "2025-05-28T12:00:00"
    assert entry.tool == "write_file"
    assert entry.path == "src/main.py"
    assert entry.summary == "Created main.py"
    assert entry.args == {"content": "test"}


def test_change_entry_defaults() -> None:
    """Summary and args should default to empty."""
    entry = ChangeEntry(timestamp="now", tool="edit_file", path="file.py")
    assert entry.summary == ""
    assert entry.args == {}


def test_format_changelog_empty() -> None:
    """Empty changelog should return 'No changes recorded yet.'"""
    result = format_changelog([])
    assert "No changes recorded yet." in result


def test_format_changelog_single_entry() -> None:
    """Single entry should include timestamp, tool, and path."""
    entries = [
        ChangeEntry(timestamp="2025-05-28T12:00:00", tool="write_file", path="src/main.py"),
    ]
    result = format_changelog(entries)
    assert "2025-05-28T12:00:00" in result
    assert "write_file" in result
    assert "src/main.py" in result


def test_format_changelog_multiple_entries() -> None:
    """Multiple entries should all appear."""
    entries = [
        ChangeEntry(timestamp="2025-05-28T12:00:00", tool="write_file", path="a.py"),
        ChangeEntry(timestamp="2025-05-28T12:01:00", tool="edit_file", path="b.py"),
    ]
    result = format_changelog(entries)
    assert "a.py" in result
    assert "b.py" in result
    assert "write_file" in result
    assert "edit_file" in result


def test_format_changelog_with_summary() -> None:
    """Summary text should appear in the output."""
    entries = [
        ChangeEntry(
            timestamp="2025-05-28T12:00:00",
            tool="write_file",
            path="src/main.py",
            summary="Created the main entry point",
        ),
    ]
    result = format_changelog(entries)
    assert "Created the main entry point" in result


def test_format_changelog_max_entries() -> None:
    """Only the last max_entries should be shown."""
    entries = [ChangeEntry(timestamp=f"t{i}", tool="tool", path=f"f{i}.py") for i in range(10)]
    result = format_changelog(entries, max_entries=3)
    # Should only contain 3 file references
    assert result.count("f") == 3  # f0.py, f1.py, f2.py won't appear
    assert "f7.py" in result or "f8.py" in result or "f9.py" in result


def test_format_changelog_timestamp_truncation() -> None:
    """Long ISO timestamps should be truncated to 19 chars."""
    long_ts = "2025-05-28T12:00:00.123456"
    entries = [ChangeEntry(timestamp=long_ts, tool="write_file", path="x.py")]
    result = format_changelog(entries)
    # Should contain truncated version
    assert "2025-05-28T12:00:00" in result
    # Should NOT contain the full microsecond precision
    assert "123456" not in result
