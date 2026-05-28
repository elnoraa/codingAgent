from __future__ import annotations

import json
import logging
import os
import time

from .client import LlmClient
from .logging_config import get_logger
from .mode import ASK_MODE_SYSTEM_PROMPT, PLAN_MODE_SYSTEM_PROMPT
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
from tools.restart_session import restart_session_tool
from tools.web_search import web_search_tool
from tools.undo_tool import undo_tool
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
from .exporter import export_as_markdown, export_as_json
from .profiles import Profile, delete_profile, list_profiles, load_profile, save_profile
from .prompts import list_prompts, load_prompt, save_prompt

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
  /mode                   Show current mode (code/plan/ask)
  /plan, /p               Switch to plan mode (read-only exploration)
  /ask, /a                Switch to ask mode (read-only Q&A)
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
  /restart                Reset session to turn 1 (clear messages)
  /cost                   Show token usage and estimated API cost
  /export [md|json] [path]  Export conversation as Markdown or JSON
  /search <pattern>        Search conversation history
  /search -r <regex>       Search conversation with regex
  /model [name]            Show or switch the active model
  /cd [path]               Change working directory
  /rollback                Ask agent to undo file changes
  undo                     List/revert file snapshots (tool)
  /config                 Show current configuration
  /prompt list            List all prompt templates
  /prompt load <name>     Load a prompt template
  /prompt save <name>     Save last assistant response as a prompt
  /profile list           List all saved configuration profiles
  /profile load <name>    Load a configuration profile
  /profile save <name>    Save current config as a profile
  /profile delete <name>  Delete a configuration profile

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
  ASK mode   {magenta('●')}  Read-only Q&A & explanation (read-only tools only)"""


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

    def __init__(
        self,
        llm: LlmClient,
        system_prompt: str,
        max_tokens: int,
        custom_persona: str = "",
        auto_save_interval: int = 0,
        context_files: list[str] | None = None,
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

        # Cost tracking
        self._input_tokens_total = 0
        self._output_tokens_total = 0

        self.tools = ToolRegistry()
        self._register_all_tools()
        self._auto_save_interval = 0
        self._turns_since_auto_save = 0
        self._last_auto_save_path: str | None = None
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
        self.tools.register(restart_session_tool)
        self.tools.register(think_tool)
        self.tools.register(web_search_tool)
        self.tools.register(undo_tool)

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
        finally:
            # Always auto-save on exit
            if self._auto_save_interval > 0 and self._last_auto_save_path is not None:
                try:
                    path = save_session(
                        name=f"autosave-exit-{int(time.time())}",
                        messages=self.messages,
                        mode=self.mode,
                        working_directory=self.working_directory,
                        model=self.llm.model,
                        is_autosave=True,
                    )
                    print(f"  {dim('Auto-saved session:')} {cyan(path)}")
                except Exception:
                    pass

    def _turn_separator_color(self):
        """Return the color function for the current mode's separator."""
        if self.mode == "plan":
            return yellow
        if self.mode == "ask":
            return magenta
        return dim

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

    def _auto_save(self) -> None:
        """Auto-save the session if the interval has been reached."""
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
        while True:
            self._turn_number += 1
            color_fn = self._turn_separator_color()
            print()

            try:
                mode_tag = (
                    f"{magenta(self.mode.upper())}" if self.mode == "ask"
                    else f"{yellow(self.mode.upper())}" if self.mode == "plan"
                    else f"{cyan(self.mode.upper())}"
                )
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
            context = ToolContext(
                working_directory=self.working_directory,
                file_snapshots=self._file_snapshots,
            )

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
            # - Ask mode is always read-only
            # - Code mode has all tools available
            is_read_only = self.mode == "plan" or self.mode == "ask"

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

            # ── Check for restart signal from restart_session tool ──────────
            if context.restart_requested:
                self.messages.clear()
                self._turn_number = 0
                print(f"\n  {green('✓')} {bold('Restarted.')} {dim('Session reset to turn 1.')}")
                print()
                return

            # If we never got text, clear thinking indicator
            if not thinking_shown:
                print("\r" + " " * 70, end="", flush=True)
                print("\r", end="", flush=True)

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

            # ── Auto-save after successful turn ──────────────────────────
            self._auto_save()

        except json.JSONDecodeError:
            last_msgs = self.messages[-3:] if len(self.messages) >= 3 else self.messages
            logger.error("JSON decode error in LLM response stream")
            print(f"\n  {red('✗ JSON Error:')} {dim('Failed to parse API response.')}")
            print(f"  {dim('This may indicate a transient API issue or malformed response data.')}")
            print(f"  {dim(f'Last {len(last_msgs)} message(s) preserved.')}")
            print(f"  {dim('Type')} {cyan('/retry')} {dim('to re-send your last message.')}")
        except Exception as exc:
            logger.error("Unexpected error in _process_turn: %s", exc, exc_info=True)
            print(f"\n  {red('✗ Error:')} {exc}")
        print()

    def _show_trim_warning(self, dropped: int) -> None:
        """Display a warning when messages have been trimmed."""
        label = "message" if dropped == 1 else "messages"
        print(f"  {yellow('⚠')} {dim(f'{dropped} earlier {label} removed to stay within context limits.')}")

    def _get_system_prompt(self) -> str:
        if self.mode == "plan":
            base = PLAN_MODE_SYSTEM_PROMPT
        elif self.mode == "ask":
            base = ASK_MODE_SYSTEM_PROMPT
        else:
            base = self.system_prompt
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

        # Restart instruction (CODE mode only)
        restart_instruction = ""
        if self.mode == "code":
            restart_instruction = (
                "\n\n## Automatic Session Restart\n"
                "After you complete a task, present a summary of what was done, "
                "and the user is satisfied, call the `restart_session` tool to reset "
                "the session back to turn 1 for the next task."
            )

        # ── Context files injection ────────────────────────────────────────
        context_section = ""
        if self._context_files:
            import glob as _glob
            injected: list[str] = []
            for pattern in self._context_files:
                matched = _glob.glob(os.path.join(self.working_directory, pattern))
                for filepath in matched:
                    if not os.path.isfile(filepath):
                        continue
                    try:
                        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                            content = f.read(2000)  # cap at 2000 chars
                        relpath = os.path.relpath(filepath, self.working_directory)
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
            f"Current working directory: {self.working_directory}\n"
            f"Project root: {self.working_directory}\n\n"
            f"{base}\n\n"
            f"Remember to explore the codebase with read-only tools before making changes."
            f"{persona}"
            f"{coding_agent_rules}"
            f"{restart_instruction}"
            f"{context_section}"
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

    def _handle_prompt(self, cmd: str) -> None:
        """Handle /prompt command — save, load, list prompt templates."""
        parts = cmd.strip().split(maxsplit=2)
        subcommand = parts[1].lower() if len(parts) > 1 else "list"

        if subcommand == "save":
            if len(parts) < 3:
                print(f"  {dim('Usage: /prompt save <name>')}")
                print(f"  {dim('Saves the last assistant response as a prompt template.')}")
                return
            name = parts[2].strip()
            text = self._get_last_assistant_text()
            if not text:
                print(f"  {dim('No assistant response to save. Send a message first.')}")
                return
            try:
                filepath = save_prompt(name, text, self.working_directory)
                print(f"  {green('✓')} {dim('Prompt saved to')} {cyan(filepath)}")
            except Exception as exc:
                print(f"  {red('✗ Error saving prompt:')} {exc}")

        elif subcommand == "load":
            if len(parts) < 3:
                print(f"  {dim('Usage: /prompt load <name>')}")
                return
            name = parts[2].strip()
            prompt = load_prompt(name, self.working_directory)
            if prompt is None:
                print(f"  {dim('Prompt not found:')} {cyan(name)}")
                print(f"  {dim('Use /prompt list to see available prompts.')}")
                return
            tag = f"{green('built-in')}" if prompt.is_builtin else f"{yellow('custom')}"
            print(f"  {bold(prompt.name)} {tag}")
            print(f"  {dim('─' * 40)}")
            for line in prompt.content.strip().split("\n"):
                print(f"  {line}")

        elif subcommand == "list":
            prompts = list_prompts(self.working_directory)
            if not prompts:
                print(f"  {dim('No prompts available.')}")
                return
            print(f"  {bold('Prompt Templates')}")
            print()
            for p in prompts:
                tag = f"{green('built-in')}" if p.is_builtin else f"{yellow('custom')}"
                name_str = cyan(p.name.ljust(20))
                preview = p.content[:60].replace("\n", " ") + "..."
                print(f"  {name_str} {tag} {dim(preview)}")

        else:
            print(f"  {dim('Unknown prompt command. Usage:')}")
            print(f"  {dim('  /prompt list              — list all prompts')}")
            print(f"  {dim('  /prompt load <name>       — load a prompt template')}")
            print(f"  {dim('  /prompt save <name>       — save last response as prompt')}")

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
            mode_tag = (
                f"{magenta(self.mode.upper())}" if self.mode == "ask"
                else f"{yellow(self.mode.upper())}" if self.mode == "plan"
                else f"{cyan(self.mode.upper())}"
            )
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

    def _handle_profile(self, cmd: str) -> None:
        """Handle /profile command — save, load, list, delete configuration profiles."""
        parts = cmd.strip().split(maxsplit=2)
        subcommand = parts[1].lower() if len(parts) > 1 else "list"

        if subcommand == "save":
            if len(parts) < 3:
                print(f"  {dim('Usage: /profile save <name>')}")
                return
            name = parts[2].strip()
            profile_data = {
                "model": self.llm.model,
                "max_tokens": self.max_tokens,
                "temperature": self.llm.temperature,
                "top_p": self.llm.top_p,
                "system_prompt": self.system_prompt,
                "custom_persona": self._custom_persona,
            }
            try:
                filepath = save_profile(name, profile_data, self.working_directory)
                print(f"  {green('✓')} {dim('Profile saved to')} {cyan(filepath)}")
            except Exception as exc:
                print(f"  {red('✗ Error saving profile:')} {exc}")

        elif subcommand == "load":
            if len(parts) < 3:
                print(f"  {dim('Usage: /profile load <name>')}")
                return
            name = parts[2].strip()
            profile = load_profile(name, self.working_directory)
            if profile is None:
                print(f"  {dim('Profile not found:')} {cyan(name)}")
                print(f"  {dim('Use /profile list to see available profiles.')}")
                return
            # Apply profile values (only non-default fields)
            applied: list[str] = []
            if profile.model:
                self.llm.model = profile.model
                applied.append(f"model={profile.model}")
            if profile.max_tokens > 0:
                self.max_tokens = profile.max_tokens
                applied.append(f"max_tokens={profile.max_tokens}")
            if profile.temperature > 0:
                self.llm.temperature = profile.temperature
                applied.append(f"temperature={profile.temperature}")
            if profile.top_p > 0:
                self.llm.top_p = profile.top_p
                applied.append(f"top_p={profile.top_p}")
            if profile.system_prompt:
                self.system_prompt = profile.system_prompt
                applied.append("system_prompt=✓")
            if profile.custom_persona:
                self._custom_persona = profile.custom_persona
                applied.append("persona=✓")
            print(f"  {green('✓')} {bold(f'Profile loaded: {profile.name}')}")
            for item in applied:
                print(f"    {dim('•')} {cyan(item)}")

        elif subcommand == "list":
            profiles = list_profiles(self.working_directory)
            if not profiles:
                print(f"  {dim('No saved profiles found.')}")
                print(f"  {dim('Use /profile save <name> to save the current configuration.')}")
                return
            print(f"  {bold('Saved Profiles')}")
            print()
            for p in profiles:
                model_str = p.model if p.model else "(default)"
                print(f"  {cyan(p.name.ljust(20))} {dim(model_str)}")

        elif subcommand == "delete":
            if len(parts) < 3:
                print(f"  {dim('Usage: /profile delete <name>')}")
                return
            name = parts[2].strip()
            if delete_profile(name, self.working_directory):
                print(f"  {green('✓')} {dim('Profile deleted:')} {cyan(name)}")
            else:
                print(f"  {dim('Profile not found:')} {cyan(name)}")

        else:
            print(f"  {dim('Unknown profile command. Usage:')}")
            print(f"  {dim('  /profile list              — list all profiles')}")
            print(f"  {dim('  /profile load <name>       — load a configuration profile')}")
            print(f"  {dim('  /profile save <name>       — save current config as profile')}")
            print(f"  {dim('  /profile delete <name>     — delete a profile')}")

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

    def _handle_search(self, parts: list[str]) -> None:
        """Handle /search command — search messages for a pattern."""
        import re as regex_module

        args = " ".join(parts[1:]) if len(parts) > 1 else ""
        use_regex = False
        if args.startswith("-r "):
            use_regex = True
            args = args[3:].strip()

        if not args:
            print(f"  {dim('Usage: /search <pattern>')}")
            print(f"  {dim('       /search -r <regex>')}")
            return

        results: list[tuple[int, str, str]] = []
        for i, msg in enumerate(self.messages):
            role = str(msg.get("role", "unknown"))
            content = msg.get("content", "")

            text_to_search = ""
            if isinstance(content, str):
                text_to_search = content
            elif isinstance(content, list):
                from typing import cast as _cast
                blocks = _cast("list[dict[str, object]]", content)
                for block in blocks:
                    t = block.get("text")
                    if isinstance(t, str):
                        text_to_search += t + " "
                    c = block.get("content")
                    if isinstance(c, str):
                        text_to_search += c + " "

            match_found = False
            if use_regex:
                try:
                    match_found = bool(regex_module.search(args, text_to_search))
                except regex_module.error:
                    print(f"  {red('✗')} {dim(f'Invalid regex: {args}')}")
                    return
            else:
                match_found = args.lower() in text_to_search.lower()

            if match_found:
                preview = self._search_preview(text_to_search, args, use_regex)
                results.append((i, role, preview))

        if not results:
            print(f"  {dim(f'No matches for: {args}')}")
            return

        print(f"  {bold(f'Search results for "{args}":')} {dim(f'({len(results)} matches)')}")
        print()
        for idx, role, preview in results:
            role_color = green if role == "user" else cyan
            print(f"  {dim(f'#{idx + 1}')} {role_color(role.title())} {preview}")

    def _search_preview(self, text: str, pattern: str, use_regex: bool) -> str:
        """Extract ~120 chars around the match for a preview."""
        import re as regex_module

        if use_regex:
            match = regex_module.search(pattern, text)
            if not match:
                return text[:120]
            start = max(0, match.start() - 40)
            end = min(len(text), match.end() + 80)
        else:
            lower_text = text.lower()
            lower_pattern = pattern.lower()
            idx = lower_text.find(lower_pattern)
            if idx == -1:
                return text[:120]
            start = max(0, idx - 40)
            end = min(len(text), idx + len(pattern) + 80)

        preview = text[start:end]
        if start > 0:
            preview = "..." + preview
        if end < len(text):
            preview = preview + "..."
        # Replace newlines with spaces for single-line preview
        preview = preview.replace("\n", " ").strip()
        if len(preview) > 120:
            preview = preview[:117] + "..."
        return dim(preview)

    def _handle_cd(self, parts: list[str]) -> None:
        """Handle /cd command — change working directory."""
        if len(parts) < 2:
            wd = self.working_directory.replace(os.environ.get("HOME", "~"), "~") if "HOME" in os.environ else self.working_directory
            print(f"  {dim('Current directory:')} {cyan(wd)}")
            return

        path_str = " ".join(parts[1:]).strip()
        if not path_str:
            return

        new_path = os.path.abspath(os.path.join(self.working_directory, path_str))
        if not os.path.isdir(new_path):
            print(f"  {red('✗')} {dim('Not a directory:')} {cyan(path_str)}")
            return

        old_wd = self.working_directory
        self.working_directory = new_path
        logger.info("Working directory changed: %s -> %s", old_wd, new_path)
        display_new = new_path.replace(os.environ.get("HOME", "~"), "~") if "HOME" in os.environ else new_path
        print(f"  {green('✓')} {dim('Changed directory:')} {cyan(display_new)}")

    def _handle_model(self, parts: list[str]) -> None:
        """Handle /model command — show or switch the active model."""
        if len(parts) < 2:
            print(f"  {bold('Current Model:')} {cyan(self.llm.model)}")
            print(f"  {dim('Usage: /model <model-name> to switch')}")
            print(f"  {dim('Example: /model claude-3-5-sonnet-20241022')}")
            return

        new_model = parts[1].strip()
        if not new_model:
            print(f"  {dim('Usage: /model <model-name>')}")
            return

        if new_model == self.llm.model:
            print(f"  {dim('Already using')} {cyan(new_model)}")
            return

        old_model = self.llm.model
        self.llm.model = new_model
        logger.info("Model switched: %s -> %s", old_model, new_model)
        print(f"  {green('✓')} {dim('Model switched:')} {cyan(old_model)} {dim('→')} {cyan(new_model)}")

    def _handle_export(self, parts: list[str]) -> None:
        """Handle /export command — export conversation as Markdown or JSON."""
        fmt = "md"
        output_path: str | None = None
        if len(parts) > 1:
            arg = parts[1].strip().lower()
            if arg in ("json", "md"):
                fmt = arg
                if len(parts) > 2:
                    output_path = parts[2]
            else:
                # Treat as path, default to md
                output_path = parts[1]

        if not self.messages:
            print(f"  {dim('No messages to export.')}")
            return

        try:
            if fmt == "json":
                filepath = export_as_json(self.messages, self.mode, self.llm.model, output_path)
            else:
                filepath = export_as_markdown(self.messages, self.mode, self.llm.model, output_path)
            print(f"  {green('✓')} {dim('Exported to')} {cyan(filepath)}")
        except Exception as exc:
            print(f"  {red('✗ Export failed:')} {exc}")

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
                tools_to_show = self.tools.get_read_only() if self.mode in ("plan", "ask") else self.tools.get_all()
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
                    print(f"  {dim('  /ask               — switch to ask mode (Q&A)')}")
            case "/ask" | "/a":
                if self.mode == "ask":
                    print(f"  {dim('Already in ask mode.')}")
                else:
                    self.mode = "ask"
                    logger.info("Switched to ASK mode")
                    print(f"  {magenta('●')} {bold('ASK mode')} {dim('— read-only Q&A. Only read-only tools are available.')}")
                    print(f"  {dim('Use /code to switch back to CODE mode.')}")
            case "/code":
                if self.mode == "code":
                    print(f"  {dim('Already in code mode.')}")
                else:
                    self.mode = "code"
                    logger.info("Switched to CODE mode")
                    print(f"  {green('●')} {bold('CODE mode')} {dim('— all tools available (read, write, execute).')}")
                    print(f"  {dim('Use /plan to switch to PLAN mode, or /ask for Q&A mode.')}")
            case "/mode":
                logger.info("Mode check: current mode=%s", self.mode)
                print(f"  {bold('Mode:')} {bold(self.mode.upper())}")
            case "/edit":
                self._handle_edit()
            case "/retry" | "/r":
                self._handle_retry()
            case "/cost":
                self._handle_cost()
            case "/cd":
                self._handle_cd(parts)
            case "/rollback":
                print(f"  {dim('Use the undo tool to rollback changes.')}")
                print(f"  {dim('The agent can list and revert file snapshots automatically.')}")
            case "/model":
                self._handle_model(parts)
            case "/search":
                self._handle_search(parts)
            case "/export":
                self._handle_export(parts)
            case "/config":
                self._handle_config()
            case "/prompt":
                self._handle_prompt(cmd)
            case "/profile":
                self._handle_profile(cmd)
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
                self._turn_number = 0
                logger.info("Session restarted (messages cleared)")
                print(f"  {green('✓')} {bold('Restarted.')} {dim('Session reset to turn 1.')}")
            case "/q":
                print(f"  {dim('Exiting...')}")
                # Trigger clean exit
                raise EOFError()
            case _:
                print(f"  {dim(f'Unknown command: {parts[0]}. Type /help for available commands.')}")
