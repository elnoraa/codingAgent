"""Core REPL class — the Coding Agent's interactive command-loop.

This module defines the ``Repl`` class, which manages the interactive
session: user input, LLM communication, tool orchestration, and state
management. Command handlers and tool runners are in sibling modules.
"""

from __future__ import annotations

import json
import os
import time
from typing import TYPE_CHECKING, Any, cast

from src.client import LlmClient
from src.formatting import Spinner, bold, cyan, dim, green, magenta, red, yellow
from src.logging_config import get_logger
from src.tool_base import ToolContext, ToolRegistry, record_session_start
from src.utils import estimate_tokens, trim_messages

if TYPE_CHECKING:
    from src.python_repl import PythonRepl

logger = get_logger(__name__)


def turn_separator_color(repl: Repl) -> Any:
    """Return the color function for the current mode's separator."""
    if repl.mode == "plan":
        return yellow
    if repl.mode == "ask":
        return magenta
    return dim


def print_separator(repl: Repl) -> None:
    """Print a mode-aware separator line."""
    color_fn = turn_separator_color(repl)
    print(f"  {color_fn('─' * 60)}")


class Repl:
    """The main interactive REPL loop for the Coding Agent."""

    def __init__(
        self,
        llm: LlmClient,
        system_prompt: str,
        max_tokens: int,
        custom_persona: str = "",
        auto_save_interval: int = 0,
        context_files: list[str] | None = None,
        custom_tools_config: str | None = None,
        notifications_enabled: bool = False,
        notifications_min_duration: int = 10,
        mcp_servers: list[dict[str, object]] | None = None,
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
        self._auto_save_interval = auto_save_interval
        self._file_snapshots: dict[str, list[tuple[str, str]]] = {}
        self._change_log: list[dict[str, object]] = []
        self._context_files = context_files or []
        self._custom_tools_config = custom_tools_config
        self._python_repl: PythonRepl | None = None
        self._import_graph = None
        self._notifications_enabled = notifications_enabled
        self._notifications_min_duration = notifications_min_duration
        self._tool_start_time: float = 0.0
        self._tool_usage: dict[str, int] = {}
        self._tool_durations: dict[str, list[float]] = {}
        self._tool_errors: dict[str, int] = {}
        self._mode_switches: int = 0
        self._spinner: Spinner | None = None
        self._turns_by_mode: dict[str, int] = {"code": 0, "plan": 0, "ask": 0}

        # Cost tracking
        self._input_tokens_total = 0
        self._output_tokens_total = 0

        # Task tracking for resilience
        self._current_task: str = ""
        self._task_attempts: int = 0
        self._max_task_attempts: int = 3
        self._recovery_mode: bool = False
        self._tool_execution_timeout: int = 120
        self._consecutive_tool_failures: int = 0
        self._last_mode: str = "code"
        self._mode_changed_via_command: bool = False

        # MCP bridge
        self._mcp_bridge: Any = None
        self._mcp_servers_config: list[dict[str, object]] = mcp_servers or []

        # Rate limit tracking
        self._rate_limit_events: int = 0
        self._pending_input: str | None = None
        self._confirm_edits: bool = False

        # Token budget
        self._token_budget: int | None = None
        self._token_budget_warning: float = 0.8
        self._token_budget_hard_limit: float = 1.0
        self._token_budget_exceeded: bool = False
        self._total_tokens_used: int = 0

        # Summarization
        self._enable_summarization: bool = False

        # File watcher
        self._file_watcher: Any = None

        # RAG index (lazily initialized)
        self._rag_index: Any = None

        # Branch manager
        self._branch_manager: Any = None

        # Per-turn latency timeline
        self._turn_timeline: list[dict[str, object]] = []
        self._current_turn_tools: list[dict[str, object]] = []
        self._current_llm_start: float = 0.0
        self._turn_start_time: float = 0.0

        # Record session start for file-tamper detection
        record_session_start()

        self.tools = ToolRegistry()
        self._register_all_tools()
        self._auto_save_interval = auto_save_interval
        self._turns_since_auto_save = 0
        self._last_auto_save_path: str | None = None

        # Initialize the import graph
        from src.dep_analyzer import ImportGraph

        self._import_graph = ImportGraph()

        # Initialize the agent orchestrator for multi-agent support
        from src.orchestrator import Orchestrator
        from src.repl.system_prompt import build_orchestrator_system_prompt

        self._orchestrator = Orchestrator(
            default_llm=self.llm,
            default_system_prompt=build_orchestrator_system_prompt(self),
            default_working_directory=self.working_directory,
        )

        logger.info(
            "REPL initialized: mode=%s, model=%s, max_tokens=%d, persona=%s",
            self.mode,
            self.llm.model,
            self.max_tokens,
            bool(self._custom_persona),
        )

    def _register_all_tools(self) -> None:
        """Register all available tools into the registry."""
        from src.tools.api_tool import api_tool
        from src.tools.ask_user import ask_user_tool
        from src.tools.bash_tool import bash_tool
        from src.tools.ci_tool import ci_tool
        from src.tools.complete_plan import complete_plan_tool
        from src.tools.config_tool import config_tool
        from src.tools.db_tool import db_tool
        from src.tools.diff_tool import diff_tool
        from src.tools.directory_tree import directory_tree_tool
        from src.tools.docker_tool import docker_tool
        from src.tools.edit_file import edit_file_tool
        from src.tools.edit_plan import edit_plan_tool
        from src.tools.environment import environment_tool
        from src.tools.file_search import file_search_tool
        from src.tools.git_branch import git_branch_tool
        from src.tools.git_commit import git_commit_tool
        from src.tools.git_log import git_log_tool
        from src.tools.git_push import git_push_tool
        from src.tools.git_revert import git_revert_tool
        from src.tools.git_status import git_status_tool
        from src.tools.glob_tool import glob_tool
        from src.tools.grep_tool import grep_tool
        from src.tools.list_agents import list_agents_tool
        from src.tools.list_directory import list_directory_tool
        from src.tools.precommit_tool import precommit_tool
        from src.tools.python_tool import python_tool
        from src.tools.read_file import read_file_tool
        from src.tools.rename_file import rename_file_tool
        from src.tools.replace_in_files import replace_in_files_tool
        from src.tools.restart_session import restart_session_tool
        from src.tools.run_swarm import run_swarm_tool
        from src.tools.run_tests import run_tests_tool
        from src.tools.send_to_agent import send_to_agent_tool
        from src.tools.spawn_agent import spawn_agent_tool
        from src.tools.syntax_check import syntax_check_tool
        from src.tools.terminate_agent import terminate_agent_tool
        from src.tools.think_tool import think_tool
        from src.tools.undo_tool import undo_tool
        from src.tools.url_fetch import url_fetch_tool
        from src.tools.verify_content import verify_content_tool
        from src.tools.web_search import web_search_tool
        from src.tools.write_file import write_file_tool
        from src.tools.write_plan import write_plan_tool

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
        self.tools.register(restart_session_tool)
        self.tools.register(think_tool)
        self.tools.register(web_search_tool)
        self.tools.register(undo_tool)
        self.tools.register(python_tool)
        self.tools.register(write_plan_tool)
        self.tools.register(complete_plan_tool)
        self.tools.register(edit_plan_tool)
        self.tools.register(ask_user_tool)
        self.tools.register(syntax_check_tool)
        self.tools.register(verify_content_tool)
        self.tools.register(config_tool)
        self.tools.register(git_log_tool)
        self.tools.register(environment_tool)
        self.tools.register(spawn_agent_tool)
        self.tools.register(list_agents_tool)
        self.tools.register(send_to_agent_tool)
        self.tools.register(terminate_agent_tool)
        self.tools.register(run_swarm_tool)
        self.tools.register(git_revert_tool)
        self.tools.register(rename_file_tool)
        self.tools.register(git_branch_tool)
        self.tools.register(api_tool)
        self.tools.register(precommit_tool)
        self.tools.register(ci_tool)
        self.tools.register(db_tool)
        self.tools.register(docker_tool)

        # Register RAG tools
        from src.tools.rag_index import rag_index_tool
        from src.tools.rag_query import rag_query_tool
        from src.tools.rag_status import rag_status_tool

        self.tools.register(rag_index_tool)
        self.tools.register(rag_query_tool)
        self.tools.register(rag_status_tool)

        # Load custom tools from config
        if self._custom_tools_config:
            from src.custom_tools import load_custom_tools

            custom_tools = load_custom_tools(self._custom_tools_config, self.working_directory)
            for ct in custom_tools:
                self.tools.register(ct)
            if custom_tools:
                logger.info("Registered %d custom tool(s)", len(custom_tools))

        # Load MCP tools from configured servers
        if self._mcp_servers_config:
            from src.mcp_bridge import MCPBridge

            try:
                self._mcp_bridge = MCPBridge(self._mcp_servers_config)
                mcp_tools = self._mcp_bridge.start()
                for t in mcp_tools:
                    self.tools.register(t)
                if mcp_tools:
                    logger.info(
                        "Registered %d MCP tool(s) from %d server(s)",
                        len(mcp_tools),
                        len(self._mcp_bridge.get_server_info()),
                    )
            except Exception as exc:
                logger.error("Failed to initialize MCP bridge: %s", exc)
                print(f"  {yellow('⚠')} {dim(f'MCP initialization failed: {exc}')}")

    def start(self) -> None:
        """Start the REPL loop."""
        from src.repl.ui import _readline_available, setup_tab_completion

        print()
        print(f"  {bold('Coding Agent')} {dim('v0.6')}")
        print(f"  {dim('Type /help for commands, exit to quit.')}")
        print(f"  {dim('Model:')} {cyan(self.llm.model)}")
        print(f"  {dim('History:')} {cyan('enabled' if _readline_available else 'unavailable')} (up/down arrows)")
        print()
        print_separator(self)
        print()

        # Show MCP connection status
        if self._mcp_bridge and self._mcp_bridge.is_any_connected:
            for info in self._mcp_bridge.get_server_info():
                status = f"{green('● connected')}" if info["connected"] else f"{red('● disconnected')}"
                tool_count: int = int(info["tool_count"])  # type: ignore[arg-type]
                mcp_name: str = str(info["name"])
                print(f"  {dim('MCP:')} {cyan(mcp_name)} {status} {dim(f'({tool_count} tools)')}")
        print()

        setup_tab_completion(self)
        try:
            self._run_loop()
        except EOFError:
            print()
        except KeyboardInterrupt:
            print("\nExiting...")
        finally:
            # Always auto-save on exit
            if self._auto_save_interval > 0 and self._last_auto_save_path is not None:
                import contextlib

                with contextlib.suppress(Exception):
                    from src.session import save_session

                    path = save_session(
                        name=f"autosave-exit-{int(time.time())}",
                        messages=self.messages,
                        mode=self.mode,
                        working_directory=self.working_directory,
                        model=self.llm.model,
                        is_autosave=True,
                    )
                    print(f"  {dim('Auto-saved session:')} {cyan(path)}")

            # Disconnect MCP servers on exit
            if self._mcp_bridge is not None:
                import contextlib

                with contextlib.suppress(Exception):
                    self._mcp_bridge.disconnect_all()

    def _auto_save(self) -> None:
        """Auto-save the session if the interval has been reached."""
        from src.session import save_session

        if self._auto_save_interval <= 0:
            return
        self._turns_since_auto_save += 1
        if self._turns_since_auto_save < self._auto_save_interval:
            return
        self._turns_since_auto_save = 0
        try:
            path = save_session(
                name=f"autosave-{int(time.time())}",
                messages=self.messages,
                mode=self.mode,
                working_directory=self.working_directory,
                model=self.llm.model,
                is_autosave=True,
            )
            self._last_auto_save_path = path
            logger.info("Auto-saved session: %s", path)
        except Exception as exc:
            logger.warning("Auto-save failed: %s", exc)

    def _run_loop(self) -> None:
        """Main REPL loop — reads input, dispatches commands, processes turns."""
        from src.repl.ui import read_multiline

        while True:
            self._turn_number += 1
            color_fn = turn_separator_color(self)
            print()

            # ── Mode-change announcement (only for non-command mode changes) ─
            if self.mode != self._last_mode and not self._mode_changed_via_command:
                old_mode = self._last_mode.upper()
                new_mode = self.mode.upper()
                mode_dot = {
                    "code": green("●"),
                    "plan": yellow("●"),
                    "ask": magenta("●"),
                }.get(self.mode, "●")
                print(f"  {mode_dot} {bold(f'{new_mode} mode')} {dim(f'(previously: {old_mode})')}")
                print()
            self._last_mode = self.mode
            self._mode_changed_via_command = False

            try:
                mode_tag = (
                    f"{magenta(self.mode.upper())}"
                    if self.mode == "ask"
                    else f"{yellow(self.mode.upper())}"
                    if self.mode == "plan"
                    else f"{cyan(self.mode.upper())}"
                )
                wd = (
                    self.working_directory.replace(os.environ.get("HOME", "~"), "~")
                    if "HOME" in os.environ
                    else self.working_directory
                )
                line = read_multiline(self, mode_tag, wd)
            except EOFError, KeyboardInterrupt:
                break

            if not line:
                self._turn_number -= 1
                continue

            stripped = line.strip()
            if stripped.startswith("/"):
                self._turn_number -= 1
                from src.repl.commands import dispatch

                dispatch(self, stripped)
                continue
            if stripped.lower() == "exit":
                self._turn_number -= 1
                break

            # ── Turn header with number ──────────────────────────────────────
            turn_label = (
                f"  {color_fn('─ ')}Turn {self._turn_number}{color_fn(' ' + '─' * (56 - len(str(self._turn_number))))}"
            )
            print(turn_label)

            # ── Process the turn ─────────────────────────────────────────────
            self._process_turn(line, color_fn)

    def _turn_separator_color(self) -> Any:
        """Return the color function for the current mode's separator."""
        return turn_separator_color(self)

    def _show_trim_warning(self, dropped: int) -> None:
        """Display a warning when messages have been trimmed."""
        label = "message" if dropped == 1 else "messages"
        print(f"  {yellow('⚠')} {dim(f'{dropped} earlier {label} removed to stay within context limits.')}")

    def _get_system_prompt(self) -> str:
        """Build the system prompt for the current mode."""
        from src.repl.system_prompt import build_system_prompt

        return build_system_prompt(self)

    def _get_orchestrator_system_prompt(self) -> str:
        """Return a base system prompt for the orchestrator."""
        from src.repl.system_prompt import build_orchestrator_system_prompt

        return build_orchestrator_system_prompt(self)

    def _get_last_assistant_text(self) -> str:
        """Get the last assistant text response."""
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

    def _has_recent_file_changes(self) -> bool:
        """Check if the most recent assistant turn included file modifications."""
        if not self._change_log:
            return False
        recent = self._change_log[-3:]
        for entry in recent:
            tool = str(entry.get("tool", ""))
            if tool in ("write_file", "edit_file", "replace_in_files"):
                return True
        return False

    def _handle_command(self, cmd: str) -> None:
        """Handle a /command by dispatching to the commands module."""
        from src.repl.commands import dispatch

        dispatch(self, cmd)

    def _estimated_cost(self) -> float:
        """Return estimated total API cost in USD."""
        from src.repl.help_text import MODEL_PRICING

        pricing = MODEL_PRICING.get(self.llm.model, {"input": 0.50, "output": 0.50})
        in_cost = (self._input_tokens_total / 1_000_000) * pricing["input"]
        out_cost = (self._output_tokens_total / 1_000_000) * pricing["output"]
        return in_cost + out_cost

    def _get_or_create_python_repl(self) -> PythonRepl:
        """Get or create the shared Python REPL instance."""
        if self._python_repl is None:
            from src.python_repl import PythonRepl

            self._python_repl = PythonRepl()
        return self._python_repl

    def _process_turn(self, user_input: str, color_fn: object) -> None:
        """Send a user message to the LLM, stream the response, and show token usage."""
        from src.repl.help_text import contains_markdown
        from src.repl.tool_runner import (
            handle_interactive_tool,
            on_tool_call,
            on_tool_result,
        )

        # Record turn start for latency timeline
        self._turn_start_time = time.time()
        self._current_turn_tools = []
        self._current_llm_start = time.time()

        messages_before = len(self.messages)
        self.messages.append({"role": "user", "content": user_input})
        # Track turns by mode
        self._turns_by_mode[self.mode] = self._turns_by_mode.get(self.mode, 0) + 1
        system_prompt = self._get_system_prompt()
        current_system_tokens = estimate_tokens(system_prompt)
        trimmed = trim_messages(
            self.messages,
            self.max_tokens,
            current_system_tokens,
            client=self.llm if self._enable_summarization else None,
        )
        dropped = messages_before - len(trimmed) + 1  # +1 for the just-added message
        if dropped > 0:
            self._show_trim_warning(dropped)
        self.messages = trimmed

        try:
            context = ToolContext(
                working_directory=self.working_directory,
                file_snapshots=self._file_snapshots,
                orchestrator=self._orchestrator,
                agent_id="main",
                rag_index=self._rag_index,
            )
            # Pass confirm-edits flag for the diff-review feature
            context.confirm_edits = self._confirm_edits

            text_started = False
            self._spinner = None
            # Accumulate full assistant response text for Markdown rendering
            _accumulated_text: list[str] = []
            # Track token usage for this turn
            tokens_before = sum(estimate_tokens(str(m.get("content", ""))) for m in self.messages)

            def _on_text(text: str) -> None:
                nonlocal text_started
                # Stop spinner if still running (first text from LLM)
                if self._spinner is not None:
                    self._spinner.stop()
                    self._spinner = None
                if not text_started:
                    text_started = True
                _accumulated_text.append(text)

            def _restart_spinner() -> None:
                """Restart the spinner for the next LLM round (e.g. after tool results)."""
                nonlocal text_started
                text_started = False  # Reset so next round accumulates too
                if self._spinner is not None:
                    self._spinner.stop()
                self._spinner = Spinner("thinking...")
                self._spinner.start()
                # Record when the LLM round starts for timeline tracking
                self._current_llm_start = time.time()

            # Start animated spinner
            self._spinner = Spinner("thinking...")
            self._spinner.start()

            # Determine read-only status:
            is_read_only = self.mode == "plan" or self.mode == "ask"

            # Set environment variables for the config tool to read
            os.environ["CODING_AGENT_MODE"] = self.mode
            os.environ["CODING_AGENT_MODEL"] = self.llm.model
            os.environ["CODING_AGENT_MAX_TOKENS"] = str(self.max_tokens)
            os.environ["CODING_AGENT_TEMPERATURE"] = str(self.llm.temperature)
            os.environ["CODING_AGENT_PERSONA"] = self._custom_persona or ""

            # Set up budget check callback
            self.llm.on_budget_check = lambda: not self._token_budget_exceeded

            self.llm.chat_with_tools(
                messages=self.messages,
                system=system_prompt,
                tools=self.tools,
                context=context,
                on_text=_on_text,
                on_tool_call=lambda name, args: on_tool_call(self, name, args),
                on_tool_result=lambda _name, r: on_tool_result(self, r, tool_name=_name),
                read_only=is_read_only,
                on_llm_round_start=lambda: _restart_spinner(),
                on_interactive_tool=lambda tool, args: handle_interactive_tool(self, tool, args),
            )

            # ── Check for restart signal from restart_session tool ──────────
            if context.restart_requested:
                # Stop spinner if still running
                if self._spinner is not None:
                    self._spinner.stop()
                    self._spinner = None

                # ── Auto-complete any pending plans (safety net) ─────────────
                from src.plan import complete_plan, list_pending_plans

                pending = list_pending_plans(self.working_directory)
                if len(pending) == 1:
                    plan_name = pending[0].name
                    complete_plan(plan_name, self.working_directory)
                    logger.info("Auto-completed pending plan on restart: name=%s", plan_name)
                    print(f"  {dim(f'📋 Auto-completed plan: {plan_name}')}")
                elif len(pending) > 1:
                    names = ", ".join(p.name for p in pending)
                    print(f"  {yellow('⚠')} {dim(f'{len(pending)} pending plans remain: {names}.')}")

                self.messages.clear()
                self._turn_number = 0
                print(f"\n  {green('✓')} {bold('Restarted.')} {dim('Session reset to turn 1.')}")
                print()
                return

            # If we never got text or tool call, clear spinner
            if self._spinner is not None:
                self._spinner.stop()
                self._spinner = None

            # ── Render final response ─────────────────────────────────────────
            if _accumulated_text:
                full_text = "".join(_accumulated_text)
                # Process mermaid code blocks
                from src.diagrams import process_mermaid_blocks

                full_text = process_mermaid_blocks(full_text)
                # Render with Rich if Markdown formatting detected, else plain text
                if contains_markdown(full_text):
                    from src.markdown import render_markdown

                    color_fn_rendered = turn_separator_color(self)
                    print(f"  {color_fn_rendered('┃')}", end=" ")
                    render_markdown(full_text)
                else:
                    color_fn_rendered = turn_separator_color(self)
                    print(f"  {color_fn_rendered('┃')} {full_text}")

            # ── Finalize turn latency timeline ────────────────────────────
            llm_duration = time.time() - self._turn_start_time
            self._turn_timeline.append(
                {
                    "turn": len(self._turn_timeline) + 1,
                    "llm_duration": llm_duration,
                    "tools": list(self._current_turn_tools),
                    "total_duration": time.time() - self._turn_start_time,
                }
            )

            # ── Show token usage for this turn ──────────────────────────────
            tokens_after = sum(estimate_tokens(str(m.get("content", ""))) for m in self.messages)
            turn_tokens = tokens_after - tokens_before
            # Track cumulative costs (estimated: split 50/50 in/out for simplicity)
            estimated_input = turn_tokens // 2
            estimated_output = turn_tokens - estimated_input
            self._input_tokens_total += estimated_input
            self._output_tokens_total += estimated_output
            print(f"  {dim(f'┄ {turn_tokens} tokens used this turn')}")

            # ── Auto-save after successful turn ──────────────────────────
            self._auto_save()

            # ── Post-turn verification nudge (for code mode) ─────────────
            if self.mode == "code" and self._has_recent_file_changes():
                last_asst = self._get_last_assistant_text()
                if last_asst and not any(
                    word in last_asst.lower() for word in ["verified", "verification", "check", "test", "confirm"]
                ):
                    print(f"  {yellow('💡')} {dim('Tip: Verify your changes with read_file, diff, or run_tests.')}")

        except json.JSONDecodeError:
            if self._spinner is not None:
                self._spinner.stop()
                self._spinner = None
            last_msgs = self.messages[-3:] if len(self.messages) >= 3 else self.messages
            logger.error("JSON decode error in LLM response stream")
            print(f"\n  {red('✗ JSON Error:')} {dim('Failed to parse API response.')}")
            print(f"  {dim('This may indicate a transient API issue or malformed response data.')}")
            print(f"  {dim(f'Last {len(last_msgs)} message(s) preserved.')}")
            print(f"  {dim('Type')} {cyan('/retry')} {dim('to re-send your last message.')}")

        except Exception as exc:
            from anthropic import (
                APIConnectionError,
                APIError,
                InternalServerError,
                RateLimitError,
            )

            if self._spinner is not None:
                self._spinner.stop()
                self._spinner = None

            if isinstance(exc, APIConnectionError):
                logger.error("API connection error")
                print(f"\n  {red('✗ Connection Error:')} {dim('Failed to connect to API.')}")
                print(f"  {dim('Check your internet connection and API endpoint.')}")
                print(f"  {dim('Type')} {cyan('/retry')} {dim('to re-send your last message.')}")
            elif isinstance(exc, RateLimitError):
                logger.error("Rate limit exceeded")
                print(f"\n  {red('✗ Rate Limited:')} {dim('API rate limit exceeded.')}")
                print(f"  {dim('Waiting before retry...')}")
                time.sleep(5)
                self._handle_retry()  # type: ignore[attr-defined]
            elif isinstance(exc, InternalServerError):
                logger.error("Anthropic internal server error")
                print(f"\n  {red('✗ Server Error:')} {dim('API internal server error.')}")
                print(f"  {dim('Waiting before retry...')}")
                time.sleep(3)
                self._handle_retry()  # type: ignore[attr-defined]
            elif isinstance(exc, APIError):
                logger.error("API error: %s", exc)
                print(f"\n  {red('✗ API Error:')} {dim(str(exc))}")
                print(f"  {dim('Type')} {cyan('/retry')} {dim('to re-send your last message.')}")
            else:
                logger.error("Unexpected error in _process_turn: %s", exc, exc_info=True)
                print(f"\n  {red('✗ Error:')} {exc}")
                print(f"  {dim('Type')} {cyan('/retry')} {dim('to re-send your last message.')}")
        print()
