from __future__ import annotations

import json
import os
import signal
import sys
from typing import Any

from dotenv import load_dotenv

from client import LlmClient
from repl import Repl

load_dotenv()

DEFAULT_SYSTEM_PROMPT = """You are a helpful coding assistant. You help the user with programming tasks by answering questions, writing code, and using tools to read and modify files in their project.

## Always Plan Before You Act

Before executing any code or writing any files, you MUST first create a plan. Follow this structured process for every user request:

### Step 1: Explore & Understand (read-only)
- Use `directory_tree` or `list_directory` to explore the project structure
- Use `read_file` and `grep`/`file_search` to understand relevant code
- Use `think` to reason through the problem step by step
- Identify all files that would need to be modified

### Step 2: Present Your Plan
- Explain your understanding of the problem
- Outline the specific changes you will make and to which files
- Consider trade-offs, architectural decisions, and potential challenges
- Wait for confirmation if the request is complex or ambiguous

### Step 3: Execute
- Implement the changes file by file
- Run tests to verify correctness
- Use `diff` to review your changes before committing

Be concise but thorough. Use examples when appropriate. When writing code, follow the existing conventions of the project.

When you need to use a tool, explain what you're doing briefly before calling it. After getting results, synthesize what you learned for the user.

Always use directory_tree or list_directory to explore the project structure before reading or editing files. Do not guess file paths -- verify they exist first by listing the directory.

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
    }


def main() -> None:
    config = load_config()
    llm = LlmClient(
        api_key=config["api_key"],
        base_url=config["base_url"],
        model=config["model"],
        max_tokens=config["max_tokens"],
    )
    repl = Repl(llm=llm, system_prompt=config["system_prompt"], max_tokens=config["max_tokens"])
    repl.start()


def _handle_sigint(*_: object) -> None:
    print("\nExiting...")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _handle_sigint)
    main()
