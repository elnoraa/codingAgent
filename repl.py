from __future__ import annotations

import os
import time
from pathlib import Path

from client import LlmClient
from mode import PLAN_MODE_SYSTEM_PROMPT
from tools import ToolContext, ToolRegistry
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
from tools.url_fetch import url_fetch_tool
from tools.think_tool import think_tool
from typing import cast

from utils import bold, dim, green, yellow, cyan, red, color_json, estimate_tokens, trim_messages, blue, magenta

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
  /edit                   Edit and re-send the last user message
  /retry, /r              Re-send the last user message (e.g. after API error)

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
  url_fetch       Fetch a URL's content
  think           Reason step by step (no-op)

{bold('Modes')}
  CODE mode  {green('●')}  All tools available (read + write + execute)
  PLAN mode  {yellow('●')}  Read-only exploration & planning (read-only tools only)"""


class Repl:
    def __init__(
        self,
        llm: LlmClient,
        system_prompt: str,
        max_tokens: int,
    ) -> None:
        self.llm = llm
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens
        self.messages: list[dict[str, object]] = []
        self.working_directory = os.getcwd()
        self.mode = "code"
        self._turn_number = 0
        self._start_time = time.time()

        self.tools = ToolRegistry()
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
        self.tools.register(url_fetch_tool)
        self.tools.register(think_tool)

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

            self.llm.chat_with_tools(
                messages=self.messages,
                system=system_prompt,
                tools=self.tools,
                context=context,
                on_text=_on_text,
                on_tool_call=self._on_tool_call,
                on_tool_result=lambda _name, r: self._on_tool_result(r),
                read_only=(self.mode == "plan"),
            )

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
        return (
            f"Current working directory: {self.working_directory}\n"
            f"Available project directories: /app (this agent), /projects/ (sibling projects)\n\n"
            f"{base}\n\n"
            f"Remember: Always plan before you act. Explore the codebase, reason with the think tool, "
            f"present your plan, and only then execute changes."
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

        plans_dir = Path(self.working_directory) / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)

        safe_name = name.replace(" ", "-")
        safe_name = "".join(c for c in safe_name if c.isalnum() or c in "-_.")
        filepath = plans_dir / f"{safe_name}.md"

        filepath.write_text(text + "\n", encoding="utf-8")
        print(f"  {green('✓')} {dim('Plan saved to')} {cyan(str(filepath))}")

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

    def _handle_command(self, cmd: str) -> None:
        if cmd.startswith("/plan save"):
            self._handle_plan_save(cmd)
            return

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
            case "/plan" | "/p":
                if self.mode == "plan":
                    print(f"  {dim('Already in plan mode.')}")
                else:
                    self.mode = "plan"
                    print(f"  {yellow('●')} {bold('PLAN mode')} {dim('— read-only exploration. Only read-only tools are available.')}")
                    print(f"  {dim('Use /code to switch back to CODE mode.')}")
            case "/code":
                if self.mode == "code":
                    print(f"  {dim('Already in code mode.')}")
                else:
                    self.mode = "code"
                    print(f"  {green('●')} {bold('CODE mode')} {dim('— all tools available (read, write, execute).')}")
                    print(f"  {dim('Use /plan to switch to PLAN mode.')}")
            case "/mode":
                print(f"  {bold('Mode:')} {bold(self.mode.upper())}")
            case "/edit":
                self._handle_edit()
            case "/retry" | "/r":
                self._handle_retry()
            case "/q":
                print(f"  {dim('Exiting...')}")
                # Trigger clean exit
                raise EOFError()
            case _:
                print(f"  {dim(f'Unknown command: {parts[0]}. Type /help for available commands.')}")
