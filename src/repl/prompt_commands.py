"""Prompt template commands — /prompt."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.formatting import bold, cyan, dim, green, red, yellow

if TYPE_CHECKING:
    from src.repl.repl import Repl


def _get_last_assistant_text(repl: Repl) -> str:
    """Get the last assistant text response from messages."""
    from typing import cast

    for msg in reversed(repl.messages):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                texts: list[str] = []
                blocks = cast("list[dict[str, object]]", content)
                for block in blocks:
                    if block.get("type") == "text":
                        t = block.get("text", "")
                        if isinstance(t, str):
                            texts.append(t)
                return "\n".join(texts)
    return ""


def handle_prompt(repl: Repl, cmd: str) -> None:
    """Handle /prompt command — save, load, list prompt templates."""
    from src.prompts import list_prompts, load_prompt, save_prompt

    parts = cmd.strip().split(maxsplit=2)
    subcommand = parts[1].lower() if len(parts) > 1 else "list"

    if subcommand == "save":
        if len(parts) < 3:
            print(f"  {dim('Usage: /prompt save <name>')}")
            print(f"  {dim('Saves the last assistant response as a prompt template.')}")
            return
        name = parts[2].strip()
        text = _get_last_assistant_text(repl)
        if not text:
            print(f"  {dim('No assistant response to save. Send a message first.')}")
            return
        try:
            filepath = save_prompt(name, text, repl.working_directory)
            print(f"  {green('✓')} {dim('Prompt saved to')} {cyan(filepath)}")
        except Exception as exc:
            print(f"  {red('✗ Error saving prompt:')} {exc}")

    elif subcommand == "load":
        if len(parts) < 3:
            print(f"  {dim('Usage: /prompt load <name>')}")
            return
        name = parts[2].strip()
        prompt = load_prompt(name, repl.working_directory)
        if prompt is None:
            print(f"  {dim('Prompt not found:')} {cyan(name)}")
            print(f"  {dim('Use /prompt list to see available prompts.')}")
            return
        tag = f"{green('built-in')}" if prompt.is_builtin else f"{yellow('custom')}"
        print(f"  {bold(prompt.name)} {tag}")
        print(f"  {dim('─' * 40)}")
        for line in prompt.content.strip().split("\n"):
            print(f"  {line}")
        print()
        try:
            confirm = input(f"  {bold('Send this prompt as your message?')} {dim('[Y/n]')} ").strip().lower()
        except EOFError, KeyboardInterrupt:
            confirm = "n"
        if confirm in ("", "y", "yes"):
            repl._turn_number += 1
            from src.repl.repl import turn_separator_color

            color_fn = turn_separator_color(repl)
            repl._process_turn(prompt.content, color_fn)

    elif subcommand == "list":
        prompts = list_prompts(repl.working_directory)
        if not prompts:
            print(f"  {dim('No prompts available.')}")
            return
        print(f"  {bold('Prompt Templates')}")
        print()
        for p in prompts:
            tag = f"{green('built-in')}" if p.is_builtin else f"{yellow('custom')}"
            name_str = cyan(p.name.ljust(20))
            preview = p.content[:60].replace("\n", " ") + "..."
            print(f"  {name_str} {tag} {dim(preview)}")

    else:
        print(f"  {dim('Unknown prompt command. Usage:')}")
        print(f"  {dim('  /prompt list              — list all prompts')}")
        print(f"  {dim('  /prompt load <name>       — load a prompt template')}")
        print(f"  {dim('  /prompt save <name>       — save last response as prompt')}")
