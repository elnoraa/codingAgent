from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class ToolContext:
    working_directory: str


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, object]
    execute: Callable[[dict[str, object], ToolContext], str]
    read_only: bool = False


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def get_all(self) -> list[Tool]:
        return list(self._tools.values())

    def get_read_only(self) -> list[Tool]:
        return [t for t in self._tools.values() if t.read_only]

    def to_anthropic_tools(self, *, read_only: bool = False) -> list[dict[str, object]]:
        tools = self.get_read_only() if read_only else self.get_all()
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in tools
        ]
