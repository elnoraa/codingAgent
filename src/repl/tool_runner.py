"""Tool execution and orchestration — running tools with timeouts, tracking calls and results."""

from __future__ import annotations

import concurrent.futures as _futures
import logging
import time
from typing import TYPE_CHECKING

from src.formatting import bold, dim, green, yellow, cyan, red, color_json, Spinner

if TYPE_CHECKING:
    from src.repl.repl import Repl
    from src.tool_base import Tool, ToolContext

logger = logging.getLogger(__name__)


def execute_tool_with_timeout(
    repl: "Repl",
    tool: "Tool",
    args: dict[str, object],
    context: "ToolContext",
    timeout: int | None = None,
) -> str:
    """Execute a tool with a timeout. Returns the result or an error message.

    Uses a thread pool to enforce a maximum execution duration, preventing a
    single hung tool (e.g. a bash command that hangs indefinitely) from
    blocking the entire agent.
    """
    from src.tool_base import Tool, ToolContext

    effective_timeout = timeout if timeout is not None else repl._tool_execution_timeout
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


def handle_interactive_tool(repl: "Repl", tool: "Tool", args: dict[str, object]) -> str:
    """Handle an interactive tool that needs user input.

    Pauses the tool loop, displays the question, reads user response,
    and returns it as the tool result.
    """
    # Stop spinner if running
    if repl._spinner is not None:
        repl._spinner.stop()
        repl._spinner = None

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


def on_tool_call(repl: "Repl", name: str, args: dict[str, object]) -> None:
    """Handle a tool call from the LLM — display, track usage, log changes."""
    # Stop spinner if still running (LLM called a tool before generating text)
    if repl._spinner is not None:
        repl._spinner.stop()
        repl._spinner = None

    args_str = color_json(args)
    print(f"\n  {cyan('⚡')} {bold(name)}")
    # Only show args if they're non-trivial, to keep display clean
    if len(str(args)) > 4:  # more than just "{}"
        print(f"  {'│'}   {args_str}")

    # ── Track start time for notification timing ──────────────────────
    repl._tool_start_time = time.time()

    # ── Track tool usage for statistics ───────────────────────────────
    repl._tool_usage[name] = repl._tool_usage.get(name, 0) + 1

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
        repl._change_log.append({
            "timestamp": ts,
            "tool": name,
            "path": path_arg,
            "summary": summary,
        })


def on_tool_result(repl: "Repl", result: str, tool_name: str = "") -> None:
    """Handle a tool result — display outcome, track timing, notify."""
    is_error = result.startswith("Error:")

    # Record tool execution in the current turn timeline
    if tool_name and repl._tool_start_time > 0:
        duration = time.time() - repl._tool_start_time
        repl._current_turn_tools.append({
            "name": tool_name,
            "duration": duration,
            "error": is_error,
        })

    # Track consecutive tool failures
    if is_error:
        repl._consecutive_tool_failures += 1
    else:
        repl._consecutive_tool_failures = 0

    truncated = len(result) > 250
    preview = result if not truncated else result[:250]
    suffix = ""
    if truncated:
        suffix = f" {dim(f'[+{len(result) - 250} more chars]')}"

    # Show elapsed time for the tool
    elapsed_str = ""
    if repl._tool_start_time > 0:
        elapsed = time.time() - repl._tool_start_time
        elapsed_str = f" {dim(f'┄ {elapsed:.1f}s')}"
        # Track duration per tool
        if tool_name and tool_name not in repl._tool_durations:
            repl._tool_durations[tool_name] = []
        if tool_name:
            repl._tool_durations[tool_name].append(elapsed)

    # Track errors
    if is_error and tool_name:
        repl._tool_errors[tool_name] = repl._tool_errors.get(tool_name, 0) + 1

    if is_error:
        print(f"  {red('✗')} {red(preview)}{suffix}{elapsed_str}")
    else:
        print(f"  {green('✓')} {dim(preview)}{suffix}{elapsed_str}")

    # ── Desktop notification for long-running tools ───────────────────
    if repl._notifications_enabled and repl._tool_start_time > 0:
        from src.notifications import notify, should_notify, play_sound

        elapsed = time.time() - repl._tool_start_time
        if should_notify(elapsed, repl._notifications_min_duration):
            tool_display = tool_name or "Tool"
            notify(
                title=f"Coding Agent: {tool_display}",
                message=f"Completed in {elapsed:.1f}s",
            )
            play_sound()


def check_token_budget(repl: "Repl") -> None:
    """Check current token usage against budget and warn/block as needed."""
    if repl._token_budget is None:
        return

    ratio = repl._total_tokens_used / repl._token_budget

    if ratio >= repl._token_budget_hard_limit:
        repl._token_budget_exceeded = True
        print(f"\n  {red('✗')} Token budget exceeded ({repl._total_tokens_used:,} / {repl._token_budget:,} tokens)")
        print(f"  {yellow('⟳')} Switching to read-only mode. Use /budget reset to clear.")
        repl.mode = "plan"

    elif ratio >= repl._token_budget_warning:
        warning_level = "WARNING" if ratio >= 0.9 else "CAUTION"
        print(f"\n  {yellow('⚠')} Token budget {warning_level}: {repl._total_tokens_used:,} / {repl._token_budget:,} tokens ({ratio:.0%})")
