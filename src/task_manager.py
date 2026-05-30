"""Task manager for long-running multi-step tasks with progress persistence."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .logging_config import get_logger

logger = get_logger(__name__)

# Task storage directory
TASKS_DIR = Path("tasks")

# Status constants
STATUS_PENDING = "pending"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked"


@dataclass
class TaskStep:
    """A single step in a multi-step task."""

    id: str
    name: str
    description: str = ""
    status: str = STATUS_PENDING
    notes: str = ""
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None

    @property
    def duration(self) -> float | None:
        if self.completed_at:
            return self.completed_at - self.created_at
        return None


@dataclass
class Task:
    """A multi-step task with progress tracking."""

    name: str
    description: str = ""
    steps: list[TaskStep] = field(default_factory=list)
    status: str = STATUS_PENDING
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    context: dict[str, Any] = field(default_factory=dict)
    """Arbitrary context data saved with the task (e.g., current file paths, variables)."""

    @property
    def progress(self) -> float:
        """Return completion percentage (0.0 to 1.0)."""
        if not self.steps:
            return 0.0
        completed = sum(1 for s in self.steps if s.status == STATUS_COMPLETED)
        return completed / len(self.steps)

    @property
    def completed_steps(self) -> int:
        return sum(1 for s in self.steps if s.status == STATUS_COMPLETED)

    @property
    def total_steps(self) -> int:
        return len(self.steps)


def _ensure_tasks_dir() -> Path:
    """Create tasks directory if it doesn't exist."""
    tasks_dir = TASKS_DIR.resolve()
    tasks_dir.mkdir(parents=True, exist_ok=True)
    return tasks_dir


def _task_path(name: str) -> Path:
    """Get the file path for a task."""
    safe_name = name.replace(" ", "_").replace("/", "_").replace("\\", "_")
    return _ensure_tasks_dir() / f"{safe_name}.json"


def create_task(name: str, description: str = "", steps: list[dict[str, str]] | None = None) -> str:
    """Create a new task.

    Args:
        name: Task name (used as filename)
        description: Task description
        steps: List of dicts with 'name' and optional 'description' keys

    Returns:
        Success or error message
    """
    task_path = _task_path(name)
    if task_path.exists():
        return f"Error: task '{name}' already exists."

    task_steps: list[TaskStep] = []
    if steps:
        for i, step in enumerate(steps):
            task_steps.append(
                TaskStep(
                    id=f"step-{i + 1}",
                    name=step.get("name", f"Step {i + 1}"),
                    description=step.get("description", ""),
                )
            )

    task = Task(
        name=name,
        description=description,
        steps=task_steps,
    )

    _save_task(task)
    return f"Task '{name}' created with {len(task_steps)} step(s)."


def _save_task(task: Task) -> None:
    """Save a task to disk."""
    task.updated_at = time.time()
    data = {
        "name": task.name,
        "description": task.description,
        "status": task.status,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "context": task.context,
        "steps": [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "status": s.status,
                "notes": s.notes,
                "created_at": s.created_at,
                "completed_at": s.completed_at,
            }
            for s in task.steps
        ],
    }

    task_path = _task_path(task.name)
    task_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("Saved task: %s (%d steps)", task.name, len(task.steps))


def load_task(name: str) -> Task | None:
    """Load a task from disk."""
    task_path = _task_path(name)
    if not task_path.exists():
        return None

    try:
        data = json.loads(task_path.read_text(encoding="utf-8"))
        steps = [
            TaskStep(
                id=s["id"],
                name=s["name"],
                description=s.get("description", ""),
                status=s.get("status", STATUS_PENDING),
                notes=s.get("notes", ""),
                created_at=s.get("created_at", time.time()),
                completed_at=s.get("completed_at"),
            )
            for s in data.get("steps", [])
        ]

        return Task(
            name=data["name"],
            description=data.get("description", ""),
            steps=steps,
            status=data.get("status", STATUS_PENDING),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            context=data.get("context", {}),
        )
    except Exception as e:
        logger.error("Failed to load task '%s': %s", name, e)
        return None


def list_tasks(status_filter: str | None = None) -> list[dict[str, Any]]:
    """List all saved tasks with metadata."""
    tasks_dir = _ensure_tasks_dir()
    tasks: list[dict[str, Any]] = []

    for f in tasks_dir.iterdir():
        if f.suffix == ".json":
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if status_filter and data.get("status") != status_filter:
                    continue

                steps_total = len(data.get("steps", []))
                steps_done = sum(1 for s in data.get("steps", []) if s.get("status") == STATUS_COMPLETED)

                tasks.append(
                    {
                        "name": data["name"],
                        "description": data.get("description", ""),
                        "status": data.get("status", STATUS_PENDING),
                        "progress": f"{steps_done}/{steps_total}",
                        "updated": datetime.fromtimestamp(data.get("updated_at", 0)).strftime("%Y-%m-%d %H:%M"),
                    }
                )
            except Exception:
                continue

    return sorted(tasks, key=lambda t: t["updated"], reverse=True)


def complete_step(task_name: str, step_id: str, notes: str = "") -> str:
    """Mark a step as completed."""
    task = load_task(task_name)
    if task is None:
        return f"Error: task '{task_name}' not found."

    for step in task.steps:
        if step.id == step_id or step.name == step_id:
            step.status = STATUS_COMPLETED
            step.completed_at = time.time()
            if notes:
                step.notes = notes
            break
    else:
        return f"Error: step '{step_id}' not found in task '{task_name}'."

    # Update task status
    if task.progress >= 1.0:
        task.status = STATUS_COMPLETED
    else:
        task.status = STATUS_IN_PROGRESS

    _save_task(task)
    return f"Step '{step_id}' completed. Progress: {task.completed_steps}/{task.total_steps}"


def update_context(task_name: str, key: str, value: Any) -> str:
    """Update task context with a key-value pair."""
    task = load_task(task_name)
    if task is None:
        return f"Error: task '{task_name}' not found."

    task.context[key] = value
    _save_task(task)
    return f"Context updated: {key} = {value}"


def delete_task(name: str) -> bool:
    """Delete a task file."""
    task_path = _task_path(name)
    if not task_path.exists():
        return False
    task_path.unlink()
    return True
