"""Backup commands — /backup."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.formatting import bold, dim, green

if TYPE_CHECKING:
    from src.repl.repl import Repl


def handle_backup(repl: Repl, args: str) -> None:
    """Handle /backup commands."""
    from src.backup import clean_backups, create_backup, list_backups, restore_backup

    parts = args.strip().split(maxsplit=1)
    subcmd = parts[0].lower() if parts else ""
    rest = parts[1] if len(parts) > 1 else ""

    if subcmd == "list":
        backups = list_backups()
        if not backups:
            print("  No backups found.")
            return
        print(f"\n  {bold('Available Backups')}")
        print(f"  {'─' * 50}")
        for b in backups:
            created = b["created"].strftime("%Y-%m-%d %H:%M") if b["created"] else "?"
            print(f"  {green(b['name'])}  {dim(b['type'])}  {b['size']}  {created}")

    elif subcmd == "restore":
        if not rest:
            print("  Usage: /backup restore <name>")
            return
        result = restore_backup(rest, repl.working_directory)
        print(f"  {result}")

    elif subcmd == "clean":
        count = int(rest) if rest.isdigit() else 5
        result = clean_backups(count)
        print(f"  {result}")

    else:
        # Create backup
        label = subcmd if subcmd else ""
        result = create_backup(repl.working_directory, label=label)
        print(f"  {result}")
