"""Interactive user clarification tool.

Allows the agent to ask the user a clarifying question when uncertain.
The tool raises AskUserException, which the REPL catches to prompt the user
for input and feeds the response back as the tool result.
"""

from __future__ import annotations

from typing import Any

from src.tools import Tool, ToolContext


class AskUserException(Exception):
    """Raised when the agent needs user clarification. Caught by the REPL."""

    def __init__(self, question: str) -> None:
        self.question = question
        super().__init__(question)


def execute(args: dict[str, Any], _ctx: ToolContext) -> str:
    question = args.get("question", "")
    if not question or not isinstance(question, str):
        return "Error: missing required argument 'question'."
    raise AskUserException(question)


ask_user_tool = Tool(
    name="ask_user",
    description=(
        "Ask the user a clarifying question when you are uncertain about "
        "something. Use this when instructions are ambiguous, incomplete, "
        "contradictory, or when you need more details to proceed correctly. "
        "The user's response will be returned as the tool result."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The clarifying question to ask the user",
            },
        },
        "required": ["question"],
    },
    execute=execute,
    read_only=False,
    interactive=True,
)
