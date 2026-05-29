"""Scaffold commands — /scaffold."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.formatting import bold, dim, green

if TYPE_CHECKING:
    from src.repl.repl import Repl


def handle_scaffold(repl: "Repl", args: str) -> None:
    """Handle /scaffold commands."""
    from src.scaffold import list_templates, scaffold_project, show_template

    parts = args.strip().split(maxsplit=2)
    subcmd = parts[0].lower() if parts else ""

    if subcmd == "list":
        templates = list_templates()
        if not templates:
            print("  No templates available.")
            return
        print(f"\n  {bold('Available Templates')}")
        for t in templates:
            builtin = dim("(built-in)") if t.get("builtin") else dim("(custom)")
            desc = f" — {t['description']}" if t.get("description") else ""
            print(f"  {green(t['name'])} {builtin}{desc}")

    elif subcmd == "show":
        if len(parts) < 2:
            print("  Usage: /scaffold show <template>")
            return
        result = show_template(parts[1])
        print(f"\n{result}")

    else:
        if len(parts) < 2:
            print("  Usage: /scaffold <template> <name>")
            print("         /scaffold list")
            print("         /scaffold show <template>")
            return
        template_name = parts[0]
        project_name = parts[1] if len(parts) > 1 else template_name
        result = scaffold_project(template_name, project_name)
        print(f"  {result}")
