"""Task management commands — /task."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.formatting import bold, dim, green, red, yellow

if TYPE_CHECKING:
    from src.repl.repl import Repl


def handle_task(repl: Repl, args: str) -> None:
    """Handle /task commands."""
    from datetime import datetime as _dt

    from src.task_manager import (
        STATUS_COMPLETED,
        STATUS_FAILED,
        STATUS_IN_PROGRESS,
        STATUS_PENDING,
        TaskStep,
        _save_task,
        complete_step,
        create_task,
        delete_task,
        list_tasks,
        load_task,
        update_context,
    )

    parts = args.strip().split(maxsplit=2)
    subcmd = parts[0].lower() if parts else ""

    if subcmd in ("start", "create"):
        if len(parts) < 2:
            print("  Usage: /task start <name> [description]")
            return
        name = parts[1]
        description = parts[2] if len(parts) > 2 else ""
        result = create_task(name, description)
        print(f"  {result}")

    elif subcmd == "step":
        if len(parts) < 3:
            print("  Usage: /task step <name> <step_name>")
            return
        name = parts[1]
        step_name = parts[2] if len(parts) > 2 else ""

        task = load_task(name)
        if task is None:
            print(f"  {red('✗')} Task '{name}' not found.")
            return

        if any(s.name == step_name for s in task.steps):
            print(f"  {yellow('⚠')} Step '{step_name}' already exists in task '{name}'.")
            return

        step_id = f"step-{len(task.steps) + 1}"
        task.steps.append(TaskStep(id=step_id, name=step_name))
        task.status = STATUS_IN_PROGRESS
        _save_task(task)
        print(f"  Added step '{step_name}' to task '{name}'.")

    elif subcmd in ("complete-step", "done"):
        if len(parts) < 3:
            print("  Usage: /task complete-step <name> <step_name> [notes]")
            return
        name = parts[1]
        step_name = parts[2] if len(parts) > 2 else ""
        notes = parts[3] if len(parts) > 3 else ""
        result = complete_step(name, step_name, notes)
        print(f"  {result}")

    elif subcmd == "status":
        name = parts[1] if len(parts) > 1 else ""
        if not name:
            tasks = list_tasks()
            if not tasks:
                print("  No tasks found.")
                return
            print(f"\n  {bold('Tasks')}")
            print(f"  {'─' * 60}")
            for t in tasks:
                status_color = {
                    "completed": green("✓"),
                    "in_progress": yellow("⟳"),
                    "failed": red("✗"),
                    "pending": dim("○"),
                }.get(t["status"], dim("○"))
                print(f"  {status_color} {t['name']:<25} [{t['progress']:<5}] {dim(t['updated'])}")
            return

        task = load_task(name)
        if task is None:
            print(f"  {red('✗')} Task '{name}' not found.")
            return

        bar_len = 20
        filled = int(task.progress * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)

        print(f"\n  {bold(f'Task: {task.name}')}")
        if task.description:
            print(f"  {dim(task.description)}")
        print(f"  Status: {task.status}")
        print(f"  Progress: [{bar}] {task.completed_steps}/{task.total_steps} ({task.progress:.0%})")
        print(f"  Created: {_dt.fromtimestamp(task.created_at).strftime('%Y-%m-%d %H:%M')}")
        print()

        if task.steps:
            print(f"  {bold('Steps:')}")
            for step in task.steps:
                status_icon = {
                    STATUS_COMPLETED: green("✓"),
                    STATUS_IN_PROGRESS: yellow("⟳"),
                    STATUS_FAILED: red("✗"),
                    STATUS_PENDING: dim("○"),
                }.get(step.status, dim("○"))
                print(f"  {status_icon} {step.name}")
                if step.notes:
                    print(f"    {dim(step.notes)}")
            print()

        if task.context:
            print(f"  {bold('Context:')}")
            for k, v in task.context.items():
                print(f"    {k}: {v}")

    elif subcmd == "resume":
        name = parts[1] if len(parts) > 1 else ""
        import json as _json

        if not name:
            tasks = list_tasks(status_filter=STATUS_IN_PROGRESS)
            if not tasks:
                print("  No in-progress tasks to resume.")
                return
            name = tasks[0]["name"]

        task = load_task(name)
        if task is None:
            print(f"  {red('✗')} Task '{name}' not found.")
            return

        print(f"\n  {bold(f'Resuming task: {task.name}')}")
        if task.description:
            print(f"  {dim(task.description)}")
        print(f"  Progress: {task.completed_steps}/{task.total_steps} ({task.progress:.0%})")

        next_step = next(
            (s for s in task.steps if s.status != STATUS_COMPLETED),
            None,
        )
        if next_step:
            print(f"  Next step: {green(next_step.name)}")

        if task.context:
            print(f"  Context: {_json.dumps(task.context, indent=2)}")

    elif subcmd == "delete":
        name = parts[1] if len(parts) > 1 else ""
        if not name:
            print("  Usage: /task delete <name>")
            return
        if delete_task(name):
            print(f"  Deleted task: {name}")
        else:
            print(f"  {red('✗')} Task '{name}' not found.")

    elif subcmd == "context":
        if len(parts) < 3:
            print("  Usage: /task context <name> <key>=<value>")
            return
        name = parts[1]
        kv = parts[2].split("=", 1)
        if len(kv) != 2:
            print("  Use format: key=value")
            return
        result = update_context(name, kv[0], kv[1])
        print(f"  {result}")

    else:
        print("  Usage: /task [start|step|complete-step|status|resume|delete|context]")
