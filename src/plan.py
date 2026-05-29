"""Plan file management for the Coding Agent.

Plans are stored as Markdown files in:
- plans/pending/   — plans awaiting user approval
- plans/completed/ — plans that have been approved and acted upon

Each plan is a Markdown file with YAML front-matter containing metadata.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from .logging_config import get_logger

logger = get_logger(__name__)


PLANS_DIR = "plans"
PENDING_DIR = "pending"
COMPLETED_DIR = "completed"


@dataclass
class Plan:
    """Represents a saved plan."""

    name: str
    content: str
    status: str  # "pending" or "completed"
    created_at: str
    completed_at: str | None = None
    filepath: str | None = None


def _ensure_dirs(working_directory: str) -> tuple[Path, Path, Path]:
    """Ensure plans/{pending,completed} directories exist. Returns (plans_dir, pending_dir, completed_dir)."""
    base = Path(working_directory).resolve()
    plans_dir = base / PLANS_DIR
    pending_dir = plans_dir / PENDING_DIR
    completed_dir = plans_dir / COMPLETED_DIR
    pending_dir.mkdir(parents=True, exist_ok=True)
    completed_dir.mkdir(parents=True, exist_ok=True)
    return plans_dir, pending_dir, completed_dir


def _sanitize_name(name: str) -> str:
    """Sanitize a plan name for use as a filename."""
    safe = name.strip().replace(" ", "-")
    safe = "".join(c for c in safe if c.isalnum() or c in "-_.")
    if not safe:
        safe = f"plan-{int(time.time())}"
    return safe


def _strip_leading_number(name: str) -> str:
    """Strip an existing leading numeric prefix (e.g. '05-', '123-') from a plan name.

    This prevents double-numbering when a user passes a name that already
    contains a numeric prefix (e.g. '05-feat-add-login' becomes 'feat-add-login').
    """
    return re.sub(r"^\d+-", "", name, count=1)


def _get_next_plan_number(working_directory: str) -> int:
    """Return the next available plan number (highest existing + 1, default 1).

    Scans both plans/pending/ and plans/completed/ for .md files with
    a leading numeric prefix (e.g. "01-", "23-") and returns max + 1.
    """
    _, pending_dir, completed_dir = _ensure_dirs(working_directory)
    max_num = 0

    for directory in (pending_dir, completed_dir):
        if not directory.is_dir():
            continue
        for f in directory.iterdir():
            if f.suffix != ".md":
                continue
            match = re.match(r"^(\d+)", f.stem)
            if match:
                num = int(match.group(1))
                if num > max_num:
                    max_num = num
    return max_num + 1


def save_pending_plan(name: str, content: str, working_directory: str) -> str:
    """Save a plan to plans/pending/. Returns the file path.

    Automatically prepends a sequential numeric prefix (e.g., "01-", "02-")
    based on the highest existing plan number in both pending/ and completed/.

    If *name* already starts with a numeric prefix (e.g. ``"05-feat-foo"``),
    that prefix is stripped first to avoid double-numbering.
    """
    _, pending_dir, _ = _ensure_dirs(working_directory)
    next_num = _get_next_plan_number(working_directory)
    clean_name = _strip_leading_number(name)
    prefixed_name = f"{next_num:02d}-{clean_name}"
    safe_name = _sanitize_name(prefixed_name)
    timestamp = datetime.now().isoformat()

    # Build the Markdown file with front-matter
    plan_content = f"""---
name: {safe_name}
status: pending
created_at: {timestamp}
---

{content}
"""
    filepath = pending_dir / f"{safe_name}.md"
    filepath.write_text(plan_content, encoding="utf-8")
    logger.info("Plan saved as pending: name=%s, file=%s", safe_name, filepath)
    return str(filepath)


def complete_plan(name: str, working_directory: str) -> bool:
    """Move a plan from plans/pending/ to plans/completed/. Returns True on success."""
    _, pending_dir, completed_dir = _ensure_dirs(working_directory)
    safe_name = _sanitize_name(name)
    src = pending_dir / f"{safe_name}.md"

    if not src.is_file():
        # Try to find a matching file
        matches = list(pending_dir.glob(f"{safe_name}*"))
        if not matches:
            logger.warning("Plan not found for completion: name=%s", safe_name)
            return False
        src = matches[0]

    timestamp = datetime.now().isoformat()
    content = src.read_text(encoding="utf-8")

    # Update front-matter status
    updated = re.sub(
        r"status: pending",
        f"status: completed\ncompleted_at: {timestamp}",
        content,
    )

    dst = completed_dir / src.name
    dst.write_text(updated, encoding="utf-8")
    src.unlink()
    logger.info("Plan completed: name=%s, moved to %s", safe_name, dst)
    return True


def list_pending_plans(working_directory: str) -> list[Plan]:
    """List all pending plans."""
    _, pending_dir, _ = _ensure_dirs(working_directory)
    return _list_plans_from_dir(pending_dir, "pending")


def list_completed_plans(working_directory: str) -> list[Plan]:
    """List all completed plans."""
    _, _, completed_dir = _ensure_dirs(working_directory)
    return _list_plans_from_dir(completed_dir, "completed")


def _list_plans_from_dir(directory: Path, status: str) -> list[Plan]:
    """List plans from a specific directory."""
    plans: list[Plan] = []
    if not directory.is_dir():
        return plans

    for f in sorted(directory.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if f.suffix != ".md":
            continue
        try:
            content = f.read_text(encoding="utf-8")
            # Parse basic front-matter
            name_match = re.search(r"^name:\s*(.+)$", content, re.MULTILINE)
            created_match = re.search(r"^created_at:\s*(.+)$", content, re.MULTILINE)
            completed_match = re.search(r"^completed_at:\s*(.+)$", content, re.MULTILINE)

            plans.append(
                Plan(
                    name=name_match.group(1).strip() if name_match else f.stem,
                    content=content,
                    status=status,
                    created_at=created_match.group(1).strip() if created_match else "unknown",
                    completed_at=completed_match.group(1).strip() if completed_match else None,
                    filepath=str(f),
                )
            )
        except (OSError, UnicodeDecodeError):
            continue

    return plans


def generate_plan_template(topic: str) -> str:
    """Generate a structured Markdown plan template for a given topic/task."""
    return f"""# Plan: {topic}

## Overview

<!-- Briefly describe what this plan aims to accomplish -->

## Files to Modify

<!-- List the files that will be created, modified, or deleted -->

### New Files

- ...

### Modified Files

- ...

### Deleted Files

- ...

## Implementation Steps

### Step 1: <!-- Description -->

- [ ] ...
- [ ] ...

### Step 2: <!-- Description -->

- [ ] ...
- [ ] ...

## Architecture / Design Decisions

<!-- Explain any trade-offs, design choices, or architectural implications -->

## Dependencies

<!-- List any external dependencies, new imports, or configuration changes -->

## Testing Plan

<!-- Describe how the changes will be tested -->

- [ ] Unit tests
- [ ] Integration tests
- [ ] Manual verification

## Potential Risks

<!-- List any risks, edge cases, or areas of concern -->
"""
