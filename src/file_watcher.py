"""File watcher for detecting external file changes.

Uses watchdog (optional) for efficient monitoring, with polling fallback.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .logging_config import get_logger

logger = get_logger(__name__)

# Default poll interval (seconds) — used when watchdog is not available
DEFAULT_POLL_INTERVAL = 2.0


class FileWatcher:
    """Monitor files/directories for changes and notify via callback."""

    def __init__(
        self,
        paths: list[str] | None = None,
        *,
        recursive: bool = True,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        on_change: Callable[[list[str]], None] | None = None,
        pattern: str | None = None,
    ):
        self._paths = paths or [os.getcwd()]
        self._recursive = recursive
        self._poll_interval = poll_interval
        self._on_change = on_change
        self._pattern = pattern
        self._running = False
        self._thread: threading.Thread | None = None
        self._file_states: dict[str, float] = {}  # path -> last mtime
        self._use_watchdog = False

        # Try to use watchdog for efficiency
        self._watchdog_observer: Any = None
        self._init_watchdog()

    def _init_watchdog(self) -> None:
        """Try to initialize watchdog-based monitoring."""
        try:
            from watchdog.events import FileSystemEventHandler  # type: ignore[import-untyped]
            from watchdog.observers import Observer  # type: ignore[import-untyped]

            class _Handler(FileSystemEventHandler):
                def __init__(self, callback: Callable[[list[str]], None]):
                    self.callback = callback

                def on_modified(self, event: Any) -> None:
                    if not event.is_directory:
                        self.callback([event.src_path])

                def on_created(self, event: Any) -> None:
                    if not event.is_directory:
                        self.callback([event.src_path])

            self._watchdog_observer = Observer()
            self._watchdog_handler = _Handler(self._on_files_changed)
            self._use_watchdog = True
            logger.info("FileWatcher: using watchdog (efficient)")
        except ImportError:
            logger.info("FileWatcher: watchdog not available, using polling")

    def _on_files_changed(self, changed_paths: list[str]) -> None:
        """Called when files change."""
        if self._on_change:
            # Filter by pattern if set
            if self._pattern:
                changed_paths = [p for p in changed_paths if self._pattern in p]
            if changed_paths:
                self._on_change(changed_paths)

    def start(self) -> None:
        """Start monitoring."""
        if self._running:
            return

        self._running = True

        if self._use_watchdog:
            self._start_watchdog()
        else:
            # Build initial file state for polling
            self._refresh_file_states()
            self._thread = threading.Thread(target=self._poll_loop, daemon=True)
            self._thread.start()

        logger.info("FileWatcher started (paths=%s)", self._paths)

    def _start_watchdog(self) -> None:
        """Start watchdog-based monitoring."""
        if self._watchdog_observer:
            for watch_path in self._paths:
                self._watchdog_observer.schedule(
                    self._watchdog_handler,
                    watch_path,
                    recursive=self._recursive,
                )
            self._watchdog_observer.start()

    def _refresh_file_states(self) -> None:
        """Scan watched paths and record file mtimes."""
        self._file_states.clear()
        for watch_path in self._paths:
            root = Path(watch_path)
            if not root.exists():
                continue

            if root.is_file():
                self._file_states[str(root)] = root.stat().st_mtime
            elif self._recursive:
                for f in root.rglob("*"):
                    if f.is_file():
                        self._file_states[str(f)] = f.stat().st_mtime

    def _poll_loop(self) -> None:
        """Polling loop for when watchdog is unavailable."""
        while self._running:
            time.sleep(self._poll_interval)
            try:
                changed = self._detect_changes()
                if changed:
                    self._on_files_changed(changed)
            except Exception as e:
                logger.debug("Poll error: %s", e)

    def _detect_changes(self) -> list[str]:
        """Detect file changes by comparing mtimes."""
        changed: list[str] = []
        current_states: dict[str, float] = {}

        for watch_path in self._paths:
            root = Path(watch_path)
            if not root.exists():
                continue

            if root.is_file():
                mtime = root.stat().st_mtime
                current_states[str(root)] = mtime
                if str(root) in self._file_states:
                    if mtime != self._file_states[str(root)]:
                        changed.append(str(root))
                else:
                    changed.append(str(root))  # New file
            elif self._recursive:
                for f in root.rglob("*"):
                    if f.is_file():
                        mtime = f.stat().st_mtime
                        current_states[str(f)] = mtime
                        if str(f) in self._file_states:
                            if mtime != self._file_states[str(f)]:
                                changed.append(str(f))
                        else:
                            changed.append(str(f))

        self._file_states = current_states
        return changed

    def stop(self) -> None:
        """Stop monitoring."""
        self._running = False
        if self._watchdog_observer:
            self._watchdog_observer.stop()
            self._watchdog_observer.join(timeout=2)
        if self._thread:
            self._thread.join(timeout=2)
        logger.info("FileWatcher stopped")

    def add_path(self, path: str) -> None:
        """Add a path to monitor."""
        if path not in self._paths:
            self._paths.append(path)
            if self._use_watchdog and self._watchdog_observer:
                self._watchdog_observer.schedule(
                    self._watchdog_handler,
                    path,
                    recursive=self._recursive,
                )

    def remove_path(self, path: str) -> bool:
        """Remove a path from monitoring. Returns True if removed."""
        if path in self._paths:
            self._paths.remove(path)
            return True
        return False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def watched_paths(self) -> list[str]:
        return list(self._paths)
