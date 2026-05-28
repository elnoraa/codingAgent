from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from .client import LlmClient
from .logging_config import get_logger
from .mode import PLAN_MODE_SYSTEM_PROMPT
from tools import ToolContext, ToolRegistry

logger = get_logger(__name__)
from tools.read_file import read_file_tool
from tools.write_file import write_file_tool
from tools.edit_file import edit_file_tool
from tools.glob_tool import glob_tool
from tools.grep_tool import grep_tool
from tools.bash_tool import bash_tool
from tools.directory_tree import directory_tree_tool
from tools.list_directory import list_directory_tool
from tools.file_search import file_search_tool
from tools.diff_tool import diff_tool
from tools.replace_in_files import replace_in_files_tool
from tools.run_tests import run_tests_tool
from tools.git_commit import git_commit_tool
from tools.git_push import git_push_tool
from tools.git_status import git_status_tool
from tools.url_fetch import url_fetch_tool
from tools.think_tool import think_tool
from tools.web_search import web_search_tool
from .session import save_session, load_session, list_sessions
from typing import cast

from .plan import (
    complete_plan,
    generate_plan_template,
    list_completed_plans,
    list_pending_plans,
    save_pending_plan,
)
from .utils import bold, dim, green, yellow, cyan, red, color_json, estimate_tokens, trim_messages, blue, magenta

# ── Readline (command history with arrow keys) ──────────────────────────
_readline_available = False
try:
    import readline  # noqa: F401 — enables line editing & history in input()
    _readline_available = True
except ImportError:
    try:
        import pyreadline3  # type: ignore[import-untyped]  # noqa: F401
        _readline_available = True
    except ImportError:
        pass

# ── Cost estimates per 1M tokens (in USD) ─────────────────────────────
MODEL_PRICING: dict[str, dict[str, float]] = {
    "deepseek-chat": {"input": 0.14, "output": 0.28},
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
}

HELP_TEXT = f"""\
{bold('Commands')}
  exit, /q                Exit the agent
  /help, /h               Show this help
  /clear, /c              Clear conversation history
  /tools                  List available tools
  /history                Show detailed message/token/role breakdown
  /status, /s             Show session status (tokens, model, mode, uptime)
  /mode                   Show current mode (code/plan)
  /plan, /p               Switch to plan mode (read-only exploration)
  /code                   Switch to code mode (all tools available)
  /plan save <name>       Save last assistant response as a plan file
  /plan create <topic>    Create a structured plan template for a task
  /plan list              List pending plans awaiting approval
  /plan list completed    List completed plans
  /edit                   Edit and re-send the last user message
  /retry, /r              Re-send the last user message (e.g. after API error)
  /save <name>            Save the current session
  /load <name>            Load a saved session
  /sessions               List all saved sessions
  /persona <text>         Set a custom persona (appended to system prompt)
  /persona clear          Clear the custom persona
  /reload                 Re-discover and re-register all tools from disk (no restart needed)
  /restart                Reset session to turn 1 (clear messages, restart plan-first cycle)
  /cost                   Show token usage and estimated API cost
  /config                 Show current configuration

{bold('Multi-line input')}
  End a line with \\  to continue typing on the next line.
  This lets you paste code blocks or long instructions.

{bold('Tools')}
  read_file       Read a file's contents
  write_file      Create or overwrite a file
  edit_file       Make targeted search-and-replace edits
  glob            Search for files by pattern
  grep            Search file contents for text
  bash            Run shell commands
  directory_tree  Show project directory structure
  list_directory  List a directory's contents
  file_search     Full-text search via ripgrep/grep
  diff            Show git diff of changes
  replace_in_files  Bulk find-and-replace across files
  run_tests       Auto-detect and run tests
  git_commit      Stage and commit changes
  git_push        Push commits to a remote repository
  git_status      Show git status (branch, changes, unpushed commits)
  url_fetch       Fetch a URL's content
  think           Reason step by step (no-op)
  web_search      Search the web for information

{bold('Modes')}
  CODE mode  {green('●')}  All tools available (read + write + execute)
  PLAN mode  {yellow('●')}  Read-only exploration & planning (read-only tools only)

{bold('Plan-First Enforcement')}
  In CODE mode, the first turn is automatically read-only (planning phase).
  After the assistant presents a plan, type {green('proceed')} to approve it.
  Write tools (write_file, edit_file, bash, etc.) are BLOCKED until you approve.
  Plans are auto-saved to plans/pending/ and moved to plans/completed/ after approval.
  Type {cyan('/restart')} to reset the session and start a fresh plan cycle from turn 1.
  If you ask the assistant to refine the plan (instead of approving), the updated plan
  is re-saved and the approval prompt is shown again."""


def _plan_name_from_text(text: str) -> str:
    """Extract a safe plan name from the first meaningful line of text."""
    text = text.strip()
    if not text:
        return f"plan-{int(time.time())}"
    # Take the first line
    first_line = text.split("\n")[0].strip()
    # Remove markdown heading markers and common prefixes
    name = first_line.lstrip("#").strip()
    # Limit length and sanitize
    name = name[:50]
    safe = "".join(c for c in name if c.isalnum() or c in " -_")
    safe = safe.strip().replace(" ", "-")
    if not safe:
        return f"plan-{int(time.time())}"
    return safe.lower()


class Repl:

    # ── Plan-first enforcement helpers ────────────────────────────────────

    @staticmethod
    def _is_approval(text: str) -> bool:
        """Check if user input is an approval to proceed with execution."""
        lowered = text.strip().lower()
        approval_phrases = {
            "proceed",
            "go ahead",
            "approved",
            "approve",
            "yes proceed",
            "yes, proceed",
            "let's go",
            "lets go",
            "let's proceed",
            "lets proceed",
            "do it",
            "execute",
            "y",
            "yes",
            "ok",
            "okay",
            "sure",
            "looks good",
            "looks good, proceed",
            "approved, proceed",
        }
        return lowered in approval_phrases or any(
            lowered.startswith(p) for p in ("proceed", "go ahead", "approved")
        )

    def __init__(
        self,
        llm: LlmClient,
        system_prompt: str,
        max_tokens: int,
        custom_persona: str = "",
    ) -> None:
        self.llm = llm
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens
        self.messages: list[dict[str, object]] = []
        self.working_directory = os.getcwd()
        self.mode = "code"
        self._turn_number = 0
        self._start_time = time.time()
        self._custom_persona = custom_persona

        # Cost tracking
        self._input_tokens_total = 0
        self._output_tokens_total = 0

        # Plan-first enforcement
        self._plan_pending_approval: bool = False
        self._plan_current_name: str | None = None
        self._plan_auto_saved: bool = False
        self._first_code_turn_done: bool = False

        self.tools = ToolRegistry()
        self._register_all_tools()
        logger.info(
            "REPL initialized: mode=%s, model=%s, max_tokens=%d, persona=%s",
            self.mode, self.llm.model, self.max_tokens,
            bool(self._custom_persona),
        )

    def _register_all_tools(self) -> None:
        """Register all available tools into the registry.

        On first call this registers from the already-imported module-level
        ``*_tool`` variables.  On subsequent calls (e.g. after ``/reload``) it
        uses ``ToolRegistry.rebuild()`` to re-discover tools dynamically.
        """
        self.tools.register(read_file_tool)
        self.tools.register(write_file_tool)
        self.tools.register(edit_file_tool)
        self.tools.register(glob_tool)
        self.tools.register(grep_tool)
        self.tools.register(bash_tool)
        self.tools.register(directory_tree_tool)
        self.tools.register(list_directory_tool)
        self.tools.register(file_search_tool)
        self.tools.register(diff_tool)
        self.tools.register(replace_in_files_tool)
        self.tools.register(run_tests_tool)
        self.tools.register(git_commit_tool)
        self.tools.register(git_push_tool)
        self.tools.register(git_status_tool)
        self.tools.register(url_fetch_tool)
        self.tools.register(think_tool)
        self.tools.register(web_search_tool)

    def start(self) -> None:
        print()
        print(f"  {bold('Coding Agent')} {dim('v0.6')}")
        print(f"  {dim('Type /help for commands, exit to quit.')}")
        print(f"  {dim('Model:')} {cyan(self.llm.model)}")
        print(f"  {dim('History:')} {cyan('enabled' if _readline_available else 'unavailable')} (up/down arrows)")
        print()
        self._print_separator()
        print()
        try:
            self._run_loop()
        except EOFError:
            print()
        except KeyboardInterrupt:
            print("\nExiting...")

    def _turn_separator_color(self):
        """Return the color function for the current mode's separator."""
        return yellow if self.mode == "plan" else dim

    def _print_separator(self) -> None:
        """Print a mode-aware separator line."""
        color_fn = self._turn_separator_color()
        print(f"  {color_fn('─' * 60)}")

    def _read_multiline(self, mode_tag: str, wd_display: str) -> str:
        """Read a potentially multi-line input from the user.
        Lines ending with \\ continue to the next line.
        Returns the joined input with trailing backslash-newlines resolved.
        """
        lines: list[str] = []
        while True:
            prompt = f"  {bold(mode_tag)} {cyan(wd_display)} {green('❯')} "
            if lines:
                # Continuation prompt (no prompt symbol)
                prompt = f"  {bold(mode_tag)} {cyan(wd_display)} {dim('│')} "
            try:
                raw = input(prompt)
            except (EOFError, KeyboardInterrupt):
                return ""  # signal cancellation

            if not raw and not lines:
                # Empty line with no prior input — skip
                return ""

            if raw.endswith("\\"):
                # Line continuation: strip trailing \ and collect
                lines.append(raw[:-1])
                continue

            lines.append(raw)
            break

        return "".join(lines)

    def _run_loop(self) -> None:
        while True:
            self._turn_number += 1
            color_fn = self._turn_separator_color()
            print()

            try:
                mode_tag = f"{cyan(self.mode.upper())}" if self.mode == "code" else f"{yellow(self.mode.upper())}"
                wd = self.working_directory.replace(os.environ.get("HOME", "~"), "~") if "HOME" in os.environ else self.working_directory
                line = self._read_multiline(mode_tag, wd)
            except (EOFError, KeyboardInterrupt):
                break

            if not line:
                self._turn_number -= 1
                continue

            stripped = line.strip()
            if stripped.startswith("/"):
                self._turn_number -= 1
                self._handle_command(stripped)
                continue
            if stripped.lower() == "exit":
                self._turn_number -= 1
                break

            # ── Turn header with number ──────────────────────────────────────
            turn_label = f"  {color_fn('─ ')}Turn {self._turn_number}{color_fn(' ' + '─' * (56 - len(str(self._turn_number))))}"
            print(turn_label)

            # ── Process the turn ─────────────────────────────────────────────
            self._process_turn(line, color_fn)

    def _process_turn(self, user_input: str, color_fn: object) -> None:
        """Send a user message to the LLM, stream the response, and show token usage."""

        # ── Plan approval check ────────────────────────────────────────────
        if self._plan_pending_approval and self.mode == "code":
            if self._is_approval(user_input):
                # User approved — unlock write tools
                logger.info("Plan approved by user: plan=%s", self._plan_current_name)
                self._plan_pending_approval = False
                # Keep _first_code_turn_done=True so the execution turn is write-enabled
                self._plan_auto_saved = True  # Suppress auto-save of the upcoming summary response
                # Move plan from pending to completed
                if self._plan_current_name:
                    cplan_name = self._plan_current_name
                    completed = complete_plan(cplan_name, self.working_directory)
                    if completed:
                        print(f"  {green('✓')} {dim('Plan completed:')} {cyan(cplan_name)}")
                    self._plan_current_name = None
                print(f"  {green('✓')} {bold('Plan approved!')} {dim('Write tools are now available.')}")
                print()
            else:
                # User didn't approve — keep read-only mode, this refines the plan
                logger.info("Plan refinement requested (not yet approved): plan=%s", self._plan_current_name)
                pass  # Will use read-only mode below

        messages_before = len(self.messages)
        self.messages.append({"role": "user", "content": user_input})
        system_prompt = self._get_system_prompt()
        current_system_tokens = estimate_tokens(system_prompt)
        trimmed = trim_messages(self.messages, self.max_tokens, current_system_tokens)
        dropped = messages_before - len(trimmed) + 1  # +1 for the just-added message
        if dropped > 0:
            self._show_trim_warning(dropped)
        self.messages = trimmed

        try:
            context = ToolContext(working_directory=self.working_directory)

            thinking_shown = False
            text_started = False
            # Track token usage for this turn
            tokens_before = sum(
                estimate_tokens(str(m.get("content", "")))
                for m in self.messages
            )

            def _on_text(text: str) -> None:
                nonlocal thinking_shown, text_started
                if not thinking_shown:
                    thinking_shown = True
                    # Clear the thinking indicator line
                    print("\r" + " " * 70, end="", flush=True)
                    print("\r", end="", flush=True)
                if not text_started:
                    text_started = True
                    # Show streaming prefix
                    color_fn = self._turn_separator_color()
                    print(f"  {color_fn('┃')} ", end="", flush=True)
                print(text, end="", flush=True)

            # Show thinking indicator
            print(f"  {dim('⟳ thinking...')}", end="", flush=True)

            # Determine read-only status:
            # - Plan mode is always read-only
            # - First code-mode turn forces read-only (plan-first)
            # - Pending approval keeps read-only
            is_read_only = (
                self.mode == "plan"
                or (self.mode == "code" and not self._first_code_turn_done)
                or self._plan_pending_approval
            )

            self.llm.chat_with_tools(
                messages=self.messages,
                system=system_prompt,
                tools=self.tools,
                context=context,
                on_text=_on_text,
                on_tool_call=self._on_tool_call,
                on_tool_result=lambda _name, r: self._on_tool_result(r),
                read_only=is_read_only,
            )

            # If we never got text, clear thinking indicator
            if not thinking_shown:
                print("\r" + " " * 70, end="", flush=True)
                print("\r", end="", flush=True)

            # ── Post-turn plan enforcement (code mode) ──────────────────────
            if self.mode == "code" and self._plan_auto_saved:
                # Just finished an approved execution turn — reset for next plan-first cycle
                logger.info("Execution turn completed, resetting plan-first cycle")
                self._plan_auto_saved = False
                self._first_code_turn_done = False
            elif self.mode == "code" and not self._first_code_turn_done and not self._plan_pending_approval:
                self._first_code_turn_done = True
                self._plan_pending_approval = True
                logger.info("First code turn completed, entering plan review phase")

                # Auto-save the assistant response as a plan
                plan_text = self._get_last_assistant_text()
                if plan_text:
                    # Generate a unique plan name from the first line or a timestamp
                    first_line = plan_text.strip().split("\n")[0][:50]
                    plan_name = _plan_name_from_text(first_line)
                    try:
                        fpath = save_pending_plan(plan_name, plan_text, self.working_directory)
                        self._plan_current_name = plan_name
                        logger.info("Plan auto-saved: %s -> %s", plan_name, fpath)
                        print(f"\n  {dim('📋 Plan auto-saved to')} {cyan(fpath)}")
                    except Exception as exc:
                        logger.error("Failed to auto-save plan: %s", exc)
                        print(f"\n  {dim(f'⚠ Could not auto-save plan: {exc}')}")

                # Show approval prompt
                print(f"\n  {yellow('●')} {bold('Plan is ready for review.')}")
                print(f"  {dim('Type')} {green('proceed')} {dim('to approve and execute, or keep refining the plan.')}")
            elif self.mode == "code" and self._plan_pending_approval and self._first_code_turn_done:
                # Plan was refined (user didn't approve) — re-save and re-prompt
                plan_text = self._get_last_assistant_text()
                if plan_text and self._plan_current_name:
                    try:
                        fpath = save_pending_plan(self._plan_current_name, plan_text, self.working_directory)
                        logger.info("Plan updated: %s -> %s", self._plan_current_name, fpath)
                        print(f"\n  {dim('📋 Plan updated:')} {cyan(fpath)}")
                    except Exception as exc:
                        logger.error("Failed to update plan: %s", exc)
                        print(f"\n  {dim(f'⚠ Could not update plan: {exc}')}")

                # Show approval prompt again
                print(f"\n  {yellow('●')} {bold('Updated plan is ready for review.')}")
                print(f"  {dim('Type')} {green('proceed')} {dim('to approve and execute, or keep refining the plan.')}")

            # ── Show token usage for this turn ──────────────────────────────
            tokens_after = sum(
                estimate_tokens(str(m.get("content", "")))
                for m in self.messages
            )
            turn_tokens = tokens_after - tokens_before
            # Track cumulative costs (estimated: split 50/50 in/out for simplicity)
            estimated_input = turn_tokens // 2
            estimated_output = turn_tokens - estimated_input
            self._input_tokens_total += estimated_input
            self._output_tokens_total += estimated_output
            print(f"  {dim(f'┄ {turn_tokens} tokens used this turn')}")

        except Exception as exc:
            print(f"\n  {red('✗ Error:')} {exc}")
        print()

    def _show_trim_warning(self, dropped: int) -> None:
        """Display a warning when messages have been trimmed."""
        label = "message" if dropped == 1 else "messages"
        print(f"  {yellow('⚠')} {dim(f'{dropped} earlier {label} removed to stay within context limits.')}")

    def _get_system_prompt(self) -> str:
        base = PLAN_MODE_SYSTEM_PROMPT if self.mode == "plan" else self.system_prompt
        persona = f"\n\n{self._custom_persona}" if self._custom_persona else ""

        # ── Load coding-agent.md instructions (if present) ─────────────────
        coding_agent_rules = ""
        coding_agent_path = os.path.join(self.working_directory, "coding-agent.md")
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

        # Phase-specific instructions
        phase_instruction = ""
        if self._plan_pending_approval and self.mode == "code":
            phase_instruction = (
                "\n\n## IMPORTANT: You are in the PLAN REVIEW phase\n"
                "The user has NOT yet approved your plan. You can ONLY use read-only tools "
                "(directory_tree, list_directory, read_file, grep, file_search, think, url_fetch, web_search).\n"
                "Write tools (write_file, edit_file, replace_in_files, bash, run_tests, git_commit) are BLOCKED.\n"
                "If the user is asking you to refine or clarify the plan, do so using only read-only tools.\n"
                "If the user approves your plan (says 'proceed', 'go ahead', 'approved', etc.), "
                "you may then use write tools to implement the plan."
            )

        return (
            f"Current working directory: {self.working_directory}\n"
            f"Project root: {self.working_directory}\n\n"
            f"{base}\n\n"
            f"Remember: Always plan before you act. Explore the codebase, reason with the think tool, "
            f"present your plan, and only then execute changes."
            f"{persona}"
            f"{coding_agent_rules}"
            f"{phase_instruction}"
        )

    def _on_tool_call(self, name: str, args: dict[str, object]) -> None:
        args_str = color_json(args)
        color_fn = self._turn_separator_color()
        print(f"\n  {cyan('⚡')} {bold(name)}")
        # Only show args if they're non-trivial, to keep display clean
        if len(str(args)) > 4:  # more than just "{}"
            print(f"  {color_fn('│')}   {args_str}")

    def _on_tool_result(self, result: str) -> None:
        is_error = result.startswith("Error:")
        truncated = len(result) > 250
        preview = result if not truncated else result[:250]
        suffix = ""
        if truncated:
            suffix = f" {dim(f'[+{len(result) - 250} more chars]')}"
        if is_error:
            print(f"  {red('✗')} {red(preview)}{suffix}")
        else:
            print(f"  {green('✓')} {dim(preview)}{suffix}")

    def _handle_plan_save(self, cmd: str) -> None:
        parts = cmd.split(maxsplit=2)
        if len(parts) < 3:
            print(f"  {dim('Usage: /plan save <name>')}")
            return

        name = parts[2].strip()
        if not name:
            print(f"  {dim('Usage: /plan save <name>')}")
            return

        text = self._get_last_assistant_text()
        if not text:
            print(f"  {dim('No assistant response to save. Send a message first.')}")
            return

        try:
            filepath = save_pending_plan(name, text, self.working_directory)
            print(f"  {green('✓')} {dim('Plan saved to')} {cyan(filepath)}")
        except Exception as exc:
            print(f"  {red('✗ Error saving plan:')} {exc}")

    def _handle_plan_create(self, parts: list[str]) -> None:
        """Handle /plan create <topic> — generate a structured plan template."""
        topic_parts = parts[1:] if len(parts) > 1 else []
        if not topic_parts:
            print(f"  {dim('Usage: /plan create <topic description>')}")
            print(f"  {dim('Example: /plan create Add user authentication')}")
            return

        topic = " ".join(topic_parts)
        template = generate_plan_template(topic)

        # Save the template as a pending plan
        safe_name = _plan_name_from_text(topic)
        try:
            filepath = save_pending_plan(safe_name, template, self.working_directory)
            print(f"  {green('✓')} {bold('Plan template created:')} {cyan(filepath)}")
            print(f"  {dim('You can now edit it or ask the agent to follow this plan.')}")
        except Exception as exc:
            print(f"  {red('✗ Error creating plan:')} {exc}")

    def _handle_plan_list(self, subcommand: str = "") -> None:
        """Handle /plan list and /plan list completed."""
        show_completed = subcommand == "completed"
        if show_completed:
            plans = list_completed_plans(self.working_directory)
            title = "Completed Plans"
        else:
            plans = list_pending_plans(self.working_directory)
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

    def _get_last_assistant_text(self) -> str:
        for msg in reversed(self.messages):
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

    def _get_last_user_index(self) -> int | None:
        """Return the index of the last user message, or None."""
        for i in range(len(self.messages) - 1, -1, -1):
            if self.messages[i].get("role") == "user":
                content = self.messages[i].get("content", "")
                if isinstance(content, str):
                    return i
        return None

    def _handle_edit(self) -> None:
        """Edit the last user message and re-send it."""
        idx = self._get_last_user_index()
        if idx is None:
            print(f"  {dim('No previous user message to edit.')}")
            return

        old_content = cast("str", self.messages[idx].get("content", ""))
        print(f"  {dim('Previous message:')}")
        print(f"  {dim('│')} {old_content[:200]}")
        if len(old_content) > 200:
            print(f"  {dim(f'└ [+{len(old_content) - 200} more chars]')}")
        print()

        try:
            mode_tag = f"{cyan(self.mode.upper())}" if self.mode == "code" else f"{yellow(self.mode.upper())}"
            wd = self.working_directory.replace(os.environ.get("HOME", "~"), "~") if "HOME" in os.environ else self.working_directory
            prompt = f"  {bold(mode_tag)} {cyan(wd)} {green('❯')} "
            new_line = input(prompt)
        except (EOFError, KeyboardInterrupt):
            print()
            print(f"  {dim('Edit cancelled.')}")
            return

        new_line = new_line.strip()
        if not new_line:
            print(f"  {dim('Edit cancelled (empty input).')}")
            return

        # Replace the content
        self.messages[idx]["content"] = new_line
        # Remove everything after the edited message (tool results, assistant responses)
        self.messages = self.messages[: idx + 1]

        print(f"  {dim('Message updated. Re-processing...')}")
        print()
        color_fn = self._turn_separator_color()
        turn_label = f"  {color_fn('─ ')}Turn {self._turn_number}{color_fn(' ' + '─' * (56 - len(str(self._turn_number))))}"
        print(turn_label)
        self._process_turn(new_line, color_fn)

    def _handle_retry(self) -> None:
        """Re-send the last user message (same content)."""
        idx = self._get_last_user_index()
        if idx is None:
            print(f"  {dim('No previous user message to retry.')}")
            return

        content = cast("str", self.messages[idx].get("content", ""))
        # Remove everything after the last user message
        self.messages = self.messages[: idx + 1]

        print(f"  {dim('Retrying last message...')}")
        print()
        color_fn = self._turn_separator_color()
        turn_label = f"  {color_fn('─ ')}Turn {self._turn_number}{color_fn(' ' + '─' * (56 - len(str(self._turn_number))))}"
        print(turn_label)
        self._process_turn(content, color_fn)

    def _handle_reload(self) -> None:
        """Re-discover and re-register all tools from disk."""
        print(f"  {dim('⟳ Reloading tools...')}", end="", flush=True)
        try:
            count = self.tools.rebuild()
            print(f"\r  {green('✓')} {dim(f'Reloaded {count} tools.')}")
            # Show the freshly loaded tools
            for t in self.tools.get_all():
                ro = f" {dim('(read-only)')}" if t.read_only else ""
                print(f"    {bold(t.name)}{dim(f' — {t.description}')}{ro}")
        except Exception as exc:
            print(f"\r  {red('✗ Error reloading tools:')} {exc}")

    # ── New feature handlers ────────────────────────────────────────────

    def _estimated_cost(self) -> float:
        """Return estimated total API cost in USD."""
        pricing = MODEL_PRICING.get(self.llm.model, {"input": 0.50, "output": 0.50})
        in_cost = (self._input_tokens_total / 1_000_000) * pricing["input"]
        out_cost = (self._output_tokens_total / 1_000_000) * pricing["output"]
        return in_cost + out_cost

    def _handle_cost(self) -> None:
        """Show detailed cost breakdown."""
        system_prompt = self._get_system_prompt()
        system_tokens = estimate_tokens(system_prompt)

        pricing = MODEL_PRICING.get(self.llm.model, {"input": 0.50, "output": 0.50})
        in_cost = (self._input_tokens_total / 1_000_000) * pricing["input"]
        out_cost = (self._output_tokens_total / 1_000_000) * pricing["output"]
        total_cost = in_cost + out_cost

        print(f"  {bold('Cost Breakdown')}")
        print(f"  {dim('Model:')}    {cyan(self.llm.model)}")
        print(f"  {dim('Pricing:')}  {dim(f'${pricing["input"]}/1M in, ${pricing["output"]}/1M out')}")
        print()
        print(f"  {dim('Input tokens:')}  {self._input_tokens_total}")
        print(f"  {dim('Output tokens:')} {self._output_tokens_total}")
        print(f"  {dim('System tokens:')} {system_tokens}")
        print()
        print(f"  {dim('Input cost:')}   ${in_cost:.6f}")
        print(f"  {dim('Output cost:')}  ${out_cost:.6f}")
        print(f"  {bold(f'Total cost:')}  {bold(f'${total_cost:.4f}')}")
        print()
        print(f"  {dim('Note: Cost estimates use per-model pricing. Update MODEL_PRICING')}")
        print(f"  {dim('in repl.py if you use a different model or have custom pricing.')}")

    def _handle_config(self) -> None:
        """Show current configuration."""
        print(f"  {bold('Configuration')}")
        print(f"  {dim('Model:')}       {cyan(self.llm.model)}")
        print(f"  {dim('Max tokens:')}  {cyan(str(self.max_tokens))}")
        print(f"  {dim('Temperature:')} {cyan(str(self.llm.temperature))}")
        print(f"  {dim('Top-p:')}       {cyan(str(self.llm.top_p))}")
        print(f"  {dim('Base URL:')}    {dim(str(self.llm.client.base_url))}")
        if self._custom_persona:
            print(f"  {dim('Persona:')}     {cyan(self._custom_persona)}")
        else:
            print(f"  {dim('Persona:')}     {dim('(none)')}")

    def _handle_session_save(self, parts: list[str]) -> None:
        """Save the current session."""
        if len(parts) < 2:
            print(f"  {dim('Usage: /save <name>')}")
            return
        name = parts[1].strip()
        if not name:
            print(f"  {dim('Usage: /save <name>')}")
            return

        result = save_session(
            name=name,
            messages=self.messages,
            mode=self.mode,
            working_directory=self.working_directory,
            model=self.llm.model,
        )
        if result.startswith("Error:"):
            logger.warning("Session save failed: %s", result)
            print(f"  {red('✗')} {result}")
        else:
            logger.info("Session saved: %s -> %s", name, result)
            print(f"  {green('✓')} {dim('Session saved to')} {cyan(result)}")

    def _handle_session_load(self, parts: list[str]) -> None:
        """Load a saved session."""
        if len(parts) < 2:
            print(f"  {dim('Usage: /load <name>')}")
            return
        name = parts[1].strip()
        if not name:
            print(f"  {dim('Usage: /load <name>')}")
            return

        session = load_session(name, self.working_directory)
        if session is None:
            print(f"  {red('✗')} {dim('Session not found:')} {cyan(name)}")
            print(f"  {dim('Use /sessions to list available sessions.')}")
            return

        loaded_msgs = session.get("messages", [])
        if isinstance(loaded_msgs, list):
            self.messages = cast("list[dict[str, object]]", loaded_msgs)
        loaded_mode = session.get("mode", "code")
        if isinstance(loaded_mode, str):
            self.mode = loaded_mode

        msg_count = len(self.messages)
        logger.info("Session loaded: %s (%d messages, %s mode)", name, msg_count, loaded_mode)
        print(f"  {green('✓')} {dim('Loaded session:')} {cyan(name)} {dim(f'({msg_count} messages, {loaded_mode} mode)')}")

    def _handle_session_list(self) -> None:
        """List all saved sessions."""
        sessions = list_sessions(self.working_directory)
        if not sessions:
            print(f"  {dim('No saved sessions found.')}")
            print(f"  {dim('Use /save <name> to save the current session.')}")
            return

        print(f"  {bold('Saved Sessions')}")
        print()
        for s in sessions:
            name = cast("str", s.get("name", "?"))
            saved_at = cast("str", s.get("saved_at", "?"))
            mode = cast("str", s.get("mode", "?"))
            msg_count = cast("int", s.get("message_count", 0))
            # Truncate ISO timestamp for display
            display_time = saved_at[:19] if len(saved_at) > 19 else saved_at
            print(f"  {cyan(name.rjust(20))}  {dim(display_time)}  {dim(f'({msg_count} msgs, {mode})')}")

    def _handle_persona(self, parts: list[str]) -> None:
        """Set or clear the custom persona."""
        if len(parts) < 2:
            print(f"  {dim('Usage: /persona <text>')}")
            print(f"  {dim('       /persona clear')}")
            return

        text = parts[1].strip()
        if text.lower() == "clear":
            if self._custom_persona:
                self._custom_persona = ""
                print(f"  {green('✓')} {dim('Custom persona cleared.')}")
            else:
                print(f"  {dim('No custom persona to clear.')}")
            return

        if not text:
            print(f"  {dim('Usage: /persona <text>')}")
            return

        self._custom_persona = text
        logger.info("Custom persona set (length=%d)", len(text))
        print(f"  {green('✓')} {dim('Custom persona set. It will be appended to the system prompt for all future turns.')}")

    def _handle_command(self, cmd: str) -> None:
        parts = cmd.lower().split(maxsplit=1)
        match parts[0]:
            case "/help" | "/h":
                print(HELP_TEXT)
            case "/clear" | "/c":
                self.messages.clear()
                print(f"  {dim('Conversation history cleared.')}")
            case "/tools":
                tools_to_show = self.tools.get_read_only() if self.mode == "plan" else self.tools.get_all()
                for t in tools_to_show:
                    print(f"  {bold(t.name)}{dim(f' — {t.description}')}")
                print(f"  {dim(f'[{self.mode.upper()} mode — {len(tools_to_show)} tools available]')}")
            case "/reload":
                self._handle_reload()
            case "/history":
                count = len(self.messages)
                user_msgs = sum(1 for m in self.messages if m.get("role") == "user")
                asst_msgs = sum(1 for m in self.messages if m.get("role") == "assistant")
                tool_calls = sum(
                    1 for m in self.messages
                    if isinstance(m.get("content"), list)
                )
                total_tokens = 0
                print(f"  {bold('History')}  {dim(f'({count} messages)')}")
                print()
                # Show conversation flow
                for i, m in enumerate(self.messages):
                    role = cast("str", m.get("role", "unknown"))
                    content = m.get("content", "")
                    tokens = 0
                    preview = ""

                    if isinstance(content, str):
                        tokens = estimate_tokens(content)
                        preview = content[:80].replace("\n", " ")
                    elif isinstance(content, list):
                        blocks = cast("list[dict[str, object]]", content)
                        texts_parts: list[str] = []
                        has_tool_result = False
                        has_tool_use = False
                        for b in blocks:
                            t = b.get("text", "")
                            if isinstance(t, str):
                                texts_parts.append(t)
                                tokens += estimate_tokens(t)
                            c = b.get("content", "")
                            if isinstance(c, str):
                                tokens += estimate_tokens(c)
                            if b.get("type") == "tool_result":
                                has_tool_result = True
                            if b.get("type") == "tool_use":
                                has_tool_use = True
                        if has_tool_result:
                            preview = f"[tool results: {sum(1 for b in blocks if b.get('type') == 'tool_result')} blocks]"
                        elif has_tool_use:
                            preview = f"[tool calls: {sum(1 for b in blocks if b.get('type') == 'tool_use')} tools]"
                        else:
                            preview = texts_parts[0][:80].replace("\n", " ") if texts_parts else "[content]"

                    role_color = {
                        "user": green,
                        "assistant": cyan,
                    }.get(role, dim)
                    arrow = "→" if role == "user" else "←"
                    print(f"  {dim(str(i+1).rjust(3))} {role_color(arrow)} {bold(role_color(role.title()))}"
                          f" {dim(f'~{tokens}tok')}  {dim(preview)}")

                print()
                print(f"  {dim('Summary:')}    {count} messages ({green(str(user_msgs))} user, {cyan(str(asst_msgs))} assistant, {yellow(str(tool_calls))} tool blocks)")
                print(f"  {dim('Tokens:')}     ~{total_tokens} estimated")
            case "/status" | "/s":
                system_prompt = self._get_system_prompt()
                system_tokens = estimate_tokens(system_prompt)
                msg_count = len(self.messages)
                total_tokens = sum(
                    estimate_tokens(str(m.get("content", "")))
                    for m in self.messages
                )
                elapsed = time.time() - self._start_time
                hours, remainder = divmod(int(elapsed), 3600)
                minutes, seconds = divmod(remainder, 60)
                uptime_str = f"{hours}h {minutes}m {seconds}s" if hours else f"{minutes}m {seconds}s"
                print(f"  {bold('Status')}")
                print(f"  {dim('Mode:')}      {cyan(self.mode.upper())}")
                print(f"  {dim('Model:')}     {cyan(self.llm.model)}")
                print(f"  {dim('Max tokens:')} {cyan(str(self.max_tokens))}")
                print(f"  {dim('Messages:')}  {msg_count}")
                print(f"  {dim('Tokens:')}   ~{total_tokens + system_tokens} total (~{system_tokens} system)")
                print(f"  {dim('Uptime:')}   {cyan(uptime_str)}")
                print(f"  {dim('WD:')}       {dim(self.working_directory)}")
                if self._custom_persona:
                    print(f"  {dim('Persona:')}  {cyan(self._custom_persona)}")
                print(f"  {dim('Cost:')}    {dim(f'${self._estimated_cost():.4f} estimated (in: {self._input_tokens_total}, out: {self._output_tokens_total})')}")
            case "/plan" | "/p":
                # Check for subcommands first
                full_cmd = cmd.lower().strip()
                if full_cmd.startswith("/plan save"):
                    self._handle_plan_save(cmd)
                elif full_cmd.startswith("/plan create"):
                    parts_create = cmd.split(maxsplit=2)
                    self._handle_plan_create(parts_create)
                elif full_cmd.startswith("/plan list"):
                    parts_list = cmd.split(maxsplit=2)
                    sub = parts_list[2].strip() if len(parts_list) > 2 else ""
                    self._handle_plan_list(sub)
                elif full_cmd == "/plan" or full_cmd == "/p":
                    if self.mode == "plan":
                        print(f"  {dim('Already in plan mode.')}")
                    else:
                        self.mode = "plan"
                        logger.info("Switched to PLAN mode")
                        print(f"  {yellow('●')} {bold('PLAN mode')} {dim('— read-only exploration. Only read-only tools are available.')}")
                        print(f"  {dim('Use /code to switch back to CODE mode.')}")
                else:
                    print(f"  {dim('Unknown plan command. Usage:')}")
                    print(f"  {dim('  /plan              — switch to plan mode')}")
                    print(f"  {dim('  /plan save <name>  — save last response as plan')}")
                    print(f"  {dim('  /plan create <topic> — create a structured plan template')}")
                    print(f"  {dim('  /plan list         — list pending plans')}")
                    print(f"  {dim('  /plan list completed — list completed plans')}")
            case "/code":
                if self.mode == "code":
                    print(f"  {dim('Already in code mode.')}")
                else:
                    self.mode = "code"
                    logger.info("Switched to CODE mode")
                    print(f"  {green('●')} {bold('CODE mode')} {dim('— all tools available (read, write, execute).')}")
                    print(f"  {dim('Use /plan to switch to PLAN mode.')}")
            case "/mode":
                logger.info("Mode check: current mode=%s", self.mode)
                print(f"  {bold('Mode:')} {bold(self.mode.upper())}")
            case "/edit":
                self._handle_edit()
            case "/retry" | "/r":
                self._handle_retry()
            case "/cost":
                self._handle_cost()
            case "/config":
                self._handle_config()
            case "/save":
                self._handle_session_save(parts)
            case "/load":
                self._handle_session_load(parts)
            case "/sessions":
                self._handle_session_list()
            case "/persona":
                self._handle_persona(parts)
            case "/restart":
                self.messages.clear()
                self._first_code_turn_done = False
                self._plan_pending_approval = False
                self._plan_current_name = None
                self._plan_auto_saved = False
                self._turn_number = 0
                logger.info("Session restarted (messages cleared, plan cycle reset)")
                print(f"  {green('✓')} {bold('Restarted.')} {dim('Session reset to turn 1 (plan-first cycle).')}")
            case "/q":
                print(f"  {dim('Exiting...')}")
                # Trigger clean exit
                raise EOFError()
            case _:
                print(f"  {dim(f'Unknown command: {parts[0]}. Type /help for available commands.')}")
