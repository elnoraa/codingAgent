from __future__ import annotations

import json
import logging
import os
import time

import anthropic

from .client import LlmClient
from .logging_config import get_logger
from .mode import ASK_MODE_SYSTEM_PROMPT, PLAN_MODE_SYSTEM_PROMPT
from .notifications import notify, should_notify, play_sound
from tools import Tool, ToolContext, ToolRegistry

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
from tools.python_tool import python_tool
from tools.write_plan import write_plan_tool
from tools.complete_plan import complete_plan_tool
from tools.ask_user import ask_user_tool
from tools.syntax_check import syntax_check_tool
from tools.verify_content import verify_content_tool
from tools.config_tool import config_tool
from tools.git_log import git_log_tool
from tools.environment import environment_tool
from tools.spawn_agent import spawn_agent_tool
from tools.list_agents import list_agents_tool
from tools.send_to_agent import send_to_agent_tool
from tools.terminate_agent import terminate_agent_tool
from tools.run_swarm import run_swarm_tool
from tools.git_revert import git_revert_tool
from tools.rename_file import rename_file_tool
from tools.git_branch import git_branch_tool
from tools.api_tool import api_tool
from tools.precommit_tool import precommit_tool
from tools.ci_tool import ci_tool
from tools.db_tool import db_tool
from tools.docker_tool import docker_tool
from .session import save_session, load_session, list_sessions
from typing import Any, cast, TYPE_CHECKING

if TYPE_CHECKING:
    from src.python_repl import PythonRepl

from .plan import (
    complete_plan,
    generate_plan_template,
    list_completed_plans,
    list_pending_plans,
    save_pending_plan,
)
from .utils import bold, dim, green, yellow, cyan, red, color_json, estimate_tokens, trim_messages, blue, magenta, Spinner, render_markdown
from .exporter import export_as_markdown, export_as_json
from .custom_tools import load_custom_tools
from .dep_analyzer import ImportGraph
from .profiles import Profile, delete_profile, list_profiles, load_profile, save_profile
from .prompts import list_prompts, load_prompt, save_prompt
from .orchestrator import Orchestrator
from .mcp_bridge import MCPBridge
from .snippets import list_snippets, load_snippet, save_snippet, delete_snippet

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
  /help <command>         Show detailed help for a specific command
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
  /retry-auto, /ra        Re-send with escalation prompt ("try harder")
  /save <name>            Save the current session
  /load <name>            Load a saved session
  /sessions               List all saved sessions
  /persona <text>         Set a custom persona (appended to system prompt)
  /persona clear          Clear the custom persona
  /reload                 Re-discover and re-register all tools from disk (no restart needed)
  /restart                Reset session to turn 1 (clear messages)
  /cost                   Show token usage and estimated API cost
  /stats                  Show detailed session statistics
  /export [md|json|session] [path]  Export conversation as Markdown, JSON, or full .agent-session
  /search <pattern>        Search conversation history
  /search -r <regex>       Search conversation with regex
  /diff-review [on|off]    Toggle interactive diff review (confirm edits)
  /snippet list            List all saved snippets
  /snippet save <name>     Save last assistant response as a snippet
  /snippet load <name>     Display a saved snippet
  /snippet delete <name>   Delete a snippet
  /snippet apply <name>    Load snippet into next message
  /model [name]            Show or switch the active model
  /cd [path]               Change working directory
  /rollback                Ask agent to undo file changes
  /config                 Show current configuration
  /prompt list            List all prompt templates
  /prompt load <name>     Load a prompt template
  /prompt save <name>     Save last assistant response as a prompt
  /profile list           List all saved configuration profiles
  /profile load <name>    Load a configuration profile
  /profile save <name>    Save current config as a profile
  /profile delete <name>  Delete a configuration profile
  /mcp                    Show MCP server connection status and tools
  /changes                Show session change log (audit trail)
  /open <filename>         Fuzzy-find and open a file by partial name
  /backup [label]          Create a backup (optional label)
  /backup list             List all backups
  /backup restore <name>   Restore from a backup
  /backup clean [N]        Remove old backups, keep N most recent
  /timeline                Show per-turn latency breakdown (LLM vs tools)
  /python                 Show Python REPL state
  /reset-python           Reset the Python REPL (clear all variables)
  /deps <file>            Show what a Python file imports (dependencies)
  /impact <file>          Show what imports a Python file (impact analysis)

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
  complete_plan   Move a plan from pending to completed
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
  python          Execute Python code snippets in an embedded REPL
  restart_session Reset session to turn 1 (clears messages)
  think           Reason step by step (no-op)
  undo            List/revert file snapshots
  web_search      Search the web for information
  write_plan      Save a plan to plans/pending/
  ask_user        Ask for clarification when instructions are ambiguous
  syntax_check    Validate Python files for syntax errors
  verify_content  Verify file contains/omits expected text
  config          Show agent's current configuration
  git_log         Show git commit history
  environment     Show runtime environment details
  spawn_agent     Spawn a sub-agent to complete a task
  list_agents     List all active sub-agents
  send_to_agent   Send a message to another agent
  terminate_agent Stop and remove a sub-agent
  run_swarm       Run a swarm of agents in a collaboration pattern
  git_revert      Undo/revert git changes (unstage, undo_commit, reset, discard)
  rename_file     Rename or move files/directories (git-aware)
  git_branch      Manage git branches (list, create, switch, merge, delete, diff)
  api             Make HTTP requests (GET, POST, etc.) to API endpoints
  precommit       Manage pre-commit hooks (install, run, update, validate)
  ci              CI/CD integration (detect, validate config, check pipeline status)
  db              Explore databases (SQLite, PostgreSQL, MySQL)
  docker          Manage Docker (containers, images, Compose)

{bold('Modes')}
  CODE mode  {green('●')}  All tools available (read + write + execute)
  PLAN mode  {yellow('●')}  Read-only exploration & planning (read-only tools only)
  ASK mode   {magenta('●')}  Read-only Q&A & explanation (read-only tools only)"""

COMMAND_HELP: dict[str, str] = {
    "save": """\
Usage: /save <name>

Saves the current session (messages, mode, model, working directory)
to a JSON file in the sessions/ directory.

Examples:
  /save my-session       Save as "my-session"
  /save project-analysis Save as "project-analysis"

See also: /load, /sessions""",
    "load": """\
Usage: /load <name>

Loads a previously saved session from the sessions/ directory.
Restores messages, mode, and working directory.

Examples:
  /load my-session

See also: /save, /sessions""",
    "sessions": """\
Usage: /sessions

Lists all saved sessions with timestamps, message count, and mode.
Sessions are stored as JSON files in the sessions/ directory.

See also: /save, /load""",
    "help": """\
Usage: /help [<command>]

With no arguments: shows the full list of available commands and tools.
With a command name: shows detailed help for that specific command.

Examples:
  /help              Show all commands
  /help save         Show detailed help for /save
  /help /prompt      Also works with leading slash""",
    "clear": """\
Usage: /clear or /c

Clears the conversation history (all messages).
Does not affect mode, model, or other settings.

See also: /restart""",
    "tools": """\
Usage: /tools

Lists all tools available in the current mode.
- In CODE mode: all tools are available (read + write + execute)
- In PLAN mode: only read-only tools
- In ASK mode: only read-only tools""",
    "history": """\
Usage: /history

Shows a detailed breakdown of all messages in the current session,
including role (user/assistant), estimated tokens, and preview text.

See also: /status""",
    "status": """\
Usage: /status or /s

Shows the current session status: mode, model, max tokens,
message count, estimated tokens, uptime, working directory,
custom persona (if set), and estimated cost.

See also: /history, /cost""",
    "mode": """\
Usage: /mode

Shows the current mode: CODE, PLAN, or ASK.

Modes:
  CODE  - All tools available (read + write + execute)
  PLAN  - Read-only exploration & planning
  ASK   - Read-only Q&A & explanation

See also: /plan, /ask, /code""",
    "plan": """\
Usage: /plan or /p

Switches to PLAN mode (read-only exploration and planning).

Subcommands:
  /plan save <name>       Save last assistant response as a plan file
  /plan create <topic>    Create a structured plan template for a task
  /plan list              List pending plans
  /plan list completed    List completed plans

See also: /ask, /code""",
    "ask": """\
Usage: /ask or /a

Switches to ASK mode (read-only Q&A). In this mode, only
read-only tools are available for asking questions about the codebase.

See also: /plan, /code""",
    "code": """\
Usage: /code

Switches to CODE mode where all tools are available, including
read, write, and execute operations.

See also: /plan, /ask""",
    "edit": """\
Usage: /edit

Edits the last user message and re-sends it. Shows the previous
message content, then prompts for the new content.

See also: /retry""",
    "retry": """\
Usage: /retry or /r

Re-sends the last user message with the same content.
Useful after an API error or when you want the LLM to try again.

See also: /edit""",
    "retry-auto": """\
Usage: /retry-auto or /ra

Re-sends the last user message with an escalation prompt that tells
the agent to "try harder" and use a different approach if previous
attempts failed. Use this when the agent gave up too early or missed
parts of your request.

The escalation includes an attempt counter so the agent knows how many
times this task has been retried.

See also: /retry""",
    "persona": """\
Usage: /persona <text>
       /persona clear

Sets a custom persona that gets appended to the system prompt.
Use /persona clear to remove the custom persona.

Examples:
  /persona You are an expert Python developer
  /persona clear""",
    "reload": """\
Usage: /reload

Re-discovers and re-registers all tools from disk. Useful after
adding new tool modules without restarting the agent.

See also: /restart""",
    "restart": """\
Usage: /restart

Resets the session to turn 1 by clearing all messages.
Does not change mode, model, or other settings.

See also: /clear""",
    "cost": """\
Usage: /cost

Shows detailed cost breakdown: model pricing, input/output tokens,
system prompt tokens, and estimated total cost in USD.

Pricing is based on the built-in MODEL_PRICING table.""",
    "export": """\
Usage: /export [md|json|session] [path]

Exports the conversation history as Markdown, JSON, or full .agent-session format.

Formats:
  md       - Markdown format (default)
  json     - JSON format with messages
  session  - Full .agent-session file with messages, metadata, and file listing

Examples:
  /export                  Export as Markdown (default)
  /export json             Export as JSON
  /export session          Export full session as .agent-session
  /export session ./backup.agent-session Export to a specific path""",
    "search": """\
Usage: /search <pattern>
       /search -r <regex>

Searches the conversation history for a text pattern or regex.

Examples:
  /search error            Find messages containing "error"
  /search -r \\d+\\.\\d+     Find messages matching a regex pattern""",
    "stats": """\
Usage: /stats

Shows detailed session statistics: duration, total turns, messages,
tokens, mode switches, turns by mode, tool usage counts, and estimated cost.

See also: /status, /cost""",
    "model": """\
Usage: /model [name]

Shows the current model, or switches to a different model.

Examples:
  /model                   Show current model
  /model claude-3-5-sonnet-20241022  Switch model""",
    "cd": """\
Usage: /cd [path]

Changes the working directory. With no arguments, shows the
current working directory.

Examples:
  /cd                      Show current directory
  /cd src                  Change to src/ directory
  /cd ..                   Go up one directory""",
    "rollback": """\
Usage: /rollback

Asks the agent to undo file changes. The agent can list and
revert file snapshots automatically using the undo tool.

See also: undo (tool)""",
    "config": """\
Usage: /config

Shows the current configuration: model, max tokens, temperature,
top-p, base URL, and custom persona (if set).""",
    "prompt": """\
Usage:
  /prompt list              List all prompt templates
  /prompt load <name>       Load a prompt template
  /prompt save <name>       Save last assistant response as a prompt

Includes built-in templates: refactor, fix-bug, add-feature,
write-tests, code-review. Custom templates are stored in prompts/.""",
    "profile": """\
Usage:
  /profile list             List all saved configuration profiles
  /profile load <name>      Load a configuration profile
  /profile save <name>      Save current config as a profile
  /profile delete <name>    Delete a configuration profile

Profiles store model, max_tokens, temperature, top_p, and persona.""",
    "changes": """\
Usage: /changes

Shows the session change log (audit trail) of all file modifications
made during the session via write_file, edit_file, and replace_in_files.

The log is in-memory only and is lost when the session ends.""",
    "open": """\
Usage: /open <partial-filename>

Fuzzy-finds and opens a file by partial name. Walks the project tree
(skipping hidden directories) and shows matching files.
If exactly one match is found, it is auto-opened with a preview.

Examples:
  /open main               Find files with "main" in the name
  /open utils              Find files with "utils" in the name""",
    "python": """\
Usage: /python

Shows the Python REPL state: number of executions, errors, and
defined variables. The python tool is available to the agent for
executing code snippets.

See also: /reset-python""",
    "reset-python": """\
Usage: /reset-python

Resets the Python REPL, clearing all variables, execution history,
and error count.

See also: /python""",
    "deps": """\
Usage: /deps <file>

Shows what a Python file imports (its dependencies). Uses static
analysis with the ast module. Only shows project-internal
dependencies (standard library and third-party imports are excluded).

See also: /impact""",
    "impact": """\
Usage: /impact <file>

Shows what files import the given file (impact analysis). This
helps understand the blast radius of changes to a file.

See also: /deps""",
    "mcp": """\
Usage: /mcp

Shows the status of all configured MCP (Model Context Protocol) servers:
- Connection status (connected/disconnected)
- Number of tools available from each server
- Individual tool names and descriptions

MCP servers are configured in config.json under the "mcpServers" key.
See the project documentation for configuration examples.""",
}


def _contains_markdown(text: str) -> bool:
    """Check if text contains Markdown formatting that would benefit from rich rendering."""
    import re as _re
    # Check for common Markdown patterns
    patterns = [
        r"```",           # Code blocks
        r"^#{1,6}\s",     # Headings (at start of line)
        r"\*\*[^*]+\*\*", # Bold
        r"\*[^*]+\*",     # Italic
        r"^[-*+]\s",      # Unordered lists
        r"^\d+\.\s",      # Ordered lists
        r"\[.+\]\(.+\)",  # Links
        r"\|.+\|.+\|",    # Tables
        r"^>\s",          # Blockquotes
        r"---",           # Horizontal rules
        r"`[^`]+`",       # Inline code
    ]
    return any(bool(_re.search(p, text, _re.MULTILINE)) for p in patterns)


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
        self._python_repl: "PythonRepl | None" = None
        self._import_graph = ImportGraph()
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
        self._tool_execution_timeout: int = 120  # seconds
        self._consecutive_tool_failures: int = 0
        self._last_mode: str = "code"  # track for mode-change announcements
        self._mode_changed_via_command: bool = False

        # MCP bridge for Model Context Protocol servers
        self._mcp_bridge: MCPBridge | None = None
        self._mcp_servers_config: list[dict[str, object]] = mcp_servers or []

        # Rate limit tracking
        self._rate_limit_events: int = 0
        self._pending_input: str | None = None
        self._confirm_edits: bool = False

        # Per-turn latency timeline
        self._turn_timeline: list[dict[str, object]] = []
        self._current_turn_tools: list[dict[str, object]] = []
        self._current_llm_start: float = 0.0
        self._turn_start_time: float = 0.0

        self.tools = ToolRegistry()
        self._register_all_tools()
        self._auto_save_interval = 0
        self._turns_since_auto_save = 0
        self._last_auto_save_path: str | None = None

        # Initialize the agent orchestrator for multi-agent support
        self._orchestrator = Orchestrator(
            default_llm=self.llm,
            default_system_prompt=self._get_orchestrator_system_prompt(),
            default_working_directory=self.working_directory,
        )

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
        self.tools.register(python_tool)
        self.tools.register(write_plan_tool)
        self.tools.register(complete_plan_tool)
        self.tools.register(ask_user_tool)
        self.tools.register(syntax_check_tool)
        self.tools.register(verify_content_tool)
        self.tools.register(config_tool)
        self.tools.register(git_log_tool)
        self.tools.register(environment_tool)
        # Multi-agent tools
        self.tools.register(spawn_agent_tool)
        self.tools.register(list_agents_tool)
        self.tools.register(send_to_agent_tool)
        self.tools.register(terminate_agent_tool)
        self.tools.register(run_swarm_tool)
        # New Wave 1 tools
        self.tools.register(git_revert_tool)
        self.tools.register(rename_file_tool)
        self.tools.register(git_branch_tool)
        self.tools.register(api_tool)
        self.tools.register(precommit_tool)
        self.tools.register(ci_tool)
        self.tools.register(db_tool)
        self.tools.register(docker_tool)
        # Load custom tools from config
        if self._custom_tools_config:
            custom_tools = load_custom_tools(self._custom_tools_config, self.working_directory)
            for ct in custom_tools:
                self.tools.register(ct)
            if custom_tools:
                logger.info("Registered %d custom tool(s)", len(custom_tools))

        # Load MCP tools from configured servers
        if self._mcp_servers_config:
            try:
                self._mcp_bridge = MCPBridge(self._mcp_servers_config)
                mcp_tools = self._mcp_bridge.start()
                for t in mcp_tools:
                    self.tools.register(t)
                if mcp_tools:
                    logger.info(
                        "Registered %d MCP tool(s) from %d server(s)",
                        len(mcp_tools), len(self._mcp_bridge.get_server_info()),
                    )
            except Exception as exc:
                logger.error("Failed to initialize MCP bridge: %s", exc)
                print(f"  {yellow('⚠')} {dim(f'MCP initialization failed: {exc}')}")

    def _execute_tool_with_timeout(
        self,
        tool: Tool,
        args: dict[str, object],
        context: ToolContext,
        timeout: int | None = None,
    ) -> str:
        """Execute a tool with a timeout. Returns the result or an error message.

        Uses a thread pool to enforce a maximum execution duration, preventing a
        single hung tool (e.g. a bash command that hangs indefinitely) from
        blocking the entire agent.
        """
        import concurrent.futures as _futures

        effective_timeout = timeout if timeout is not None else self._tool_execution_timeout
        try:
            with _futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(tool.execute, args, context)
                try:
                    return future.result(timeout=effective_timeout)
                except _futures.TimeoutError:
                    logger.error("Tool %s timed out after %ds", tool.name, effective_timeout)
                    return f"Error: Tool '{tool.name}' timed out after {effective_timeout} seconds."
        except Exception as exc:
            logger.error("Tool %s execution error: %s", tool.name, exc)
            return f"Error executing {tool.name}: {exc}"

    def _handle_interactive_tool(self, tool: Tool, args: dict[str, object]) -> str:
        """Handle an interactive tool that needs user input.

        Pauses the tool loop, displays the question, reads user response,
        and returns it as the tool result.
        """
        # Stop spinner if running
        if self._spinner is not None:
            self._spinner.stop()
            self._spinner = None

        question = str(args.get("question", str(args)))
        print()
        print(f"  {'─' * 60}")
        print(f"  {bold(yellow('❓ Agent needs clarification:'))}")
        print()
        for line in question.split("\n"):
            print(f"    {line}")
        print()
        print(f"  {bold('Your response:')} ", end="")
        try:
            response = input()
        except (EOFError, KeyboardInterrupt):
            response = "[User cancelled]"
        print(f"  {'─' * 60}")
        print()
        return response

    def _setup_tab_completion(self) -> None:
        """Set up tab completion for commands using readline."""
        if not _readline_available:
            return

        import readline as _readline  # type: ignore[import-untyped]

        # List of all available commands
        commands = [
            "/help", "/h", "/clear", "/c", "/tools", "/history", "/status", "/s",
            "/mode", "/plan", "/p", "/ask", "/a", "/code",
            "/plan", "/edit", "/retry", "/r", "/retry-auto", "/ra",
            "/save", "/load", "/sessions", "/persona", "/reload", "/restart",
            "/cost", "/export", "/search", "/model", "/cd", "/rollback",
            "/config", "/prompt", "/profile", "/changes", "/open",
            "/python", "/reset-python", "/deps", "/impact",
            "/q", "/exit",
        ]

        def _completer(text: str, state: int) -> str | None:
            """Readline completer function."""
            if not text.startswith("/"):
                return None

            # Filter commands by prefix
            candidates = [c for c in commands if c.startswith(text)]
            if state < len(candidates):
                return candidates[state] + " "
            return None

        _readline.set_completer(_completer)  # type: ignore[attr-defined]
        _readline.parse_and_bind("tab: complete")  # type: ignore[attr-defined]
        # Make sure tab completion works at the start of the line
        _readline.set_completer_delims(" \t\n")  # type: ignore[attr-defined]

    def start(self) -> None:
        print()
        print(f"  {bold('Coding Agent')} {dim('v0.6')}")
        print(f"  {dim('Type /help for commands, exit to quit.')}")
        print(f"  {dim('Model:')} {cyan(self.llm.model)}")
        print(f"  {dim('History:')} {cyan('enabled' if _readline_available else 'unavailable')} (up/down arrows)")
        print()
        self._print_separator()
        print()

        # Show MCP connection status
        if self._mcp_bridge and self._mcp_bridge.is_any_connected:
            for info in self._mcp_bridge.get_server_info():
                status = f"{green('● connected')}" if info["connected"] else f"{red('● disconnected')}"
                tool_count: int = int(info["tool_count"])  # type: ignore[arg-type]
                mcp_name: str = str(info["name"])
                print(f"  {dim('MCP:')} {cyan(mcp_name)} {status} {dim(f'({tool_count} tools)')}")
        print()

        self._setup_tab_completion()
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

            # Disconnect MCP servers on exit
            if self._mcp_bridge is not None:
                try:
                    self._mcp_bridge.disconnect_all()
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

            # Check for /editor trigger at empty prompt
            if not lines and raw.strip().lower() == "/editor":
                return self._open_external_editor()

            if raw.endswith("\\"):
                # Line continuation: strip trailing \ and collect
                lines.append(raw[:-1])
                continue

            lines.append(raw)
            break

        return "".join(lines)

    def _open_external_editor(self) -> str:
        """Open an external text editor for composing long messages.

        Uses $EDITOR or $VISUAL environment variable (Unix convention).
        Falls back to normal input if no editor is configured.
        Returns the edited content or '' if cancelled/empty.
        """
        import subprocess
        import tempfile

        editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
        if not editor:
            print(f"  {yellow('⚠')} {dim('No editor configured. Set $EDITOR or $VISUAL environment variable.')}")
            print(f"  {dim('Falling back to multi-line input (use \\ to continue lines).')}")
            return ""

        temp_path: str | None = None
        try:
            # Create a temporary file with instructions
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".md",
                encoding="utf-8",
                delete=False,
            ) as f:
                temp_path = f.name
                f.write("# Write your message below. Lines starting with # are ignored.\n")
                f.write("# Save and exit the editor when done.\n")
                f.write("# Close without saving to cancel.\n")

            # Launch the editor
            try:
                result = subprocess.call([editor, temp_path])
            except (OSError, FileNotFoundError) as exc:
                print(f"  {yellow('⚠')} {dim(f'Could not launch editor "{editor}": {exc}')}")
                print(f"  {dim('Falling back to multi-line input (use \\ to continue lines).')}")
                return ""

            if result != 0:
                print(f"  {yellow('⚠')} {dim('Editor exited with non-zero status. Cancelled.')}")
                return ""

            # Read the file back
            if temp_path is None:
                return ""
            try:
                with open(temp_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except (OSError, IOError) as exc:
                print(f"  {yellow('⚠')} {dim(f'Could not read editor output: {exc}')}")
                return ""

            # Strip comment lines and blank content
            lines: list[str] = []
            for line in content.split("\n"):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                lines.append(line)

            result_text = "\n".join(lines).strip()
            if not result_text:
                print(f"  {dim('Editor content was empty. Message cancelled.')}")
                return ""

            print(f"  {dim(f'✓ Content captured from editor ({len(result_text)} chars).')}")
            return result_text

        finally:
            # Clean up temp file
            if temp_path is not None:
                try:
                    os.unlink(temp_path)
                except (OSError, IOError):
                    pass

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
        trimmed = trim_messages(self.messages, self.max_tokens, current_system_tokens)
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
            )
            # Pass confirm-edits flag for the diff-review feature
            context.confirm_edits = self._confirm_edits

            text_started = False
            self._spinner = None
            # Accumulate full assistant response text for Markdown rendering
            _accumulated_text: list[str] = []
            # Track token usage for this turn
            tokens_before = sum(
                estimate_tokens(str(m.get("content", "")))
                for m in self.messages
            )

            def _on_text(text: str) -> None:
                nonlocal text_started
                # Stop spinner if still running (first text from LLM)
                if self._spinner is not None:
                    self._spinner.stop()
                    self._spinner = None
                if not text_started:
                    text_started = True
                    # Show streaming prefix
                    color_fn = self._turn_separator_color()
                    print(f"  {color_fn('┃')} ", end="", flush=True)
                print(text, end="", flush=True)
                _accumulated_text.append(text)

            def _restart_spinner() -> None:
                """Restart the spinner for the next LLM round (e.g. after tool results)."""
                nonlocal text_started
                text_started = False  # Reset so streaming prefix shows again
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
            # - Plan mode is always read-only
            # - Ask mode is always read-only
            # - Code mode has all tools available
            is_read_only = self.mode == "plan" or self.mode == "ask"

            # Set environment variables for the config tool to read
            os.environ["CODING_AGENT_MODE"] = self.mode
            os.environ["CODING_AGENT_MODEL"] = self.llm.model
            os.environ["CODING_AGENT_MAX_TOKENS"] = str(self.max_tokens)
            os.environ["CODING_AGENT_TEMPERATURE"] = str(self.llm.temperature)
            os.environ["CODING_AGENT_PERSONA"] = self._custom_persona or ""

            self.llm.chat_with_tools(
                messages=self.messages,
                system=system_prompt,
                tools=self.tools,
                context=context,
                on_text=_on_text,
                on_tool_call=self._on_tool_call,
                on_tool_result=lambda _name, r: self._on_tool_result(r, tool_name=_name),
                read_only=is_read_only,
                on_llm_round_start=lambda: _restart_spinner(),
                on_interactive_tool=self._handle_interactive_tool,
            )

            # ── Check for restart signal from restart_session tool ──────────
            if context.restart_requested:
                # Stop spinner if still running
                if self._spinner is not None:
                    self._spinner.stop()
                    self._spinner = None

                # ── Auto-complete any pending plans (safety net) ─────────────
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

            # ── Re-render final response as Markdown ─────────────────────────
            if _accumulated_text:
                full_text = "".join(_accumulated_text)
                # Process mermaid code blocks
                from .diagrams import process_mermaid_blocks
                full_text = process_mermaid_blocks(full_text)
                # Only re-render if it looks like it contains Markdown formatting
                if _contains_markdown(full_text):
                    print()  # Newline to end streaming line
                    render_markdown(full_text)

            # ── Finalize turn latency timeline ────────────────────────────
            llm_duration = time.time() - self._turn_start_time
            self._turn_timeline.append({
                "turn": len(self._turn_timeline) + 1,
                "llm_duration": llm_duration,
                "tools": list(self._current_turn_tools),
                "total_duration": time.time() - self._turn_start_time,
            })

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

            # ── Post-turn verification nudge (for code mode) ─────────────
            if self.mode == "code" and self._has_recent_file_changes():
                # Check if the assistant acknowledged doing verification
                last_asst = self._get_last_assistant_text()
                if last_asst and not any(
                    word in last_asst.lower() for word in ["verified", "verification", "check", "test", "confirm"]
                ):
                    print(f"  {yellow('💡')} {dim('Tip: Verify your changes with read_file, diff, or run_tests.')}")

        except json.JSONDecodeError:
            # Stop spinner if running
            if self._spinner is not None:
                self._spinner.stop()
                self._spinner = None
            last_msgs = self.messages[-3:] if len(self.messages) >= 3 else self.messages
            logger.error("JSON decode error in LLM response stream")
            print(f"\n  {red('✗ JSON Error:')} {dim('Failed to parse API response.')}")
            print(f"  {dim('This may indicate a transient API issue or malformed response data.')}")
            print(f"  {dim(f'Last {len(last_msgs)} message(s) preserved.')}")
            print(f"  {dim('Type')} {cyan('/retry')} {dim('to re-send your last message.')}")
        except anthropic.APIConnectionError:
            if self._spinner is not None:
                self._spinner.stop()
                self._spinner = None
            logger.error("API connection error")
            print(f"\n  {red('✗ Connection Error:')} {dim('Failed to connect to API.')}")
            print(f"  {dim('Check your internet connection and API endpoint.')}")
            print(f"  {dim('Type')} {cyan('/retry')} {dim('to re-send your last message.')}")
        except anthropic.RateLimitError:
            if self._spinner is not None:
                self._spinner.stop()
                self._spinner = None
            logger.error("Rate limit exceeded")
            print(f"\n  {red('✗ Rate Limited:')} {dim('API rate limit exceeded.')}")
            print(f"  {dim('Waiting before retry...')}")
            import time as _time
            _time.sleep(5)
            # Auto-retry the last message
            self._handle_retry()
        except anthropic.InternalServerError:
            if self._spinner is not None:
                self._spinner.stop()
                self._spinner = None
            logger.error("Anthropic internal server error")
            print(f"\n  {red('✗ Server Error:')} {dim('API internal server error.')}")
            print(f"  {dim('Waiting before retry...')}")
            import time as _time
            _time.sleep(3)
            self._handle_retry()
        except anthropic.APIError as api_err:
            if self._spinner is not None:
                self._spinner.stop()
                self._spinner = None
            logger.error("API error: %s", api_err)
            print(f"\n  {red('✗ API Error:')} {dim(str(api_err))}")
            print(f"  {dim('Type')} {cyan('/retry')} {dim('to re-send your last message.')}")
        except Exception as exc:
            # Stop spinner if running
            if self._spinner is not None:
                self._spinner.stop()
                self._spinner = None
            logger.error("Unexpected error in _process_turn: %s", exc, exc_info=True)
            print(f"\n  {red('✗ Error:')} {exc}")
            print(f"  {dim('Type')} {cyan('/retry')} {dim('to re-send your last message.')}")
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

        # ── Resilience instructions (CODE mode only) ─────────────────────────
        resilience_instruction = ""
        if self.mode == "code":
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
        if self.mode == "code":
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
            f"{resilience_instruction}"
            f"{multi_agent_instruction}"
            f"{context_section}"
        )

    def _get_orchestrator_system_prompt(self) -> str:
        """Return a base system prompt for the orchestrator (less decoration)."""
        return (
            f"Current working directory: {self.working_directory}\n"
            f"Project root: {self.working_directory}\n\n"
            f"{self.system_prompt}\n\n"
            f"Remember to explore the codebase with read-only tools before making changes."
        )

    def _on_tool_call(self, name: str, args: dict[str, object]) -> None:
        # Stop spinner if still running (LLM called a tool before generating text)
        if self._spinner is not None:
            self._spinner.stop()
            self._spinner = None

        args_str = color_json(args)
        color_fn = self._turn_separator_color()
        print(f"\n  {cyan('⚡')} {bold(name)}")
        # Only show args if they're non-trivial, to keep display clean
        if len(str(args)) > 4:  # more than just "{}"
            print(f"  {color_fn('│')}   {args_str}")

        # ── Track start time for notification timing ──────────────────────
        self._tool_start_time = time.time()

        # ── Track tool usage for statistics ───────────────────────────────
        self._tool_usage[name] = self._tool_usage.get(name, 0) + 1

        # ── Log file modifications for audit trail ─────────────────────────
        if name in ("write_file", "edit_file", "replace_in_files"):
            from datetime import datetime as _dt
            ts = _dt.now().isoformat()
            path_arg = str(args.get("path", ""))
            summary = ""
            if name == "write_file":
                summary = f"Created/overwrote: {path_arg}"
            elif name == "edit_file":
                summary = f"Edited: {path_arg}"
            elif name == "replace_in_files":
                old = str(args.get("oldText", ""))[:40]
                summary = f"Bulk replace '{old}...' in {path_arg}"
            self._change_log.append({
                "timestamp": ts,
                "tool": name,
                "path": path_arg,
                "summary": summary,
            })

    def _on_tool_result(self, result: str, tool_name: str = "") -> None:
        is_error = result.startswith("Error:")

        # Record tool execution in the current turn timeline
        if tool_name and self._tool_start_time > 0:
            duration = time.time() - self._tool_start_time
            self._current_turn_tools.append({
                "name": tool_name,
                "duration": duration,
                "error": is_error,
            })

        # Track consecutive tool failures
        if is_error:
            self._consecutive_tool_failures += 1
        else:
            self._consecutive_tool_failures = 0

        truncated = len(result) > 250
        preview = result if not truncated else result[:250]
        suffix = ""
        if truncated:
            suffix = f" {dim(f'[+{len(result) - 250} more chars]')}"

        # Show elapsed time for the tool
        elapsed_str = ""
        if self._tool_start_time > 0:
            elapsed = time.time() - self._tool_start_time
            elapsed_str = f" {dim(f'┄ {elapsed:.1f}s')}"
            # Track duration per tool
            if tool_name and tool_name not in self._tool_durations:
                self._tool_durations[tool_name] = []
            if tool_name:
                self._tool_durations[tool_name].append(elapsed)

        # Track errors
        if is_error and tool_name:
            self._tool_errors[tool_name] = self._tool_errors.get(tool_name, 0) + 1

        if is_error:
            print(f"  {red('✗')} {red(preview)}{suffix}{elapsed_str}")
        else:
            print(f"  {green('✓')} {dim(preview)}{suffix}{elapsed_str}")

        # ── Desktop notification for long-running tools ───────────────────
        if self._notifications_enabled and hasattr(self, "_tool_start_time"):
            elapsed = time.time() - self._tool_start_time
            if should_notify(elapsed, self._notifications_min_duration):
                tool_display = tool_name or "Tool"
                notify(
                    title=f"Coding Agent: {tool_display}",
                    message=f"Completed in {elapsed:.1f}s",
                )
                # Audio notification (best-effort, no config toggle for now)
                play_sound()

    # ── Snippet command handlers ──────────────────────────────────────────

    def _handle_snippet(self, args: str) -> None:
        """Handle /snippet commands."""
        parts = args.strip().split(maxsplit=1)
        subcommand = parts[0].lower() if parts else ""
        rest = parts[1] if len(parts) > 1 else ""

        if subcommand == "list":
            snippets = list_snippets()
            if not snippets:
                print("  No snippets saved.")
                return
            print(f"\n  {bold('Saved Snippets')}")
            for s in snippets:
                desc = f" — {s['description']}" if s['description'] else ""
                size_str = self._format_size(s['size'])
                print(f"  {green(s['name'])}{desc} ({size_str})")

        elif subcommand == "save":
            if not rest:
                print("  Usage: /snippet save <name>")
                return
            # Save the last assistant response as a snippet
            last_response = self._get_last_assistant_response()
            if not last_response:
                print("  No assistant response to save.")
                return
            if save_snippet(rest, last_response):
                print(f"  {green('✓')} Saved snippet: {rest}")

        elif subcommand == "load":
            if not rest:
                print("  Usage: /snippet load <name>")
                return
            content = load_snippet(rest)
            if content is None:
                print(f"  {red('✗')} Snippet not found: {rest}")
                return
            print(f"\n  {bold(f'Snippet: {rest}')}")
            print(content)

        elif subcommand == "delete":
            if not rest:
                print("  Usage: /snippet delete <name>")
                return
            if delete_snippet(rest):
                print(f"  {green('✓')} Deleted snippet: {rest}")
            else:
                print(f"  {red('✗')} Snippet not found: {rest}")

        elif subcommand == "apply":
            if not rest:
                print("  Usage: /snippet apply <name>")
                return
            content = load_snippet(rest)
            if content is None:
                print(f"  {red('✗')} Snippet not found: {rest}")
                return
            # Insert snippet into user input buffer (next message)
            self._pending_input = content
            print(f"  {green('✓')} Loaded snippet '{rest}' — press Enter to send")

        else:
            print("  Usage: /snippet [list|save|load|delete|apply] <name>")

    def _get_last_assistant_response(self) -> str:
        """Get the last assistant text response."""
        return self._get_last_assistant_text()

    def _format_size(self, bytes_size: int) -> str:
        """Format file size in human-readable format."""
        size = float(bytes_size)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"

    # ── Diff review command ──────────────────────────────────────────────

    def _handle_diff_review(self, args: str = "") -> None:
        """Toggle interactive diff review mode."""
        parts = args.strip().split()
        if parts and parts[0].lower() == "on":
            self._confirm_edits = True
        elif parts and parts[0].lower() == "off":
            self._confirm_edits = False
        else:
            self._confirm_edits = not self._confirm_edits
        status = green("ON") if self._confirm_edits else dim("OFF")
        print(f"  Diff review mode: {status}")

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
            print()
            try:
                confirm = input(f"  {bold('Send this prompt as your message?')} {dim('[Y/n]')} ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                confirm = "n"
            if confirm in ("", "y", "yes"):
                self._turn_number += 1
                color_fn = self._turn_separator_color()
                self._process_turn(prompt.content, color_fn)

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

    def _handle_retry_auto(self) -> None:
        """Re-send the last user message with an escalation prompt.

        Adds an instruction telling the agent to "try harder" or use a different
        approach if previous attempts failed.
        """
        idx = self._get_last_user_index()
        if idx is None:
            print(f"  {dim('No previous user message to retry.')}")
            return

        content = cast("str", self.messages[idx].get("content", ""))
        # Remove everything after the last user message
        self.messages = self.messages[: idx + 1]

        # Add an escalation instruction
        self._task_attempts += 1
        escalation = (
            f"\n\n[IMPORTANT: Previous attempt(s) did not complete all requested tasks. "
            f"This is attempt #{self._task_attempts}. Please be thorough, check your work, "
            f"and ensure ALL aspects of the request are completed. If a previous approach "
            f"failed, try a different strategy. Verify each step before proceeding.]"
        )
        self.messages.append({"role": "user", "content": content + escalation})

        print(f"  {yellow('⟳')} {dim(f'Retrying with escalation (attempt {self._task_attempts})...')}")
        print()
        color_fn = self._turn_separator_color()
        turn_label = f"  {color_fn('─ ')}Turn {self._turn_number}{color_fn(' ' + '─' * (56 - len(str(self._turn_number))))}"
        print(turn_label)
        self._process_turn(content + escalation, color_fn)

    def _has_recent_file_changes(self) -> bool:
        """Check if the most recent assistant turn included file modifications."""
        if not self._change_log:
            return False
        # Simple heuristic: check the last 3 change log entries
        recent = self._change_log[-3:]
        for entry in recent:
            tool = str(entry.get("tool", ""))
            if tool in ("write_file", "edit_file", "replace_in_files"):
                return True
        return False

    def _handle_timeline(self) -> None:
        """Display the per-turn latency timeline (LLM vs tool execution times)."""
        if not self._turn_timeline:
            print(f"  {dim('No timeline data yet.')}")
            return

        print(f"\n  {bold('Per-Turn Latency Timeline')}")
        print(f"  {'─' * 60}")

        max_total = max(e["total_duration"] for e in self._turn_timeline)  # type: ignore[typeddict-item]
        bar_scale = 30 / max(max_total, 0.001)

        for entry in self._turn_timeline:
            turn: int = int(entry.get("turn", 0))  # type: ignore[assignment]
            total: float = float(entry.get("total_duration", 0))  # type: ignore[assignment]
            llm_dur: float = float(entry.get("llm_duration", 0))  # type: ignore[assignment]
            tools_raw = entry.get("tools", [])
            tools_list: list[dict[str, object]] = tools_raw if isinstance(tools_raw, list) else []  # type: ignore[assignment]

            bar_len = int(total * bar_scale)
            bar = "█" * bar_len

            print(f"  Turn {turn}: {cyan(bar)} {bold(f'{total:.1f}s')}")

            # Breakdown
            llm_pct = (llm_dur / total * 100) if total > 0 else 0
            print(f"    {cyan('LLM')}:     {llm_dur:.1f}s ({llm_pct:.0f}%)")

            for tool in tools_list:
                t_dur: float = float(tool.get("duration", 0))  # type: ignore[assignment]
                t_name: str = str(tool.get("name", "?"))
                t_err: str = " ⚠" if bool(tool.get("error", False)) else ""
                t_pct: float = (t_dur / total * 100) if total > 0 else 0
                print(f"    {green(t_name)}: {t_dur:.1f}s ({t_pct:.0f}%){t_err}")

    def _handle_reload(self) -> None:
        """Re-discover and re-register all tools from disk."""
        spinner = Spinner("Reloading tools...")
        spinner.start()
        try:
            count = self.tools.rebuild()
            spinner.stop(f"  {green('✓')} {dim(f'Reloaded {count} tools.')}")
            # Show the freshly loaded tools
            for t in self.tools.get_all():
                ro = f" {dim('(read-only)')}" if t.read_only else ""
                print(f"    {bold(t.name)}{dim(f' — {t.description}')}{ro}")
        except Exception as exc:
            spinner.stop(f"  {red('✗ Error reloading tools:')} {exc}")

    # ── New feature handlers ────────────────────────────────────────────

    def _estimated_cost(self) -> float:
        """Return estimated total API cost in USD."""
        pricing = MODEL_PRICING.get(self.llm.model, {"input": 0.50, "output": 0.50})
        in_cost = (self._input_tokens_total / 1_000_000) * pricing["input"]
        out_cost = (self._output_tokens_total / 1_000_000) * pricing["output"]
        return in_cost + out_cost

    def _handle_stats(self) -> None:
        """Handle /stats command — show session statistics."""
        elapsed = time.time() - self._start_time
        hours, remainder = divmod(int(elapsed), 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s" if hours else f"{minutes}m {seconds}s"

        total_turns = sum(self._turns_by_mode.values())
        total_tokens = sum(
            estimate_tokens(str(m.get("content", "")))
            for m in self.messages
        )
        system_prompt = self._get_system_prompt()
        system_tokens = estimate_tokens(system_prompt)
        avg_tokens_per_turn = total_tokens // max(total_turns, 1)

        print(f"  {bold('Session Statistics')}")
        print()
        print(f"  {dim('Session duration:')}  {cyan(uptime_str)}")
        print(f"  {dim('Total turns:')}      {cyan(str(total_turns))}")
        print(f"  {dim('Total messages:')}   {cyan(str(len(self.messages)))}")
        print(f"  {dim('Total tokens:')}     {cyan(str(total_tokens + system_tokens))} ({dim('~' + str(avg_tokens_per_turn) + ' avg/turn')})")
        print(f"  {dim('Mode switches:')}    {cyan(str(self._mode_switches))}")
        print()

        # Turns per mode
        print(f"  {bold('Turns by Mode')}")
        for mode_name in ("code", "plan", "ask"):
            count = self._turns_by_mode.get(mode_name, 0)
            if mode_name == "code":
                color_fn = green
            elif mode_name == "plan":
                color_fn = yellow
            else:
                color_fn = magenta
            bar_len = max(1, count) if count > 0 else 0
            bar = "█" * min(bar_len, 30)
            print(f"  {color_fn(mode_name.upper().ljust(6))} {dim(bar)} {cyan(str(count))}")
        print()

        # Tool usage
        if self._tool_usage:
            print(f"  {bold('Tool Usage')}")
            max_count = max(self._tool_usage.values())
            for tool_name, count in sorted(self._tool_usage.items(), key=lambda x: -x[1]):
                bar_len = int((count / max(1, max_count)) * 20)
                bar = "█" * bar_len
                durations = self._tool_durations.get(tool_name, [])
                avg_dur = sum(durations) / len(durations) if durations else 0
                errors = self._tool_errors.get(tool_name, 0)
                error_str = f"  errors: {errors}" if errors else ""
                print(f"  {cyan(tool_name.ljust(20))} {dim(bar)} {cyan(str(count).ljust(4))} {dim(f'avg {avg_dur:.2f}s')} {red(error_str) if errors else dim(error_str)}")
        else:
            print(f"  {dim('No tools have been called yet.')}")
        print()
        print(f"  {dim('Estimated cost:')}  {dim(f'${self._estimated_cost():.4f}')}")

    def _handle_changes(self) -> None:
        """Handle /changes command — show session change log."""
        if not self._change_log:
            print(f"  {dim('No changes recorded yet.')}")
            print(f"  {dim('File modifications via write_file, edit_file, or replace_in_files')}")
            print(f"  {dim('will appear here as they happen.')}")
            return

        print(f"  {bold('Session Change Log')}  {dim(f'({len(self._change_log)} changes)')}")
        print()
        for entry in self._change_log:
            ts = str(entry.get("timestamp", ""))
            if len(ts) > 19:
                ts = ts[:19]
            tool_name = str(entry.get("tool", "?"))
            path = str(entry.get("path", ""))
            summary = str(entry.get("summary", ""))
            rel_path = path
            if self.working_directory and path:
                try:
                    rel_path = os.path.relpath(str(path), self.working_directory)
                except (ValueError, OSError):
                    pass
            print(f"  {dim(ts)} {cyan(tool_name):<18} {dim(rel_path)}")
            if summary:
                print(f"  {' ' * 20} {yellow(summary[:100])}")

    def _handle_open(self, parts: list[str]) -> None:
        """Handle /open command — interactive file finder with inline preview."""
        if len(parts) < 2:
            print(f"  {dim('Usage: /open <partial-filename>')}")
            print(f"  {dim('Searches the project tree for files matching the given name.')}")
            return

        query = " ".join(parts[1:]).strip()
        if not query:
            print(f"  {dim('Usage: /open <partial-filename>')}")
            return

        query_lower = query.lower()
        matches: list[tuple[str, str]] = []

        try:
            for root, dirs, files in os.walk(self.working_directory):
                # Skip hidden directories
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for filename in files:
                    if query_lower in filename.lower():
                        full_path = os.path.join(root, filename)
                        rel_path = os.path.relpath(full_path, self.working_directory)
                        matches.append((rel_path, full_path))
                        if len(matches) >= 50:
                            break
                if len(matches) >= 50:
                    break
        except (OSError, PermissionError) as exc:
            print(f"  {red('✗ Error searching:')} {exc}")
            return

        if not matches:
            print(f"  {dim('No files found matching:')} {cyan(query)}")
            return

        # Sort: name starts-with-query first, then alphabetical
        def _sort_key(item: tuple[str, str]) -> tuple[int, str]:
            relpath = item[0]
            basename = os.path.basename(relpath)
            priority = 0 if basename.lower().startswith(query_lower) else 1
            return (priority, relpath.lower())

        matches.sort(key=_sort_key)

        # Auto-open if exactly 1 match
        if len(matches) == 1:
            rel_path, full_path = matches[0]
            print(f"  {green('✓')} {dim('Opened:')} {cyan(rel_path)}")
            print()
            self._preview_file(full_path)
            return

        # Show numbered results with file icons and sizes
        print(f"\n  {bold(f'Files matching \"{query}\"')}  ({dim(str(len(matches)) + ' found')})")
        print(f"  {'─' * 60}")

        for i, (rel_path, full_path) in enumerate(matches[:20], 1):
            try:
                size = os.path.getsize(full_path)
                size_str = self._format_size(size)
            except OSError:
                size_str = "?"
            icon = self._get_file_icon(rel_path)
            print(f"  {cyan(f'{i:2d}.')} {icon} {cyan(rel_path)}  {dim(f'({size_str})')}")

        if len(matches) > 20:
            print(f"  {dim(f'... and {len(matches) - 20} more matches')}")

        # Interactive selection
        print(f"\n  {yellow('Select file number')} (or press Enter to cancel): ", end="", flush=True)
        try:
            choice = input().strip()
            if not choice:
                return
            idx = int(choice) - 1
            if 0 <= idx < min(len(matches), 20):
                self._preview_file(matches[idx][1])
            else:
                print(f"  {red('✗')} Invalid selection: {choice}")
        except ValueError:
            print(f"  {red('✗')} Invalid input")
        except (EOFError, KeyboardInterrupt):
            print()

    # ── File preview helpers ─────────────────────────────────────────────

    @staticmethod
    def _get_file_icon(filepath: str) -> str:
        """Get an emoji icon for a file based on its extension."""
        _, ext = os.path.splitext(filepath)
        icons = {
            ".py": "🐍", ".js": "📜", ".ts": "📘", ".tsx": "⚛️",
            ".jsx": "⚛️", ".json": "📋", ".md": "📝", ".yaml": "⚙️",
            ".yml": "⚙️", ".html": "🌐", ".css": "🎨", ".sh": "💻",
            ".sql": "🗃️", ".toml": "⚙️", ".ini": "⚙️",
        }
        return icons.get(ext.lower(), "📄")

    def _preview_file(self, filepath: str) -> None:
        """Show a file preview with line numbers and metadata."""
        print(f"\n  {bold(f'File: {filepath}')}")
        print(f"  {'─' * 60}")

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()

            max_preview = 30
            for i, line in enumerate(lines[:max_preview], 1):
                line_num = dim(f"{i:4d}")
                print(f"  {line_num}│{line.rstrip()}")

            if len(lines) > max_preview:
                remaining = len(lines) - max_preview
                print(f"  {dim(f'... and {remaining} more lines')}")

            # Show file metadata
            try:
                size = os.path.getsize(filepath)
                print(f"\n  {dim(f'{len(lines)} lines, {self._format_size(size)}')}")
            except OSError:
                pass

        except Exception as e:
            print(f"  {red(f'Error reading file: {e}')}")

    def _display_file_preview(self, filepath: str) -> None:
        """Display the first 30 lines of a file (legacy, delegates to _preview_file)."""
        self._preview_file(filepath)

    def _get_or_create_python_repl(self) -> "PythonRepl":
        """Get or create the shared Python REPL instance."""
        if self._python_repl is None:
            from src.python_repl import PythonRepl
            self._python_repl = PythonRepl()
        return self._python_repl

    def _handle_python(self) -> None:
        """Handle /python command — show Python REPL state."""
        repl = self._get_or_create_python_repl()
        print(f"  {bold('Python REPL')}")
        print(f"  {dim('Executions:')} {cyan(str(repl.execution_count))}")
        print(f"  {dim('Errors:')}     {cyan(str(repl.error_count))}")
        print(f"  {dim('Variables:')}  {cyan(str(len(repl.get_variables())))}")
        print()
        print(f"  {dim('The python tool is available to the agent.')}")
        print(f"  {dim('Use the tool with: {\"code\": \"print(1+1)\"}')}")
        print(f"  {dim('Type /reset-python to clear REPL state.')}")

    def _handle_reset_python(self) -> None:
        """Handle /reset-python command — reset the Python REPL."""
        repl = self._get_or_create_python_repl()
        repl.reset()
        print(f"  {green('✓')} {dim('Python REPL reset. All variables cleared.')}")

    def _ensure_import_graph_built(self) -> None:
        """Build the import graph if it hasn't been built yet."""
        if not self._import_graph._built:
            spinner = Spinner("Building import graph...")
            spinner.start()
            try:
                self._import_graph.build(self.working_directory)
                files = len(self._import_graph.get_all_files())
                spinner.stop(f"  {green('✓')} {dim(f'Import graph built ({files} files).')}")
            except Exception as exc:
                spinner.stop(f"  {red('✗ Error building import graph:')} {exc}")

    def _handle_deps(self, parts: list[str]) -> None:
        """Handle /deps command — show what a file imports."""
        self._ensure_import_graph_built()

        if len(parts) < 2:
            print(f"  {dim('Usage: /deps <file>')}")
            print(f"  {dim('Shows what the given Python file imports.')}")
            return

        raw_path = " ".join(parts[1:]).strip()
        filepath = self._resolve_relative_path(raw_path)
        if filepath is None:
            print(f"  {dim('File not found:')} {cyan(raw_path)}")
            return

        relpath = os.path.relpath(filepath, self.working_directory)
        deps = self._import_graph.get_dependencies(relpath)
        if not deps:
            print(f"  {dim('No project dependencies found for:')} {cyan(relpath)}")
            print(f"  {dim('(Standard library and third-party imports are excluded)')}")
            return

        print(f"  {bold(f'Dependencies of {relpath}:')}  {dim(f'({len(deps)} files)')}")
        print()
        for dep in deps:
            print(f"  {cyan('◈')} {dim(dep)}")

    def _handle_impact(self, parts: list[str]) -> None:
        """Handle /impact command — show what imports a file (impact analysis)."""
        self._ensure_import_graph_built()

        if len(parts) < 2:
            print(f"  {dim('Usage: /impact <file>')}")
            print(f"  {dim('Shows which files import the given file (impact analysis).')}")
            return

        raw_path = " ".join(parts[1:]).strip()
        filepath = self._resolve_relative_path(raw_path)
        if filepath is None:
            print(f"  {dim('File not found:')} {cyan(raw_path)}")
            return

        relpath = os.path.relpath(filepath, self.working_directory)
        dependents = self._import_graph.get_dependents(relpath)
        if not dependents:
            print(f"  {dim('No files in the project import:')} {cyan(relpath)}")
            return

        print(f"  {bold(f'Impact analysis for {relpath}:')}  {dim(f'({len(dependents)} dependents)')}")
        print()
        for dep in dependents:
            print(f"  {yellow('◈')} {dim(dep)}")

    def _resolve_relative_path(self, raw_path: str) -> str | None:
        """Resolve a user-provided path relative to working_directory."""
        candidate = os.path.join(self.working_directory, raw_path)
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)
        # Try with .py extension
        candidate_py = candidate + ".py"
        if os.path.isfile(candidate_py):
            return os.path.abspath(candidate_py)
        return None

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
        """Handle /export command — export conversation as Markdown, JSON, or full .agent-session."""
        fmt = "md"
        output_path: str | None = None
        if len(parts) > 1:
            arg = parts[1].strip().lower()
            if arg == "session":
                fmt = "session"
                if len(parts) > 2:
                    output_path = parts[2]
            elif arg in ("json", "md"):
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
            if fmt == "session":
                from .exporter import export_full_session, load_session_file, export_summary
                from datetime import datetime as _dt

                filename = output_path or f"session_{_dt.now().strftime('%Y%m%d_%H%M%S')}.agent-session"
                if not filename.endswith(".agent-session"):
                    filename += ".agent-session"

                # Gather session data
                metadata = {
                    "model": self.llm.model,
                    "mode": self.mode,
                    "messages": len(self.messages),
                }

                result = export_full_session(
                    output_path=os.path.join(os.getcwd(), filename),
                    messages=list(self.messages),
                    metadata=metadata,
                    working_directory=self.working_directory,
                )

                if result.endswith(".agent-session"):
                    size = self._format_size(os.path.getsize(result))
                    print(f"  {green('✓')} Session exported: {result} ({size})")
                    # Show summary
                    data = load_session_file(result)
                    if data:
                        print(export_summary(data))
                else:
                    print(f"  {red('✗')} {result}")
            elif fmt == "json":
                filepath = export_as_json(self.messages, self.mode, self.llm.model, output_path)
                print(f"  {green('✓')} {dim('Exported to')} {cyan(filepath)}")
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

        # Show MCP server status
        if self._mcp_bridge and self._mcp_servers_config:
            print(f"  {dim('MCP servers:')}")
            for info in self._mcp_bridge.get_server_info():
                status_label = f"{green('connected')}" if info["connected"] else f"{red('disconnected')}"
                transport: str = str(info["transport"])
                mcp_cfg_name: str = str(info["name"])
                print(f"    {dim('·')} {cyan(mcp_cfg_name)} {dim(f'({transport})')} {dim(status_label)}")

    def _handle_mcp(self) -> None:
        """Show MCP server connection status and tools."""
        if not self._mcp_bridge:
            print(f"  {dim('No MCP servers configured.')}")
            print(f"  {dim('Add mcpServers to config.json to connect.')}")
            return

        infos: list[dict[str, Any]] = self._mcp_bridge.get_server_info()
        if not infos:
            print(f"  {dim('No MCP servers configured.')}")
            return

        total = int(sum(i['tool_count'] for i in infos))  # type: ignore[arg-type]
        connected = int(sum(1 for i in infos if i['connected']))
        print(f"  {bold('MCP Servers')}  {dim(f'({connected}/{len(infos)} connected, {total} tools)')}")
        print()
        for info in infos:
            status_symbol = green('●') if info['connected'] else red('○')
            status_label = green('Connected') if info['connected'] else red('Disconnected')
            name: str = str(info['name'])
            print(f"  {status_symbol} {cyan(name)}  {dim(status_label)}")
            if info['connected'] and info['tools']:
                tools_list: list[dict[str, Any]] = info['tools']  # type: ignore[assignment]
                for t in tools_list:
                    t_name: str = str(t.get('name', ''))
                    t_desc: str = str(t.get('description', ''))
                    print(f"     {dim('·')} {t_name}  {dim(t_desc[:60])}")
            if info.get('error'):
                err: str = str(info['error'])
                print(f"     {red('✗')} {dim(err)}")

    # ── Backup command handlers ──────────────────────────────────────────

    def _handle_backup(self, args: str) -> None:
        """Handle /backup commands."""
        from .backup import create_backup, list_backups, restore_backup, clean_backups

        parts = args.strip().split(maxsplit=1)
        subcmd = parts[0].lower() if parts else ""
        rest = parts[1] if len(parts) > 1 else ""

        if subcmd == "list":
            backups = list_backups()
            if not backups:
                print("  No backups found.")
                return
            print(f"\n  {bold('Available Backups')}")
            print(f"  {'─' * 50}")
            for b in backups:
                created = b["created"].strftime("%Y-%m-%d %H:%M") if b["created"] else "?"
                print(f"  {green(b['name'])}  {dim(b['type'])}  {b['size']}  {created}")

        elif subcmd == "restore":
            if not rest:
                print("  Usage: /backup restore <name>")
                return
            result = restore_backup(rest, self.working_directory)
            print(f"  {result}")

        elif subcmd == "clean":
            count = int(rest) if rest.isdigit() else 5
            result = clean_backups(count)
            print(f"  {result}")

        else:
            # Create backup
            label = subcmd if subcmd else ""
            result = create_backup(self.working_directory, label=label)
            print(f"  {result}")

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
                # Check for subcommand
                cmd_lower = cmd.lower().strip()
                parts_help = cmd_lower.split(maxsplit=1)
                if len(parts_help) > 1:
                    topic = parts_help[1].lstrip("/")
                    if topic in COMMAND_HELP:
                        print(f"  {bold(f'Help: /{topic}')}")
                        print()
                        for line in COMMAND_HELP[topic].split("\n"):
                            print(f"  {line}")
                    else:
                        print(f"  {dim('No detailed help available for:')} {cyan('/' + topic)}")
                        print(f"  {dim('Use /help to see all available commands.')}")
                else:
                    print(HELP_TEXT)
            case "/clear" | "/c":
                self.messages.clear()
                print(f"  {dim('Conversation history cleared.')}")
            case "/tools":
                tools_to_show = self.tools.get_read_only() if self.mode in ("plan", "ask") else self.tools.get_all()
                for t in tools_to_show:
                    is_mcp = "/" in t.name and self._mcp_bridge is not None and self._mcp_bridge.is_any_connected
                    tag = f" {cyan('[MCP]')}" if is_mcp else ""
                    print(f"  {bold(t.name)}{tag}{dim(f' — {t.description}')}")
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
                if self._mcp_bridge and self._mcp_bridge.is_any_connected:
                    total = self._mcp_bridge.total_tool_count
                    count = len(self._mcp_bridge.get_server_info())
                    print(f"  {dim('MCP:')}      {cyan(f'{total} tools from {count} server(s)')}")
                if self._rate_limit_events > 0:
                    print(f"  {dim('Rate limit events:')} {cyan(str(self._rate_limit_events))}")
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
                        self._mode_switches += 1
                        self._mode_changed_via_command = True
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
                    self._mode_switches += 1
                    self._mode_changed_via_command = True
                    logger.info("Switched to ASK mode")
                    print(f"  {magenta('●')} {bold('ASK mode')} {dim('— read-only Q&A. Only read-only tools are available.')}")
                    print(f"  {dim('Use /code to switch back to CODE mode.')}")
            case "/code":
                if self.mode == "code":
                    print(f"  {dim('Already in code mode.')}")
                else:
                    self.mode = "code"
                    self._mode_switches += 1
                    self._mode_changed_via_command = True
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
            case "/retry-auto" | "/ra":
                self._handle_retry_auto()
            case "/cost":
                self._handle_cost()
            case "/stats":
                self._handle_stats()
            case "/cd":
                self._handle_cd(parts)
            case "/rollback":
                print(f"  {dim('Use the undo tool to rollback changes.')}")
                print(f"  {dim('The agent can list and revert file snapshots automatically.')}")
            case "/backup":
                self._handle_backup(cmd.split(maxsplit=1)[1] if len(cmd.split(maxsplit=1)) > 1 else "")
            case "/timeline":
                self._handle_timeline()
            case "/mcp":
                self._handle_mcp()
            case "/model":
                self._handle_model(parts)
            case "/search":
                self._handle_search(parts)
            case "/snippet":
                self._handle_snippet(cmd.split(maxsplit=1)[1] if len(cmd.split(maxsplit=1)) > 1 else "")
            case "/diff-review":
                self._handle_diff_review(cmd.split(maxsplit=1)[1] if len(cmd.split(maxsplit=1)) > 1 else "")
            case "/export":
                self._handle_export(parts)
            case "/config":
                self._handle_config()
            case "/prompt":
                self._handle_prompt(cmd)
            case "/profile":
                self._handle_profile(cmd)
            case "/changes":
                self._handle_changes()
            case "/open":
                self._handle_open(parts)
            case "/python":
                self._handle_python()
            case "/reset-python":
                self._handle_reset_python()
            case "/deps":
                self._handle_deps(parts)
            case "/impact":
                self._handle_impact(parts)
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
