from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
from typing import Any

from dotenv import load_dotenv

from .client import LlmClient
from .logging_config import get_logger, setup_logging
from .repl import Repl

logger = get_logger(__name__)

load_dotenv()

DEFAULT_SYSTEM_PROMPT = """You are a helpful coding assistant. You help the user with programming tasks by answering questions, writing code, and using tools to read and modify files in their project.

It's good practice to explore the codebase with read-only tools (directory_tree, read_file, grep, etc.) before making changes to understand the current code structure. This helps you write better code that follows the project's conventions.

When you need to use a tool, explain what you're doing briefly before calling it. After getting results, synthesize what you learned for the user.

Always use directory_tree or list_directory to explore the project structure before reading or editing files. Do not guess file paths -- verify they exist first by listing the directory.

## CODING AGENT RULES (MANDATORY)
The following rules are MANDATORY and MUST be followed at all times:
# Coding Agent Instructions

These are MANDATORY rules. The coding agent MUST follow all instructions in this file.

## Workflow Rules

1. After implementing each feature or making significant changes, you MUST:
   a. Commit the changes using `git_commit(all=True)`
   b. Push the changes to the remote using `git_push(branch=<current-branch>)`
   c. Verify the commit was successful by checking git status using `git_status`

2. Always run tests after implementing changes if tests exist.

3. Never modify files outside the project directory.

If a "coding-agent.md" file exists in the project root, read it first -- it contains MANDATORY rules you must follow.

PYLANCE TYPE CHECKING: This project uses Pylance/Pyright for static type analysis at "standard" level. After editing any Python files, review your changes to avoid introducing type errors. Common issues to watch for:
- Missing imports -- ensure all imported symbols are actually imported
- Type mismatches -- don't pass wrong argument types to functions
- Incompatible return types -- ensure function return values match their annotations
- Attribute errors -- don't access attributes that don't exist on the type
- Unused imports -- clean up imports that are no longer needed after edits
- Variable shadowing -- don't use built-in names (list, dict, str, type, id, etc.) as variable names
- Missing None checks -- if a value can be None, check it before using it
The file-editing tools (write_file, edit_file, replace_in_files) may report pyright warnings in their output after edits -- review these carefully and fix them."""


def load_config() -> dict[str, Any]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY is not set in .env")
        print("Copy .env.example to .env and add your API key.")
        sys.exit(1)

    cfg: dict[str, Any] = {}
    try:
        if os.path.exists("config.json"):
            with open("config.json") as f:
                cfg = json.load(f)
    except Exception:
        pass

    return {
        "api_key": api_key,
        "base_url": os.environ.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic"),
        "model": cfg.get("model") or os.environ.get("ANTHROPIC_MODEL", "deepseek-chat"),
        "max_tokens": cfg.get("maxTokens") or int(os.environ.get("MAX_TOKENS", "4096")),
        "system_prompt": cfg.get("systemPrompt", DEFAULT_SYSTEM_PROMPT),
        "temperature": cfg.get("temperature", 0.7),
        "top_p": cfg.get("topP", 1.0),
        "custom_persona": cfg.get("customPersona", ""),
        "context_files": cfg.get("contextFiles", ["README*", "CONTRIBUTING*", "Makefile", "setup.py", "pyproject.toml"]),
        "custom_tools_config": cfg.get("customToolsConfig", ""),
        "notifications_enabled": cfg.get("notifications", {}).get("enabled", False),
        "notifications_min_duration": cfg.get("notifications", {}).get("minDuration", 10),
        "mcp_servers": _get_mcp_servers(cfg),
    }


def _get_mcp_servers(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract the MCP server list from config, with fallback to env var."""
    mcp_servers = cfg.get("mcpServers")
    if isinstance(mcp_servers, list):
        return mcp_servers

    # Fallback: try MCP_SERVERS env var as JSON
    env_val = os.environ.get("MCP_SERVERS")
    if env_val:
        try:
            parsed = json.loads(env_val)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, ValueError):
            logger.warning("Invalid MCP_SERVERS env var, ignoring")
    return []


def main() -> None:
    # ── Parse CLI arguments ──────────────────────────────────────────────
    parser = argparse.ArgumentParser(description="Coding Agent — AI-assisted development")
    parser.add_argument(
        "--log-level",
        default=os.environ.get("LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level (default: INFO, or LOG_LEVEL env var)",
    )
    args = parser.parse_args()

    # ── Initialize logging ───────────────────────────────────────────────
    setup_logging(level=args.log_level)
    logger.info("Starting Coding Agent session (log_level=%s)", args.log_level)

    config = load_config()
    llm = LlmClient(
        api_key=config["api_key"],
        base_url=config["base_url"],
        model=config["model"],
        max_tokens=config["max_tokens"],
        temperature=config["temperature"],
        top_p=config["top_p"],
    )
    # Read auto-save interval from config.json
    auto_save_interval = 0
    try:
        if os.path.exists("config.json"):
            with open("config.json") as f:
                raw_cfg: dict[str, object] = json.load(f)
            auto_save_interval = int(raw_cfg.get("autoSaveInterval", 0))  # type: ignore[arg-type]
    except Exception:
        pass

    repl = Repl(
        llm=llm,
        system_prompt=config["system_prompt"],
        max_tokens=config["max_tokens"],
        custom_persona=config["custom_persona"],
        auto_save_interval=auto_save_interval,
        context_files=config["context_files"],
        custom_tools_config=config["custom_tools_config"],
        notifications_enabled=config["notifications_enabled"],
        notifications_min_duration=config["notifications_min_duration"],
        mcp_servers=config["mcp_servers"],
    )
    repl.start()


def _handle_sigint(*_: object) -> None:
    print("\nExiting...")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _handle_sigint)
    main()
