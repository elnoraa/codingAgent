"""Conversation branching for exploring alternative approaches."""

from __future__ import annotations

import copy
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from .logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class Branch:
    """A forked conversation branch."""
    name: str
    parent: str  # Name of the parent branch (empty for main)
    created_at: float
    messages: list[dict[str, object]]
    description: str = ""

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def age(self) -> str:
        elapsed = time.time() - self.created_at
        if elapsed < 60:
            return f"{elapsed:.0f}s ago"
        elif elapsed < 3600:
            return f"{elapsed/60:.0f}m ago"
        else:
            return f"{elapsed/3600:.1f}h ago"


class BranchManager:
    """Manages conversation branches."""

    def __init__(self, initial_messages: list[dict[str, object]] | None = None):
        self._branches: dict[str, Branch] = {}
        self._active_branch: str = "main"

        # Initialize main branch
        self._branches["main"] = Branch(
            name="main",
            parent="",
            created_at=time.time(),
            messages=list(initial_messages or []),
            description="Main conversation",
        )

    @property
    def active_branch(self) -> str:
        return self._active_branch

    @property
    def active_messages(self) -> list[dict[str, object]]:
        return self._branches[self._active_branch].messages

    @active_messages.setter
    def active_messages(self, messages: list[dict[str, object]]) -> None:
        self._branches[self._active_branch].messages = messages

    def fork(self, name: str, description: str = "") -> bool:
        """Fork the current branch at its current state.

        Returns True if fork was created, False if name already exists.
        """
        if name in self._branches:
            return False

        current = self._branches[self._active_branch]
        self._branches[name] = Branch(
            name=name,
            parent=self._active_branch,
            created_at=time.time(),
            messages=copy.deepcopy(current.messages),
            description=description or f"Fork from {self._active_branch}",
        )
        return True

    def switch(self, name: str) -> bool:
        """Switch to a different branch.

        Returns True if switch succeeded, False if branch doesn't exist.
        """
        if name not in self._branches:
            return False
        self._active_branch = name
        return True

    def delete(self, name: str) -> bool:
        """Delete a branch (cannot delete main or active branch).

        Returns True if deleted.
        """
        if name == "main" or name == self._active_branch:
            return False
        if name not in self._branches:
            return False
        del self._branches[name]
        return True

    def list_branches(self) -> list[dict[str, Any]]:
        """List all branches with metadata."""
        return [
            {
                "name": b.name,
                "parent": b.parent,
                "messages": b.message_count,
                "age": b.age,
                "description": b.description,
                "active": b.name == self._active_branch,
            }
            for b in self._branches.values()
        ]

    def get_branch(self, name: str) -> Branch | None:
        return self._branches.get(name)

    def update_messages(self, messages: list[dict[str, object]]) -> None:
        """Update the active branch's messages."""
        self._branches[self._active_branch].messages = messages

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for session saving."""
        return {
            "active_branch": self._active_branch,
            "branches": {
                name: {
                    "name": b.name,
                    "parent": b.parent,
                    "created_at": b.created_at,
                    "messages": b.messages,
                    "description": b.description,
                }
                for name, b in self._branches.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BranchManager":
        """Create from saved session data."""
        manager = cls()
        manager._active_branch = data.get("active_branch", "main")
        manager._branches = {}
        for name, bd in data.get("branches", {}).items():
            manager._branches[name] = Branch(
                name=bd["name"],
                parent=bd.get("parent", ""),
                created_at=bd.get("created_at", time.time()),
                messages=bd.get("messages", []),
                description=bd.get("description", ""),
            )
        return manager
