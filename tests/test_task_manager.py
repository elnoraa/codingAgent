"""Tests for the Task Manager — multi-step task persistence.

NOTE: These tests use the tasks/ directory relative to the project root
because the task_manager module uses a global TASKS_DIR = Path("tasks").
Cleaning up after each test is critical.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from src.task_manager import (
    STATUS_COMPLETED,
    STATUS_IN_PROGRESS,
    STATUS_PENDING,
    Task,
    TaskStep,
    _save_task,
    create_task,
    delete_task,
    list_tasks,
    load_task,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_tasks_dir() -> Iterator[None]:
    """Clean the global tasks/ dir before and after each test."""
    tasks_dir = Path("tasks")
    if tasks_dir.exists():
        for item in tasks_dir.iterdir():
            if item.is_file():
                item.unlink()
    yield
    if tasks_dir.exists():
        for item in tasks_dir.iterdir():
            if item.is_file():
                item.unlink()


# ── TaskStep Tests ────────────────────────────────────────────────────────────


class TestTaskStep:
    """Verify TaskStep data class."""

    def test_create_step(self) -> None:
        step = TaskStep(id="1", name="Step 1")
        assert step.id == "1"
        assert step.name == "Step 1"
        assert step.status == STATUS_PENDING

    def test_step_defaults(self) -> None:
        step = TaskStep(id="1", name="test")
        assert step.description == ""
        assert step.notes == ""
        assert step.created_at > 0
        assert step.completed_at is None

    def test_step_duration_with_completion(self) -> None:
        step = TaskStep(id="1", name="test", created_at=1000.0, completed_at=1050.0)
        assert step.duration == 50.0

    def test_step_duration_without_completion(self) -> None:
        step = TaskStep(id="1", name="test", created_at=1000.0, completed_at=None)
        assert step.duration is None

    def test_step_status_transitions(self) -> None:
        step = TaskStep(id="1", name="test")
        assert step.status == STATUS_PENDING
        step.status = STATUS_IN_PROGRESS
        assert step.status == STATUS_IN_PROGRESS
        step.status = STATUS_COMPLETED
        assert step.status == STATUS_COMPLETED


# ── Task Tests ────────────────────────────────────────────────────────────────


class TestTask:
    """Verify Task data class."""

    def test_create_task(self) -> None:
        task = Task(name="my-task", description="a test task")
        assert task.name == "my-task"
        assert task.description == "a test task"
        assert task.steps == []
        assert task.status == STATUS_PENDING

    def test_task_defaults(self) -> None:
        task = Task(name="test")
        assert task.description == ""
        assert task.steps == []
        assert task.context == {}
        assert task.created_at > 0

    def test_add_step(self) -> None:
        task = Task(name="test", steps=[TaskStep(id="1", name="Step 1")])
        assert len(task.steps) == 1
        assert task.steps[0].name == "Step 1"

    def test_add_multiple_steps(self) -> None:
        steps = [TaskStep(id=str(i), name=f"Step {i}") for i in range(3)]
        task = Task(name="test", steps=steps)
        assert len(task.steps) == 3

    def test_progress_all_pending(self) -> None:
        steps = [TaskStep(id=str(i), name=f"S{i}") for i in range(4)]
        task = Task(name="test", steps=steps)
        assert task.progress == 0.0

    def test_progress_half_completed(self) -> None:
        steps = [
            TaskStep(id="0", name="S0", status=STATUS_COMPLETED),
            TaskStep(id="1", name="S1", status=STATUS_COMPLETED),
            TaskStep(id="2", name="S2", status=STATUS_PENDING),
            TaskStep(id="3", name="S3", status=STATUS_PENDING),
        ]
        task = Task(name="test", steps=steps)
        assert task.progress == 0.5  # 50%


# ── Save/Load Task Tests ─────────────────────────────────────────────────────


class TestTaskPersistence:
    """Verify task save/load round-trip."""

    def test_save_and_load(self) -> None:
        task = Task(
            name="test-task",
            description="testing",
            steps=[TaskStep(id="1", name="Step 1", status=STATUS_COMPLETED)],
        )
        _save_task(task)

        loaded = load_task("test-task")
        assert loaded is not None
        assert loaded.name == "test-task"
        assert loaded.description == "testing"
        assert len(loaded.steps) == 1
        assert loaded.steps[0].status == STATUS_COMPLETED

    def test_save_creates_file(self) -> None:
        task = Task(name="persisted-task")
        _save_task(task)
        task_file = Path("tasks") / "persisted-task.json"
        assert task_file.is_file()

    def test_load_nonexistent(self) -> None:
        loaded = load_task("nonexistent")
        assert loaded is None

    def test_list_tasks(self) -> None:
        t1 = Task(name="task-1")
        t2 = Task(name="task-2")
        _save_task(t1)
        _save_task(t2)
        tasks = list_tasks()
        assert len(tasks) == 2
        names = [t["name"] for t in tasks]
        assert "task-1" in names
        assert "task-2" in names

    def test_list_tasks_empty(self) -> None:
        tasks = list_tasks()
        assert tasks == []

    def test_delete_task(self) -> None:
        task = Task(name="to-delete")
        _save_task(task)
        assert Path("tasks/to-delete.json").exists()
        result = delete_task("to-delete")
        assert result is True
        assert not Path("tasks/to-delete.json").exists()

    def test_delete_nonexistent(self) -> None:
        """Deleting a non-existent task should return False, not crash."""
        result = delete_task("nonexistent")
        assert result is False

    def test_round_trip_preserves_context(self) -> None:
        task = Task(name="context-task")
        task.context["key1"] = "value1"
        task.context["key2"] = 42
        _save_task(task)

        loaded = load_task("context-task")
        assert loaded is not None
        assert loaded.context["key1"] == "value1"
        assert loaded.context["key2"] == 42

    def test_round_trip_preserves_steps(self) -> None:
        steps = [
            TaskStep(id="1", name="Research", status=STATUS_COMPLETED),
            TaskStep(id="2", name="Implement", status=STATUS_IN_PROGRESS, notes="halfway done"),
            TaskStep(id="3", name="Test", status=STATUS_PENDING),
        ]
        task = Task(name="multi-step", steps=steps)
        _save_task(task)

        loaded = load_task("multi-step")
        assert loaded is not None
        assert len(loaded.steps) == 3
        assert loaded.steps[1].name == "Implement"
        assert loaded.steps[1].notes == "halfway done"

    def test_create_task_function(self) -> None:
        """The create_task convenience function should work."""
        result = create_task("created-task", "A task created via create_task")
        assert "created" in result.lower()
        loaded = load_task("created-task")
        assert loaded is not None
        assert loaded.description == "A task created via create_task"

    def test_create_task_duplicate(self) -> None:
        create_task("dup-task")
        result = create_task("dup-task")
        assert "error" in result.lower() or "already exists" in result.lower()
