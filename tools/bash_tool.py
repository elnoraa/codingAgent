from __future__ import annotations

import logging
import os
import re as _re
import subprocess
from typing import Any

from tools import Tool, ToolContext

from src.logging_config import get_logger

logger = get_logger(__name__)

DEFAULT_TIMEOUT = 30

# ── Pre-execution command scanner patterns ────────────────────────────────
# Each entry is (regex_pattern, description)
#
# NOTE: These patterns are expanded to cover the most common write-related
# commands an LLM might generate. Environment variables and command
# substitution are resolved before matching to prevent trivial bypasses.

_ESCAPE_PATTERNS: list[tuple[str, str]] = [
    # Shell redirects (> and >>) to absolute paths (Unix / or Windows C:\) or paths with ../../
    (r'(?:(?:\d*>>?|&>>?)\s+)((?:[a-zA-Z]:)?[/\\]|\.\./)', "output redirect (> or >>) to a path outside the working directory"),
    # tee to absolute path
    (r'\btee\s+(-[aA]+\s+)?((?:[a-zA-Z]:)?[/\\]|\.\./)', "tee to a path outside the working directory"),
    # mv with target outside
    (r'\bmv\s+\S+\s+((?:[a-zA-Z]:)?[/\\]|\.\./)', "mv target resolves outside the working directory"),
    # cp with target outside
    (r'\bcp\s+\S+\s+((?:[a-zA-Z]:)?[/\\]|\.\./)', "cp target resolves outside the working directory"),
    # rm on absolute paths or outside
    (r'\brm\s+[-rf]*\s+((?:[a-zA-Z]:)?[/\\]|\.\./)', "rm target resolves outside the working directory"),
    # ln with target outside
    (r'\bln\s+-[sf]+\s+\S+\s+((?:[a-zA-Z]:)?[/\\]|\.\./)', "ln target resolves outside the working directory"),
    # chmod/chown on files outside
    (r'\b(?:chmod|chown)\s+\S+\s+((?:[a-zA-Z]:)?[/\\]|\.\./)', "chmod/chown target resolves outside the working directory"),
    # dd with of= outside
    (r'\bdd\b.*\bof=((?:[a-zA-Z]:)?[/\\]|\.\./)', "dd output file resolves outside the working directory"),
    # curl -o / --output to a path outside
    (r'\bcurl\s+.*\s+-[oO]\s+((?:[a-zA-Z]:)?[/\\]|\.\./)', "curl -o to a path outside the working directory"),
    (r'\bcurl\s+.*\s+--output\s+((?:[a-zA-Z]:)?[/\\]|\.\./)', "curl --output to a path outside the working directory"),
    # wget -O / --output-document to a path outside
    (r'\bwget\s+.*\s+-[Oo]\s+((?:[a-zA-Z]:)?[/\\]|\.\./)', "wget -O to a path outside the working directory"),
    (r'\bwget\s+.*\s+--output-document\s+((?:[a-zA-Z]:)?[/\\]|\.\./)', "wget --output-document to a path outside"),
    # rsync with destination outside
    (r'\brsync\b.*\s((?:[a-zA-Z]:)?[/\\]|\.\./)(?!\s)', "rsync destination resolves outside the working directory"),
    # install command (copies files with permissions)
    (r'\binstall\s+.*\s+((?:[a-zA-Z]:)?[/\\]|\.\./)', "install target resolves outside the working directory"),
    # scp to local path outside
    (r'\bscp\b.*\s((?:[a-zA-Z]:)?[/\\]|\.\./)\S*$', "scp target resolves outside the working directory"),
    # tar/gzip extraction to outside path
    (r'\b(?:tar|unzip|7z)\b.*\s+-[a-zA-Z]*[Coc]\s+((?:[a-zA-Z]:)?[/\\]|\.\./)', "archive extraction target outside the working directory"),
    # git clone to outside path
    (r'\bgit\s+clone\b.*\s+((?:[a-zA-Z]:)?[/\\]|\.\./)', "git clone target outside the working directory"),
]


def _expand_shell_variables(cmd: str) -> str:
    """Expand environment variables (``$VAR``, ``${VAR}``) and tilde (``~``)
    in a shell command string so that path-based checks see resolved values.

    This prevents trivial bypasses like ``echo test > $HOME/evil.txt``.
    """
    # Expand ~ only when it appears as a standalone token (at start or after space)
    # Do NOT replace ~ inside words like AARONL~1 (Windows short names)
    cmd = _re.sub(r'(?:^|\s)~(?=\s|$|/|\\)', lambda m: m.group(0).replace('~', os.path.expanduser("~")), cmd)
    # Expand $VAR and ${VAR}
    def _replace_var(match: _re.Match[str]) -> str:
        var_name = match.group(1) or match.group(2)
        if var_name:
            return os.environ.get(var_name, match.group(0))
        return match.group(0)
    cmd = _re.sub(r'\$(\w+)|\$\{(\w+)\}', _replace_var, cmd)
    return cmd


def _has_command_substitution(cmd: str) -> bool:
    """Detect ``$(...)`` or backtick command substitution in a command string.

    Command substitution in paths is a strong indicator of attempted bypass.
    """
    return bool(_re.search(r'\$\([^)]+\)', cmd) or _re.search(r'`[^`]+`', cmd))


def _check_command_for_outside_writes(command: str, working_directory: str) -> str | None:
    """Check if a bash command attempts to write/move/delete files outside the working directory.

    Expands environment variables and tilde before matching to prevent
    trivial bypasses. Detects command substitution as a red flag.

    Returns an error message if a violation is detected, None otherwise.
    """
    from pathlib import Path

    # First, expand variables to prevent $HOME / $VAR bypasses
    expanded = _expand_shell_variables(command)

    # Check for command substitution — a common bypass technique
    if _has_command_substitution(command):
        return (
            f"Error: Command blocked — command substitution detected (``$(...)`` or backticks).\n"
            f"Command substitution in file paths is not allowed.\n"
            f"Working directory: '{working_directory}'\n"
            f"Command: {command[:200]!r}"
        )

    for pattern, description in _ESCAPE_PATTERNS:
        match = _re.search(pattern, expanded)
        if match:
            # Do a quick sanity check — if the target resolves inside, allow it
            try:
                target = match.group(0).strip()
                path_match = _re.search(r'((?:[a-zA-Z]:)?[/\\][\w/.\-\\ :]+)', target)
                if path_match:
                    candidate = path_match.group(1)
                    resolved = Path(candidate).resolve()
                    resolved_wd = Path(working_directory).resolve()
                    resolved.relative_to(resolved_wd)
                    # It resolved inside the working directory — allow it
                    continue
            except (ValueError, IndexError):
                pass

            return (
                f"Error: Command blocked — {description}.\n"
                f"Working directory: '{working_directory}'\n"
                f"All file operations must stay within the working directory.\n"
                f"Matched pattern: {match.group(0)!r}"
            )
    return None


def execute(args: dict[str, Any], ctx: ToolContext) -> str:
    command = args.get("command")
    timeout = int(args.get("timeout", DEFAULT_TIMEOUT))
    workdir = args.get("workdir") or ctx.working_directory  # Default to working dir
    logger.info("execute: command=%s, timeout=%s, workdir=%s", command, timeout, workdir)
    if not command:
        return 'Error: missing required argument "command".'

    # Validate workdir is within the working directory
    error = ctx.validate_write_path(workdir)
    if error:
        return error

    # Pre-execution command scanner: block writes outside working dir
    scanner_error = _check_command_for_outside_writes(command, ctx.working_directory)
    if scanner_error:
        return scanner_error

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=workdir,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Command timed out after %ds: %s", timeout, command)
        return f"[Error] Command timed out after {timeout}s"
    except Exception as exc:
        logger.error("Command failed: %s", exc)
        return f"[Error] {exc}"

    # Post-execution: quick git diff check to detect writes outside working dir
    if result.returncode == 0:
        try:
            _diff_check = subprocess.run(
                ["git", "diff", "--stat"],
                capture_output=True, text=True, cwd=workdir,
                timeout=5,
            )
            if _diff_check.returncode == 0 and _diff_check.stdout:
                _changed_files = _diff_check.stdout.strip().split("\n")
                for _line in _changed_files:
                    _file_path = _line.split("|")[0].strip()
                    if _file_path:
                        _abs_path = os.path.join(workdir, _file_path)
                        err = ctx.validate_write_path(_abs_path)
                        if err:
                            # Revert the changes with git checkout
                            subprocess.run(
                                ["git", "checkout", "--", _file_path],
                                capture_output=True, cwd=workdir,
                                timeout=5,
                            )
                            return (
                                f"Command completed but wrote to file outside working directory. "
                                f"Changes reverted.\n{err}"
                            )
        except Exception:
            pass

    parts: list[str] = []
    if result.stdout:
        parts.append(result.stdout.rstrip("\n"))
    if result.stderr:
        parts.append(f"[stderr]\n{result.stderr.rstrip(chr(10))}")
    if result.returncode != 0:
        parts.append(f"\n[Exit code: {result.returncode}]")

    logger.info("Command completed (exit_code=%d, stdout_len=%d, stderr_len=%d)", result.returncode, len(result.stdout or ""), len(result.stderr or ""))
    return "\n".join(parts) if parts else "Command completed with no output."


bash_tool = Tool(
    name="bash",
    description=(
        "Run a shell command and return its output. Use this to compile, "
        "run tests, lint, install packages, or any other shell operation.\n\n"
        "WARNING: All file operations (write, move, delete, copy) must stay "
        "within the project's working directory. The tool enforces this by "
        "blocking commands that target paths outside the working directory."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The shell command to execute"},
            "timeout": {"type": "number", "description": "Timeout in seconds (default: 30)"},
            "workdir": {
                "type": "string",
                "description": "Working directory for the command (default: project root)",
            },
        },
        "required": ["command"],
    },
    execute=execute,
    read_only=False,
)
