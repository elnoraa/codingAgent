# Coding Agent

An AI-powered coding assistant that runs in your terminal. It connects to an LLM backend (e.g., Anthropic Claude or DeepSeek) and provides a rich interactive environment with **100+ tools** for code exploration, editing, debugging, and project management.

```
                        .---.
                       /     \
    python main.py →  |  🤖  |  → AI-assisted development
                       \     /
                        `---'
```

---

## Quick Start

```bash
# 1. Clone the repository
git clone <repo-url>
cd coding-agent

# 2. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate      # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure your API key
cp .env.example .env
# Edit .env — add your ANTHROPIC_API_KEY

# 5. Run the agent
python main.py
```

---

## Features

### 🤖 AI-Powered Code Assistant
- Interactive REPL with context-aware LLM conversations
- Supports multiple models (DeepSeek, Claude 3.x) with per-mode routing
- Three modes: **CODE** (full access), **PLAN** (read-only exploration), **ASK** (read-only Q&A)

### 🛠️ 40+ Built-In Tools
- **File Operations** — `read_file`, `write_file`, `edit_file`, `replace_in_files`, `glob`, `grep`, `file_search`, `rename_file`
- **Git Integration** — `git_commit`, `git_push`, `git_status`, `git_log`, `git_revert`, `git_branch`
- **Code Quality** — `run_tests`, `syntax_check`, `verify_content`, `lint`
- **System** — `bash` (shell execution), `python` (Python REPL), `url_fetch`, `web_search`
- **Planning** — `write_plan`, `edit_plan`, `complete_plan`
- **Database** — `db_tool` (SQLite, PostgreSQL, MySQL exploration)
- **DevOps** — `docker_tool`, `precommit_tool`, `ci_tool`
- **API Testing** — `api_tool` (HTTP requests to local/dev servers)
- **Multi-Agent** — `spawn_agent`, `list_agents`, `send_to_agent`, `terminate_agent`, `run_swarm`
- **Navigation** — `directory_tree`, `list_directory`, `diff`
- **RAG (Retrieval-Augmented Generation)** — `rag_index`, `rag_query`, `rag_status`

### 📋 Plan-Driven Workflow
- Create, save, and manage implementation plans in `plans/`
- Structured plan format with YAML front-matter
- Each feature gets its own branch (branch-per-task convention)
- After implementation, feature branch is merged back to main and deleted
- Auto-completion of plans on session restart
- Review and approve plans before implementation

### 🧪 Integrated Testing & Linting
- Run tests with `run_tests` (auto-detects pytest)
- Syntax checking with `syntax_check`
- Linting with auto-detected config (`/lint`)
- Pre-commit hook management (`/precommit`)
- Pyright static type checking at standard level

### 💾 Session Management
- Save/load full conversation sessions (`/save`, `/load`, `/sessions`)
- Optional AES-GCM encryption for session files
- Auto-save at configurable intervals
- File modification tracking to detect tampering

### 🔄 Multi-Agent & Swarm Support
- Spawn sub-agents for parallel tasks
- Run agent swarms: **sequential** (pipeline), **debate** (compare results), **broadcast** (best of N)
- Orchestrator manages sub-agent lifecycle automatically

### 🔍 RAG (Retrieval-Augmented Generation)
Semantically search your project codebase using natural language — more powerful than `grep` for finding code by concept.

- **`rag_index`** — Build or update a semantic search index over project files. Scans your codebase, chunks files intelligently (respecting function/class boundaries), and builds a TF-IDF index. Zero external dependencies — uses pure Python math.
- **`rag_query`** — Ask natural language questions about your codebase. Returns relevant code chunks with file paths, line numbers, and relevance scores.
- **`rag_status`** — Show index statistics: number of chunks, files indexed, vocabulary size, last indexed timestamp.
- **`/rag` commands** — `/rag index` to build the index, `/rag status` to check, `/rag clear` to reset.

The index is stored locally in `.rag_index/chunks.db` (SQLite) and persists across sessions. Incremental updates mean re-indexing only touches changed files.

Example usage:
```python
# Index your project first
rag_index(mode="project")

# Then search semantically
rag_query(query="error handling for database connections")

# Or filter by file type
rag_query(query="rate limiting implementation", fileFilter="**/*.py")
```

### 🔌 Extensible Architecture
- **MCP Bridge** — Connect to Model Context Protocol servers for additional tools
- **Plugin System** — Load custom tools from the `plugins/` directory
- **Custom Tool Config** — Define additional tools in `config.json`
- **Compatibility Shim** — The `tools/` package re-exports core types for external plugins

### 🔒 Security Features
- SSRF protection for URL fetching and API calls
- Data exfiltration detection in bash commands
- ANSI escape sequence sanitization
- Sensitive data redaction in logs and summaries
- Write-path validation (prevents writes outside working directory)
- File tamper detection during sessions
- Session file encryption
- Rate limiting on tool calls

### 📊 Insights & Monitoring
- Token usage and cost estimation (`/cost`)
- Per-turn latency timeline (`/timeline`)
- Session statistics (`/stats`)
- Change log / audit trail (`/changes`)
- Dependency analysis (`/deps`, `/impact`)
- File watching (`/watch`, `/watchers`)

---

## Configuration

### Environment Variables (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Your API key **(required)** |
| `ANTHROPIC_BASE_URL` | `https://api.deepseek.com/anthropic` | API endpoint |
| `ANTHROPIC_MODEL` | `deepseek-chat` | Model name |
| `MAX_TOKENS` | `4096` | Max response tokens |
| `LOG_LEVEL` | `INFO` | Logging level |

### `config.json`

Example configuration file at the project root:

```json
{
  "notifications": {
    "enabled": true,
    "minDuration": 10
  },
  "theme": {
    "syntax_theme": "monokai"
  }
}
```

Additional supported keys: `model`, `maxTokens`, `temperature`, `topP`, `systemPrompt`, `customPersona`, `contextFiles`, `customToolsConfig`, `mcpServers`, `autoSaveInterval`.

---

## REPL Commands

| Command | Description |
|---------|-------------|
| `/help`, `/h` | Show help |
| `/clear`, `/c` | Clear conversation history |
| `/plan`, `/p` | Switch to plan mode |
| `/ask`, `/a` | Switch to ask mode |
| `/code` | Switch to code mode |
| `/tools` | List available tools |
| `/status`, `/s` | Show session status |
| `/history` | Show message history |
| `/save <name>` | Save session |
| `/load <name>` | Load session |
| `/sessions` | List saved sessions |
| `/search <pattern>` | Search conversation history |
| `/edit` | Edit last user message |
| `/retry`, `/r` | Re-send last message |
| `/cost` | Show token usage & cost |
| `/stats` | Show session statistics |
| `/changes` | Show change log |
| `/timeline` | Show turn latency breakdown |
| `/diff-review` | Toggle edit confirmation |
| `/model` | Show/switch model |
| `/snippet` | Manage snippets |
| `/prompt` | Manage prompt templates |
| `/profile` | Manage config profiles |
| `/backup` | Manage backups |
| `/restart` | Reset session |
| `/exit` or `exit` | Quit |

---

## Project Structure

```
coding-agent/
├── main.py                  # Entry point
├── config.json              # User configuration
├── coding-agent.md          # Agent instruction rules
├── .env                     # API keys (not tracked)
├── .env.example             # Example environment
├── requirements.txt         # Python dependencies
├── pytest.ini               # Test configuration
├── pyrightconfig.json       # Type checking config
├── .pre-commit-config.yaml  # Pre-commit hooks
│
├── src/                     # Core application package
│   ├── main.py              # CLI entry, config loading
│   ├── client.py            # LLM API client (streaming, retry)
│   ├── repl/                # Interactive REPL
│   │   ├── repl.py          # Core REPL loop (Repl class)
│   │   ├── commands.py      # Command dispatcher
│   │   ├── tool_runner.py   # Tool execution helpers
│   │   ├── help_text.py     # Help text, model pricing
│   │   ├── system_prompt.py # System prompt builder
│   │   ├── ui.py            # Tab completion, multiline input
│   │   └── *.py             # Command handlers
│   ├── tools/               # Tool implementations (40+ files)
│   ├── tool_base.py         # Tool, ToolContext, ToolRegistry
│   ├── session.py           # Session save/load (encrypted)
│   ├── security.py          # SSRF, exfiltration, sanitization
│   ├── plan.py              # Plan CRUD operations
│   ├── backup.py            # Backup/restore
│   ├── changelog.py         # Audit trail
│   ├── logging_config.py    # Logging setup
│   ├── formatting.py        # Terminal formatting (Rich)
│   ├── markdown.py          # Markdown rendering
│   ├── diagrams.py          # Mermaid diagram rendering
│   ├── python_repl.py       # Embedded Python REPL
│   ├── mcp_bridge.py        # MCP server integration
│   ├── orchestrator.py      # Multi-agent orchestration
│   ├── plugin_loader.py     # Plugin discovery & loading
│   ├── custom_tools.py      # Custom tool loading from config
│   ├── validation.py        # Write-path validation
│   ├── rate_limiter.py      # Rate limiting
│   ├── profiles.py          # Configuration profiles
│   ├── prompts.py           # Prompt template management
│   ├── snippets.py          # Snippet management
│   ├── theme.py             # Theme support
│   ├── notifications.py     # Desktop notifications
│   ├── dep_analyzer.py      # Dependency graph analysis
│   └── utils.py             # Shared utilities
│
├── tools/                   # Compatibility shim (re-exports from src/)
├── plugins/                 # User-installed plugins
│   └── example_tool/
├── plans/                   # Implementation plans
│   ├── pending/             # Plans awaiting approval
│   └── completed/           # Completed plans
├── sessions/                # Saved conversation sessions
├── logs/                    # Application logs
│
└── tests/                   # Test suite (pytest)
    ├── test_repl.py
    ├── test_client.py
    ├── test_session.py
    └── ... (90+ test files)
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                   main.py                            │
│         (entry point, config loading)                │
└────────────┬────────────────────────────┬───────────┘
             │                            │
             ▼                            ▼
┌─────────────────────┐    ┌──────────────────────────┐
│    LlmClient         │    │         Repl              │
│  (API communication) │    │  (interactive loop)       │
│  • streaming         │    │  • message management     │
│  • retry/backoff     │    │  • mode switching         │
│  • tool dispatch     │◄───│  • tool execution         │
│  • multi-model       │    │  • command dispatch       │
└────────┬────────────┘    └──────────┬────────────────┘
         │                            │
         ▼                            ▼
┌─────────────────────┐    ┌──────────────────────────┐
│    ToolRegistry      │    │    Tool implementations  │
│  • register/get/all  │───►│  (40+ tools in src/tools/)│
│  • to_anthropic_tools│    └──────────────────────────┘
│  • rebuild (reload)  │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│    ToolContext        │
│  • working_directory  │
│  • file_snapshots     │
│  • path validation    │
│  • orchestrator ref   │
└─────────────────────┘
```

---

## Development

### Workflow

This project follows a **plan-first, branch-per-task** workflow:

1. **Plan** — Create or pick a plan from `plans/pending/`
2. **Branch** — Create a feature branch from `main` (e.g., `feat-add-syntax-highlighting`)
3. **Implement** — Make changes, update docs and tests
4. **Commit** — `git commit` (pre-commit hook auto-runs tests)
5. **Push** — Push the feature branch to the remote
6. **Merge** — Switch to `main`, merge the feature branch, push, delete the feature branch
7. **Complete** — Move the plan to `plans/completed/`

### Running Tests

```bash
pytest                           # All tests
pytest -m "not slow"             # Skip slow tests
pytest -m "not network"          # Skip network tests
pytest tests/test_session.py     # Specific test file
```

### Type Checking

```bash
pyright                         # Static type checking (standard mode)
```

### Pre-commit Hooks

```bash
pre-commit install               # Install git hooks
pre-commit run --all-files       # Run all hooks on all files
```

Pre-commit hooks run automatically on `git commit`, including tests and linting.

### Adding a New Tool

1. Create `src/tools/my_tool.py` with a `Tool` dataclass instance
2. Import and register it in `Repl._register_all_tools()` in `src/repl/repl.py`
3. Add tests in `tests/test_my_tool.py`

---

## Requirements

- **Python 3.10+** (type hints, `match` statement)
- **API Key** from Anthropic, DeepSeek, or compatible provider
- Optional: pre-commit, pyright, pywin32 (Windows notifications)

---

## License

MIT
