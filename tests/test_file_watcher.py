"""Tests for the file watcher module (polling mode only)."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

from src.file_watcher import FileWatcher


class TestFileWatcherInit:
    """Verify FileWatcher initialization."""

    def test_default_paths(self) -> None:
        fw = FileWatcher()
        assert os.getcwd() in fw.watched_paths
        assert fw.is_running is False
        assert fw._use_watchdog is False  # watchdog not installed in test env

    def test_default_poll_interval(self) -> None:
        fw = FileWatcher()
        assert fw._poll_interval == 2.0

    def test_custom_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fw = FileWatcher(paths=[tmp])
            assert tmp in fw.watched_paths
            assert len(fw.watched_paths) == 1

    def test_custom_pattern(self) -> None:
        fw = FileWatcher(pattern=".py")
        assert fw._pattern == ".py"

    def test_callback_stored(self) -> None:
        def cb(changed: list[str]) -> None:
            pass
        fw = FileWatcher(on_change=cb)
        assert fw._on_change is cb


class TestFileWatcherStartStop:
    """Verify start/stop lifecycle."""

    def test_start_sets_running(self) -> None:
        fw = FileWatcher()
        fw.start()
        assert fw.is_running is True
        fw.stop()

    def test_stop_clears_running(self) -> None:
        fw = FileWatcher()
        fw.start()
        fw.stop()
        assert fw.is_running is False

    def test_double_start_safe(self) -> None:
        fw = FileWatcher()
        fw.start()
        fw.start()  # should not crash
        assert fw.is_running is True
        fw.stop()

    def test_start_creates_thread_in_polling_mode(self) -> None:
        fw = FileWatcher()
        fw.start()
        assert fw._thread is not None
        assert fw._thread.is_alive()
        fw.stop()


class TestFileWatcherAddRemovePath:
    """Verify path management."""

    def test_add_path(self) -> None:
        fw = FileWatcher()
        fw.add_path("/tmp/test-dir")
        assert "/tmp/test-dir" in fw.watched_paths

    def test_add_path_ignores_duplicates(self) -> None:
        fw = FileWatcher()
        fw.add_path("/tmp/test-dir")
        fw.add_path("/tmp/test-dir")
        assert fw.watched_paths.count("/tmp/test-dir") == 1

    def test_remove_path_returns_true(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fw = FileWatcher(paths=[tmp])
            result = fw.remove_path(tmp)
            assert result is True
            assert tmp not in fw.watched_paths

    def test_remove_path_returns_false(self) -> None:
        fw = FileWatcher()
        result = fw.remove_path("/nonexistent")
        assert result is False

    def test_watched_paths_returns_copy(self) -> None:
        fw = FileWatcher(paths=["/tmp/a"])
        paths = fw.watched_paths
        paths.append("/tmp/b")
        assert "/tmp/b" not in fw.watched_paths  # original unchanged


class TestFileWatcherDetectChanges:
    """Verify change detection logic."""

    def test_no_changes_when_unmodified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fw = FileWatcher(paths=[tmp])
            fw._refresh_file_states()
            changes = fw._detect_changes()
            assert changes == []

    def test_new_file_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fw = FileWatcher(paths=[tmp])
            fw._refresh_file_states()
            # Create a new file
            test_file = Path(tmp) / "new_file.txt"
            test_file.write_text("hello", encoding="utf-8")
            time.sleep(0.06)  # ensure mtime changes
            changes = fw._detect_changes()
            assert str(test_file) in changes

    def test_modified_file_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            test_file = Path(tmp) / "test.txt"
            test_file.write_text("original", encoding="utf-8")
            fw = FileWatcher(paths=[tmp])
            fw._refresh_file_states()
            time.sleep(0.06)  # ensure mtime changes
            test_file.write_text("modified", encoding="utf-8")
            changes = fw._detect_changes()
            assert str(test_file) in changes

    def test_nonexistent_path_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fw = FileWatcher(paths=[tmp])
            fw._refresh_file_states()
            # Non-existent path should not cause errors
            fw.add_path("/nonexistent-path-12345")
            fw._refresh_file_states()  # should not raise


class TestFileWatcherOnFilesChanged:
    """Verify the on_files_changed callback filtering."""

    def test_pattern_filters_changes(self) -> None:
        changed: list[str] = []

        def callback(paths: list[str]) -> None:
            changed.extend(paths)

        with tempfile.TemporaryDirectory() as tmp:
            fw = FileWatcher(paths=[tmp], pattern=".py", on_change=callback)
            fw._on_files_changed([str(Path(tmp) / "test.py"), str(Path(tmp) / "readme.md")])
            assert len(changed) == 1
            assert changed[0].endswith(".py")

    def test_no_pattern_includes_all(self) -> None:
        changed: list[str] = []

        def callback(paths: list[str]) -> None:
            changed.extend(paths)

        with tempfile.TemporaryDirectory() as tmp:
            fw = FileWatcher(paths=[tmp], on_change=callback)
            fw._on_files_changed([str(Path(tmp) / "a.txt"), str(Path(tmp) / "b.py")])
            assert len(changed) == 2

    def test_no_callback_does_not_crash(self) -> None:
        fw = FileWatcher()
        # Should not raise
        fw._on_files_changed(["/tmp/test.txt"])

    def test_empty_changed_list_does_not_trigger(self) -> None:
        triggered = False

        def callback(paths: list[str]) -> None:
            nonlocal triggered
            triggered = True

        fw = FileWatcher(on_change=callback)
        fw._on_files_changed([])
        assert triggered is False
