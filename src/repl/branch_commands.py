"""Branch and fork commands — /branch, /fork."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.formatting import bold, dim, green, red, cyan

if TYPE_CHECKING:
    from src.repl.repl import Repl


def handle_fork(repl: "Repl", args: str) -> None:
    """Fork the conversation at the current point."""
    from src.branch_manager import BranchManager

    parts = args.strip().split(maxsplit=1)
    name = parts[0].lower() if parts else ""
    description = parts[1] if len(parts) > 1 else ""

    if not name:
        print("  Usage: /fork <name> [description]")
        return

    if name == "main":
        print("  Cannot fork 'main' branch.")
        return

    if not hasattr(repl, '_branch_manager') or repl._branch_manager is None:
        repl._branch_manager = BranchManager(repl.messages)

    if repl._branch_manager.fork(name, description):
        print(f"  {green('✓')} Forked branch: '{name}' (from '{repl._branch_manager.active_branch}')")
    else:
        print(f"  {red('✗')} Branch '{name}' already exists.")


def handle_branch(repl: "Repl", args: str) -> None:
    """Switch to or manage branches."""
    from src.branch_manager import BranchManager

    if not hasattr(repl, '_branch_manager') or repl._branch_manager is None:
        repl._branch_manager = BranchManager(repl.messages)

    parts = args.strip().split(maxsplit=1)
    subcmd = parts[0].lower() if parts else ""
    rest = parts[1] if len(parts) > 1 else ""

    if subcmd in ("list", "ls"):
        branches = repl._branch_manager.list_branches()
        if not branches:
            print("  No branches.")
            return

        print(f"\n  {bold('Branches')}")
        print(f"  {'─' * 60}")
        for b in branches:
            active_marker = green("●") if b["active"] else dim("○")
            print(f"  {active_marker} {b['name']:<20} {b['age']:<12} {b['messages']} msgs  {dim(b['description'])}")

    elif subcmd == "switch" and rest:
        if repl._branch_manager.switch(rest):
            repl.messages = repl._branch_manager.active_messages
            print(f"  Switched to branch: {green(rest)} ({len(repl.messages)} messages)")
        else:
            print(f"  {red('✗')} Branch '{rest}' not found.")

    elif subcmd == "delete" and rest:
        if repl._branch_manager.delete(rest):
            print(f"  Deleted branch: {rest}")
        else:
            print(f"  {red('✗')} Cannot delete '{rest}'. Use /branch list to see available branches.")

    elif subcmd and subcmd not in ("list", "ls", "switch", "delete"):
        if repl._branch_manager.switch(subcmd):
            repl.messages = repl._branch_manager.active_messages
            print(f"  Switched to branch: {green(subcmd)} ({len(repl.messages)} messages)")
        else:
            print(f"  {red('✗')} Branch '{subcmd}' not found.")

    else:
        print(f"  Active branch: {green(repl._branch_manager.active_branch)}")
        print(f"  Use: /branch list, /branch switch <name>, /branch delete <name>")


def handle_branches(repl: "Repl", args: str) -> None:
    """Alias for /branches list."""
    handle_branch(repl, "list")
