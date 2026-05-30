from __future__ import annotations

import os
import subprocess
from typing import Any

from src.logging_config import get_logger
from src.tools import Tool, ToolContext

logger = get_logger(__name__)


def execute(args: dict[str, Any], _ctx: ToolContext) -> str:
    root_dir = args.get("path") or os.getcwd()
    message = args.get("message") or ""
    auto_message = bool(args.get("autoMessage", True))
    all_files = bool(args.get("all", False))
    logger.info("execute: path=%s, message=%s, autoMessage=%s, all=%s", root_dir, message, auto_message, all_files)

    # Validate path is within the working directory
    error = _ctx.validate_write_path(root_dir)
    if error:
        raise ValueError(error)

    # Check if we're in a git repo
    try:
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            cwd=root_dir,
            check=True,
        )
    except subprocess.CalledProcessError:
        raise ValueError(f"{root_dir} is not inside a git repository")
    except FileNotFoundError:
        raise RuntimeError("git is not installed")

    # Stage all files if requested
    if all_files:
        try:
            subprocess.run(
                ["git", "add", "-A"],
                capture_output=True,
                cwd=root_dir,
                check=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            raise TimeoutError("git add timed out")
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"git add failed: {exc.stderr.strip()}")

    # Check if there's anything staged
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--stat"],
            capture_output=True,
            text=True,
            cwd=root_dir,
            check=True,
        )
        if not result.stdout.strip():
            raise ValueError("Nothing to commit. Use all=true to stage all changes, or stage files manually.")
        diff_stat = result.stdout.strip()
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(exc.stderr.strip())

    # Generate commit message if not provided
    if not message and auto_message:
        try:
            diff_result = subprocess.run(
                ["git", "diff", "--cached"],
                capture_output=True,
                text=True,
                cwd=root_dir,
                timeout=30,
            )
            diff_text = diff_result.stdout

            # Simple heuristic-based message generation
            message = _generate_commit_message(diff_text, diff_stat)
        except subprocess.TimeoutExpired:
            message = "Update project files"
        except Exception:
            message = "Update project files"

    if not message:
        message = "Update project files"

    # Attempt the commit, with retry logic for pre-commit hooks that modify files
    max_attempts = 3
    for attempt in range(max_attempts):
        result = subprocess.run(
            ["git", "commit", "-m", message],
            capture_output=True,
            text=True,
            cwd=root_dir,
            timeout=120,
        )

        if result.returncode == 0:
            # Commit succeeded
            return f"✅ {result.stdout.strip()}"

        stderr = result.stderr.strip()

        # Detect if pre-commit hooks modified files (common with ruff --fix)
        # The pattern is typically: "Files were modified by this hook" or similar
        if attempt < max_attempts - 1 and _hooks_modified_files(stderr):
            logger.info(
                "Pre-commit hooks modified files, staging and retrying (attempt %d/%d)", attempt + 1, max_attempts
            )
            try:
                subprocess.run(
                    ["git", "add", "-A"],
                    capture_output=True,
                    cwd=root_dir,
                    check=True,
                    timeout=30,
                )
            except subprocess.CalledProcessError as exc:
                raise RuntimeError(
                    f"Retry failed: could not stage changes after hook modifications: {exc.stderr.strip()}"
                )
            continue

        # Check if commit was rejected by a hook (non-modification failure)
        if _hooks_rejected_commit(stderr):
            raise RuntimeError(f"Commit rejected by pre-commit hook:\n{stderr}")

        # Some other failure — show the full output
        raise RuntimeError(f"Commit failed:\n{stderr}")

    raise RuntimeError("Commit failed after pre-commit hooks modified files on multiple attempts")


def _hooks_modified_files(stderr: str) -> bool:
    """Check if pre-commit hook stderr indicates files were modified."""
    indicators = [
        "files were modified by this hook",
        "reformatted",
        "fixed",
        "ruff",
        "autofix",
    ]
    return any(indicator in stderr.lower() for indicator in indicators)


def _hooks_rejected_commit(stderr: str) -> bool:
    """Check if pre-commit hook stderr indicates a hook rejection (not a modification)."""
    lines = stderr.split("\n")
    # Count lines that look like hook failures (contain "Failed" or "failed")
    failure_count = sum(1 for line in lines if "failed" in line.lower())
    return failure_count > 0


def _generate_commit_message(diff_text: str, diff_stat: str) -> str:
    """Generate a simple commit message from the diff."""
    # Parse files from diff stat
    lines = diff_stat.strip().split("\n")
    changed_files: list[str] = []
    for line in lines:
        parts = line.split("|")
        if parts and parts[0]:
            changed_files.append(parts[0].strip())

    if not changed_files:
        return "Update project files"

    # Detect common patterns
    has_python = any(f.endswith(".py") for f in changed_files)
    js_exts = (".js", ".ts", ".jsx", ".tsx")
    css_exts = (".css", ".scss", ".less")
    doc_exts = (".md", ".rst", ".txt")
    has_js = any(f.endswith(js_exts) for f in changed_files)
    has_css = any(f.endswith(css_exts) for f in changed_files)
    has_docs = any(f.endswith(doc_exts) for f in changed_files)
    has_tests = any("test" in f.lower() for f in changed_files)
    has_config = any(
        f in ("package.json", "pyproject.toml", "setup.py", "setup.cfg", "Cargo.toml", "go.mod") for f in changed_files
    )

    # Build message
    parts: list[str] = []
    if has_tests:
        parts.append("tests")
    if has_config:
        parts.append("config")
    if has_docs:
        parts.append("docs")
    if has_python:
        parts.append("Python code")
    if has_js:
        parts.append("JS/TS code")
    if has_css:
        parts.append("styles")

    if len(changed_files) <= 3:
        file_list = ", ".join(changed_files)
        if parts:
            return f"Update {', '.join(parts)}: {file_list}"
        return f"Update {file_list}"
    else:
        if parts:
            return f"Update {', '.join(parts)} ({len(changed_files)} files)"
        return f"Update {len(changed_files)} files"


git_commit_tool = Tool(
    name="git_commit",
    description=(
        "Stage all changes (optional) and create a git commit with a descriptive "
        "message. Can auto-generate the commit message based on the diff, or you "
        "can provide a custom message."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "Custom commit message. If empty and autoMessage is true, generates one automatically.",
            },
            "path": {
                "type": "string",
                "description": "Repository directory (defaults to current directory)",
            },
            "autoMessage": {
                "type": "boolean",
                "description": "Auto-generate commit message from the diff (default: true). "
                "Ignored if a custom message is provided.",
            },
            "all": {
                "type": "boolean",
                "description": "Stage all changes before committing (git add -A). Default: false.",
            },
        },
    },
    execute=execute,
    read_only=False,
)
