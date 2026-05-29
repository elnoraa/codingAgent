"""System prompt builder — constructs the system prompt for each mode."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.repl.repl import Repl

logger = logging.getLogger(__name__)


def build_system_prompt(repl: "Repl") -> str:
    """Build the system prompt for the current mode, including persona, rules, and context files."""
    from src.mode import PLAN_MODE_SYSTEM_PROMPT, ASK_MODE_SYSTEM_PROMPT

    if repl.mode == "plan":
        base = PLAN_MODE_SYSTEM_PROMPT
    elif repl.mode == "ask":
        base = ASK_MODE_SYSTEM_PROMPT
    else:
        base = repl.system_prompt
    persona = f"\n\n{repl._custom_persona}" if repl._custom_persona else ""

    # ── Load coding-agent.md instructions (if present) ─────────────────
    coding_agent_rules = ""
    coding_agent_path = os.path.join(repl.working_directory, "coding-agent.md")
    if os.path.isfile(coding_agent_path):
        try:
            with open(coding_agent_path, "r", encoding="utf-8") as f:
                rules_text = f.read().strip()
            if rules_text:
                coding_agent_rules = (
                    "\n\n## CODING AGENT RULES (MANDATORY)\n"
                    "The following rules are MANDATORY and MUST be followed at all times:\n"
                    f"{rules_text}"
                )
        except (OSError, IOError):
            pass  # If we can't read it, silently skip

    # Restart instruction (CODE mode only)
    restart_instruction = ""
    if repl.mode == "code":
        restart_instruction = (
            "\n\n## Automatic Session Restart\n"
            "After you complete a task, present a summary of what was done, "
            "and the user is satisfied, call the `restart_session` tool to reset "
            "the session back to turn 1 for the next task."
        )

    # ── Resilience instructions (CODE mode only) ─────────────────────────
    resilience_instruction = ""
    if repl.mode == "code":
        resilience_instruction = (
            "\n\n## Resilience & Task Completion\n"
            "You are expected to complete tasks to the best of your ability. Follow these guidelines:\n\n"
            "1. **Persist through errors**: If a tool call fails with a transient error (network, timeout),\n"
            "   retry it after adjusting parameters if needed. Do not give up on the first failure.\n"
            "2. **Self-verify changes**: After making file changes, use read_file, diff, or run_tests\n"
            "   to verify your changes are correct before declaring the task done.\n"
            "3. **Break down complex tasks**: If a task is complex, break it into smaller sub-steps\n"
            "   and tackle them one at a time. Use the think tool to reason through each step.\n"
            "4. **Recover gracefully**: If a step fails, explain what went wrong, adjust your approach,\n"
            "   and try an alternative. Do not abandon the task at the first obstacle.\n"
            "5. **Report completion clearly**: When a task is fully complete (all steps verified),\n"
            "   present a clear summary of what was done, what files were changed, and any\n"
            "   important notes for the user.\n"
            "6. **Ask for help when stuck**: If you have exhausted all reasonable approaches and\n"
            "   cannot proceed, explain the situation clearly so the user can provide guidance.\n"
        )

    # ── Multi-agent instructions (CODE mode only) ─────────────────────────
    multi_agent_instruction = ""
    if repl.mode == "code":
        multi_agent_instruction = (
            "\n\n## Multi-Agent & Swarm Support\n"
            "You can spawn sub-agents and run agent swarms to handle complex multi-step tasks:\n\n"
            "1. **spawn_agent** — Create a sub-agent to handle a sub-task independently.\n"
            "   Give it a clear, self-contained task. Check results with list_agents.\n"
            "2. **list_agents** — Check the status of your sub-agents (idle/running/completed/error).\n"
            "3. **send_to_agent** — Send instructions, data, or results to a running agent.\n"
            "4. **terminate_agent** — Clean up completed or stuck agents.\n"
            "5. **run_swarm** — Run multiple agents in a collaboration pattern:\n"
            "   • 'sequential': agents run in order, passing results forward\n"
            "   • 'debate': multiple agents independently solve, then compare\n"
            "   • 'broadcast': multiple agents independently solve, best result wins\n\n"
            "Use sub-agents for: parallel file analysis, independent research tasks,\n"
            "multi-file refactoring, code review, and any task that benefits from\n"
            "divide-and-conquer. Always terminate agents after use to free resources."
        )

    # ── Context files injection ────────────────────────────────────────
    context_section = ""
    if repl._context_files:
        import glob as _glob
        injected: list[str] = []
        for pattern in repl._context_files:
            matched = _glob.glob(os.path.join(repl.working_directory, pattern))
            for filepath in matched:
                if not os.path.isfile(filepath):
                    continue
                try:
                    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read(2000)  # cap at 2000 chars
                    relpath = os.path.relpath(filepath, repl.working_directory)
                    injected.append(
                        f"### `{relpath}`\n```\n{content}\n```"
                    )
                except (OSError, IOError):
                    continue
        if injected:
            context_section = (
                "\n\n## Project Context Files\n"
                "The following key project files are provided for context:\n\n"
                + "\n\n".join(injected)
            )

    return (
        f"Current working directory: {repl.working_directory}\n"
        f"Project root: {repl.working_directory}\n\n"
        f"{base}\n\n"
        f"Remember to explore the codebase with read-only tools before making changes."
        f"{persona}"
        f"{coding_agent_rules}"
        f"{restart_instruction}"
        f"{resilience_instruction}"
        f"{multi_agent_instruction}"
        f"{context_section}"
    )


def build_orchestrator_system_prompt(repl: "Repl") -> str:
    """Return a base system prompt for the orchestrator (less decoration)."""
    return (
        f"Current working directory: {repl.working_directory}\n"
        f"Project root: {repl.working_directory}\n\n"
        f"{repl.system_prompt}\n\n"
        f"Remember to explore the codebase with read-only tools before making changes."
    )
