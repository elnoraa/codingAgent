"""File watch commands — /watch, /unwatch, /watchers."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from src.formatting import bold, dim, green, yellow

if TYPE_CHECKING:
    from src.repl.repl import Repl


def init_file_watcher(repl: "Repl") -> None:
    """Initialize file watcher attribute (lazy)."""
    repl._file_watcher = None


def on_file_change(repl: "Repl", changed_paths: list[str]) -> None:
    """Callback when watched files change externally."""
    for path in changed_paths:
        print(f"\n  {yellow('⟳')} File changed externally: {path}")
    print(f"  {dim('Type /status to see current state, or continue working.')}")


def handle_watch(repl: "Repl", args: str) -> None:
    """Handle /watch command."""
    from src.file_watcher import FileWatcher

    parts = args.strip().split()
    if not parts:
        # Toggle current watcher
        if repl._file_watcher and repl._file_watcher.is_running:
            repl._file_watcher.stop()
            print("  File watcher stopped.")
        else:
            repl._file_watcher = FileWatcher(
                paths=[repl.working_directory],
                on_change=lambda paths: on_file_change(repl, paths),
            )
            repl._file_watcher.start()
            print(f"  File watcher started (watching: {repl.working_directory})")
        return

    subcmd = parts[0].lower()

    if subcmd == "add" and len(parts) > 1:
        path = os.path.join(repl.working_directory, parts[1])
        if repl._file_watcher:
            repl._file_watcher.add_path(path)
            print(f"  Added watch path: {path}")

    elif subcmd == "remove" and len(parts) > 1:
        path = os.path.join(repl.working_directory, parts[1])
        if repl._file_watcher:
            repl._file_watcher.remove_path(path)
            print(f"  Removed watch path: {path}")

    elif subcmd == "pattern" and len(parts) > 1:
        if repl._file_watcher:
            repl._file_watcher.stop()
            print(f"  Set watch pattern: {parts[1]}")


def handle_unwatch(repl: "Repl", args: str) -> None:
    """Handle /unwatch command."""
    if repl._file_watcher:
        repl._file_watcher.stop()
        repl._file_watcher = None
        print("  File watcher stopped.")
    else:
        print("  No file watcher running.")


def handle_watchers(repl: "Repl", args: str) -> None:
    """Handle /watchers command — show watcher status."""
    if repl._file_watcher and repl._file_watcher.is_running:
        print(f"\n  {bold('File Watcher')}")
        print(f"  Status: {green('Running')}")
        print(f"  Watching:")
        for p in repl._file_watcher.watched_paths:
            print(f"    {p}")
        print(f"  Method: {'watchdog' if repl._file_watcher._use_watchdog else 'polling'}")
    else:
        print("  No file watcher running.")
