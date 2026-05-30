"""Help text and constants for the REPL."""

from src.formatting import bold, green, magenta, yellow

# ── Cost estimates per 1M tokens (in USD) ─────────────────────────────
MODEL_PRICING: dict[str, dict[str, float]] = {
    "deepseek-chat": {"input": 0.14, "output": 0.28},
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
}


HELP_TEXT = f"""\
{bold("Commands")}
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
  /budget [set|reset|clear]  Manage token budget (set limit, reset counter, clear budget)
  /summarize [on|off]     Toggle automatic conversation summarization
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
  /models                 Show model routing configuration
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
  /watch [add|remove]     Start or configure file watching
  /unwatch                Stop file watching
  /watchers               Show watcher status
  /backup [label]          Create a backup (optional label)
  /backup list             List all backups
  /backup restore <name>   Restore from a backup
  /backup clean [N]        Remove old backups, keep N most recent
  /lint [path]            Run linter on file or directory (auto-detects config)
  /scaffold list              List available project templates
  /scaffold <template> <name> Create new project from template
  /scaffold show <template>   Show template structure
  /task start <name> [desc]      Start a new task
  /task step <name> <step>       Add a step to a task
  /task complete-step <name> <step> [notes]  Mark step completed
  /task status [name]            Show task status (all tasks or specific)
  /task resume [name]            Resume a task (shows next step)
  /task delete <name>            Delete a task file
  /task context <name> key=val   Update task context
  /tasks                         List all tasks
  /plugins                Show loaded plugins and their status
  /fork <name> [desc]     Fork the conversation at this point
  /branch [list|switch|delete]  Manage conversation branches
  /branches               List all branches
  /timeline                Show per-turn latency breakdown (LLM vs tools)
  /python                 Show Python REPL state
  /reset-python           Reset the Python REPL (clear all variables)
  /deps <file>            Show what a Python file imports (dependencies)
  /impact <file>          Show what imports a Python file (impact analysis)
  /rag index              Build or update the RAG search index
  /rag status             Show RAG index statistics
  /rag clear              Clear the RAG index

{bold("Multi-line input")}
  End a line with \\  to continue typing on the next line.
  This lets you paste code blocks or long instructions.

{bold("Tools")}
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
  rag_index       Build/update a semantic search index over project files
  rag_query       Semantic search across your codebase using natural language
  rag_status      Show RAG index status and statistics

{bold("Modes")}
  CODE mode  {green("●")}  All tools available (read + write + execute)
  PLAN mode  {yellow("●")}  Read-only exploration & planning (read-only tools only)
  ASK mode   {magenta("●")}  Read-only Q&A & explanation (read-only tools only)"""


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
    "rag": """\
Usage: /rag <subcommand>

Manages the RAG (Retrieval-Augmented Generation) semantic search index.
This index allows natural-language search across your project codebase.

Subcommands:
  /rag index    — Build or update the index (scans project files)
  /rag status   — Show index statistics (chunks, files, languages)
  /rag clear    — Clear the entire index

After indexing, use the rag_query tool to search semantically.
The index is stored in .rag_index/ and persists across sessions.

Examples:
  /rag index         Index the entire project
  /rag index src/    Index only the src/ directory
  /rag status        Show index statistics
  /rag clear         Reset the index""",
}


def contains_markdown(text: str) -> bool:
    """Check if text contains Markdown formatting that would benefit from rich rendering."""
    import re as _re

    # Check for common Markdown patterns
    patterns = [
        r"```",  # Code blocks
        r"^#{1,6}\s",  # Headings (at start of line)
        r"\*\*[^*]+\*\*",  # Bold
        r"\*[^*]+\*",  # Italic
        r"^[-*+]\s",  # Unordered lists
        r"^\d+\.\s",  # Ordered lists
        r"\[.+\]\(.+\)",  # Links
        r"\|.+\|.+\|",  # Tables
        r"^>\s",  # Blockquotes
        r"---",  # Horizontal rules
        r"`[^`]+`",  # Inline code
    ]
    return any(bool(_re.search(p, text, _re.MULTILINE)) for p in patterns)


def plan_name_from_text(text: str) -> str:
    """Extract a safe plan name from the first meaningful line of text."""
    import time

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
