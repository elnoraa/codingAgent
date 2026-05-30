"""Plan management commands — /plan save, create, list."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.formatting import bold, cyan, dim, green, red, yellow
from src.repl.help_text import plan_name_from_text

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


def handle_plan_save(repl: Repl, cmd: str) -> None:
    """Handle /plan save <name>."""
    from src.plan import save_pending_plan

    parts = cmd.split(maxsplit=2)
    if len(parts) < 3:
        print(f"  {dim('Usage: /plan save <name>')}")
        return

    name = parts[2].strip()
    if not name:
        print(f"  {dim('Usage: /plan save <name>')}")
        return

    text = _get_last_assistant_text(repl)
    if not text:
        print(f"  {dim('No assistant response to save. Send a message first.')}")
        return

    try:
        filepath = save_pending_plan(name, text, repl.working_directory)
        print(f"  {green('✓')} {dim('Plan saved to')} {cyan(filepath)}")
    except Exception as exc:
        print(f"  {red('✗ Error saving plan:')} {exc}")


def handle_plan_create(repl: Repl, parts: list[str]) -> None:
    """Handle /plan create <topic> — generate a structured plan template."""
    from src.plan import generate_plan_template, save_pending_plan

    topic_parts = parts[1:] if len(parts) > 1 else []
    if not topic_parts:
        print(f"  {dim('Usage: /plan create <topic description>')}")
        print(f"  {dim('Example: /plan create Add user authentication')}")
        return

    topic = " ".join(topic_parts)
    template = generate_plan_template(topic)

    # Save the template as a pending plan
    safe_name = plan_name_from_text(topic)
    try:
        filepath = save_pending_plan(safe_name, template, repl.working_directory)
        print(f"  {green('✓')} {bold('Plan template created:')} {cyan(filepath)}")
        print(f"  {dim('You can now edit it or ask the agent to follow this plan.')}")
    except Exception as exc:
        print(f"  {red('✗ Error creating plan:')} {exc}")


def handle_plan_list(repl: Repl, subcommand: str = "") -> None:
    """Handle /plan list and /plan list completed."""
    from src.plan import list_completed_plans, list_pending_plans

    show_completed = subcommand == "completed"
    if show_completed:
        plans = list_completed_plans(repl.working_directory)
        title = "Completed Plans"
    else:
        plans = list_pending_plans(repl.working_directory)
        title = "Pending Plans"

    if not plans:
        print(f"  {dim(f'No {title.lower()}.')}")
        return

    print(f"  {bold(title)}")
    print()
    for p in plans:
        display_time = p.created_at[:19] if len(p.created_at) > 19 else p.created_at
        status_tag = f"{green('✓ completed')}" if p.status == "completed" else f"{yellow('○ pending')}"
        print(f"  {cyan(p.name.ljust(25))} {status_tag} {dim(display_time)}")
