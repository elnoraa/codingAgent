"""Command dispatcher — routes /commands to the appropriate handler.

This module contains the ``dispatch()`` function which implements the
large pattern-match statement for all REPL commands, delegating to
handler functions in other modules.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, cast

from src.formatting import bold, cyan, dim, green, magenta, yellow
from src.repl.help_text import COMMAND_HELP, HELP_TEXT
from src.utils import estimate_tokens

if TYPE_CHECKING:
    from src.repl.repl import Repl

logger = logging.getLogger(__name__)


def _get_last_assistant_text(repl: Repl) -> str:
    """Get the last assistant text response."""
    for msg in reversed(repl.messages):
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


def _get_last_user_index(repl: Repl) -> int | None:
    """Return the index of the last user message, or None."""
    for i in range(len(repl.messages) - 1, -1, -1):
        if repl.messages[i].get("role") == "user":
            content = repl.messages[i].get("content", "")
            if isinstance(content, str):
                return i
    return None


def dispatch(repl: Repl, cmd: str) -> None:
    """Route a /command to the appropriate handler function."""
    from src.repl.auxiliary import (
        handle_budget,
        handle_cd,
        handle_changes,
        handle_config,
        handle_cost,
        handle_deps,
        handle_diff_review,
        handle_edit,
        handle_impact,
        handle_mcp,
        handle_model,
        handle_models,
        handle_open,
        handle_plugins,
        handle_python,
        handle_reload,
        handle_reset_python,
        handle_retry,
        handle_retry_auto,
        handle_search,
        handle_stats,
        handle_summarize,
        handle_timeline,
    )
    from src.repl.backup_commands import handle_backup
    from src.repl.branch_commands import handle_branch, handle_branches, handle_fork
    from src.repl.export_commands import handle_export
    from src.repl.lint_commands import handle_lint
    from src.repl.plan_commands import handle_plan_create, handle_plan_list, handle_plan_save
    from src.repl.profile_commands import handle_profile
    from src.repl.prompt_commands import handle_prompt
    from src.repl.scaffold_commands import handle_scaffold
    from src.repl.session_commands import (
        handle_persona,
        handle_session_list,
        handle_session_load,
        handle_session_save,
    )
    from src.repl.snippet_commands import handle_snippet
    from src.repl.task_commands import handle_task
    from src.repl.watch_commands import handle_unwatch, handle_watch, handle_watchers

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
            repl.messages.clear()
            print(f"  {dim('Conversation history cleared.')}")

        case "/tools":
            tools_to_show = repl.tools.get_read_only() if repl.mode in ("plan", "ask") else repl.tools.get_all()
            for t in tools_to_show:
                is_mcp = "/" in t.name and repl._mcp_bridge is not None and repl._mcp_bridge.is_any_connected
                tag = f" {cyan('[MCP]')}" if is_mcp else ""
                print(f"  {bold(t.name)}{tag}{dim(f' — {t.description}')}")
            print(f"  {dim(f'[{repl.mode.upper()} mode — {len(tools_to_show)} tools available]')}")

        case "/reload":
            handle_reload(repl)

        case "/history":
            count = len(repl.messages)
            user_msgs = sum(1 for m in repl.messages if m.get("role") == "user")
            asst_msgs = sum(1 for m in repl.messages if m.get("role") == "assistant")
            tool_calls = sum(1 for m in repl.messages if isinstance(m.get("content"), list))
            total_tokens = 0
            print(f"  {bold('History')}  {dim(f'({count} messages)')}")
            print()
            # Show conversation flow
            for i, m in enumerate(repl.messages):
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
                print(
                    f"  {dim(str(i + 1).rjust(3))} {role_color(arrow)} {bold(role_color(role.title()))}"
                    f" {dim(f'~{tokens}tok')}  {dim(preview)}"
                )

            print()
            print(
                f"  {dim('Summary:')}    {count} messages ({green(str(user_msgs))} user, {cyan(str(asst_msgs))} assistant, {yellow(str(tool_calls))} tool blocks)"
            )
            print(f"  {dim('Tokens:')}     ~{total_tokens} estimated")

        case "/status" | "/s":
            system_prompt = repl._get_system_prompt()
            system_tokens = estimate_tokens(system_prompt)
            msg_count = len(repl.messages)
            total_tokens = sum(estimate_tokens(str(m.get("content", ""))) for m in repl.messages)
            elapsed = time.time() - repl._start_time
            hours, remainder = divmod(int(elapsed), 3600)
            minutes, seconds = divmod(remainder, 60)
            uptime_str = f"{hours}h {minutes}m {seconds}s" if hours else f"{minutes}m {seconds}s"
            print(f"  {bold('Status')}")
            print(f"  {dim('Mode:')}      {cyan(repl.mode.upper())}")
            print(f"  {dim('Model:')}     {cyan(repl.llm.model)}")
            print(f"  {dim('Max tokens:')} {cyan(str(repl.max_tokens))}")
            print(f"  {dim('Messages:')}  {msg_count}")
            print(f"  {dim('Tokens:')}   ~{total_tokens + system_tokens} total (~{system_tokens} system)")
            print(f"  {dim('Uptime:')}   {cyan(uptime_str)}")
            print(f"  {dim('WD:')}       {dim(repl.working_directory)}")
            if repl._custom_persona:
                print(f"  {dim('Persona:')}  {cyan(repl._custom_persona)}")
            if repl._mcp_bridge and repl._mcp_bridge.is_any_connected:
                total = repl._mcp_bridge.total_tool_count
                count = len(repl._mcp_bridge.get_server_info())
                print(f"  {dim('MCP:')}      {cyan(f'{total} tools from {count} server(s)')}")
            if repl._rate_limit_events > 0:
                print(f"  {dim('Rate limit events:')} {cyan(str(repl._rate_limit_events))}")
            from src.repl.auxiliary import estimated_cost

            print(
                f"  {dim('Cost:')}    {dim(f'${estimated_cost(repl):.4f} estimated (in: {repl._input_tokens_total}, out: {repl._output_tokens_total})')}"
            )

        case "/plan" | "/p":
            full_cmd = cmd.lower().strip()
            if full_cmd.startswith("/plan save"):
                handle_plan_save(repl, cmd)
            elif full_cmd.startswith("/plan create"):
                parts_create = cmd.split(maxsplit=2)
                handle_plan_create(repl, parts_create)
            elif full_cmd.startswith("/plan list"):
                parts_list = cmd.split(maxsplit=2)
                sub = parts_list[2].strip() if len(parts_list) > 2 else ""
                handle_plan_list(repl, sub)
            elif full_cmd == "/plan" or full_cmd == "/p":
                if repl.mode == "plan":
                    print(f"  {dim('Already in plan mode.')}")
                else:
                    repl.mode = "plan"
                    repl._mode_switches += 1
                    repl._mode_changed_via_command = True
                    logger.info("Switched to PLAN mode")
                    print(
                        f"  {yellow('●')} {bold('PLAN mode')} {dim('— read-only exploration. Only read-only tools are available.')}"
                    )
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
            if repl.mode == "ask":
                print(f"  {dim('Already in ask mode.')}")
            else:
                repl.mode = "ask"
                repl._mode_switches += 1
                repl._mode_changed_via_command = True
                logger.info("Switched to ASK mode")
                print(
                    f"  {magenta('●')} {bold('ASK mode')} {dim('— read-only Q&A. Only read-only tools are available.')}"
                )
                print(f"  {dim('Use /code to switch back to CODE mode.')}")

        case "/code":
            if repl.mode == "code":
                print(f"  {dim('Already in code mode.')}")
            else:
                repl.mode = "code"
                repl._mode_switches += 1
                repl._mode_changed_via_command = True
                logger.info("Switched to CODE mode")
                print(f"  {green('●')} {bold('CODE mode')} {dim('— all tools available (read, write, execute).')}")
                print(f"  {dim('Use /plan to switch to PLAN mode, or /ask for Q&A mode.')}")

        case "/mode":
            logger.info("Mode check: current mode=%s", repl.mode)
            print(f"  {bold('Mode:')} {bold(repl.mode.upper())}")

        case "/edit":
            handle_edit(repl)

        case "/retry" | "/r":
            handle_retry(repl)

        case "/retry-auto" | "/ra":
            handle_retry_auto(repl)

        case "/cost":
            handle_cost(repl)

        case "/stats":
            handle_stats(repl)

        case "/cd":
            handle_cd(repl, parts)

        case "/rollback":
            print(f"  {dim('Use the undo tool to rollback changes.')}")
            print(f"  {dim('The agent can list and revert file snapshots automatically.')}")

        case "/backup":
            handle_backup(repl, cmd.split(maxsplit=1)[1] if len(cmd.split(maxsplit=1)) > 1 else "")

        case "/lint":
            handle_lint(repl, cmd.split(maxsplit=1)[1] if len(cmd.split(maxsplit=1)) > 1 else "")

        case "/scaffold":
            handle_scaffold(repl, cmd.split(maxsplit=1)[1] if len(cmd.split(maxsplit=1)) > 1 else "")

        case "/task":
            handle_task(repl, cmd.split(maxsplit=1)[1] if len(cmd.split(maxsplit=1)) > 1 else "")

        case "/tasks":
            handle_task(repl, "status")

        case "/plugins":
            handle_plugins(repl, cmd.split(maxsplit=1)[1] if len(cmd.split(maxsplit=1)) > 1 else "")

        case "/fork":
            handle_fork(repl, cmd.split(maxsplit=1)[1] if len(cmd.split(maxsplit=1)) > 1 else "")

        case "/branch":
            handle_branch(repl, cmd.split(maxsplit=1)[1] if len(cmd.split(maxsplit=1)) > 1 else "")

        case "/branches":
            handle_branches(repl, cmd.split(maxsplit=1)[1] if len(cmd.split(maxsplit=1)) > 1 else "")

        case "/timeline":
            handle_timeline(repl)

        case "/mcp":
            handle_mcp(repl)

        case "/model":
            handle_model(repl, parts)

        case "/models":
            handle_models(repl, cmd.split(maxsplit=1)[1] if len(cmd.split(maxsplit=1)) > 1 else "")

        case "/search":
            handle_search(repl, parts)

        case "/snippet":
            handle_snippet(repl, cmd.split(maxsplit=1)[1] if len(cmd.split(maxsplit=1)) > 1 else "")

        case "/diff-review":
            handle_diff_review(repl, cmd.split(maxsplit=1)[1] if len(cmd.split(maxsplit=1)) > 1 else "")

        case "/budget":
            handle_budget(repl, cmd.split(maxsplit=1)[1] if len(cmd.split(maxsplit=1)) > 1 else "")

        case "/summarize":
            handle_summarize(repl, cmd.split(maxsplit=1)[1] if len(cmd.split(maxsplit=1)) > 1 else "")

        case "/watch":
            handle_watch(repl, cmd.split(maxsplit=1)[1] if len(cmd.split(maxsplit=1)) > 1 else "")

        case "/unwatch":
            handle_unwatch(repl, cmd.split(maxsplit=1)[1] if len(cmd.split(maxsplit=1)) > 1 else "")

        case "/watchers":
            handle_watchers(repl, cmd.split(maxsplit=1)[1] if len(cmd.split(maxsplit=1)) > 1 else "")

        case "/export":
            handle_export(repl, parts)

        case "/config":
            handle_config(repl)

        case "/prompt":
            handle_prompt(repl, cmd)

        case "/profile":
            handle_profile(repl, cmd)

        case "/changes":
            handle_changes(repl)

        case "/open":
            handle_open(repl, parts)

        case "/python":
            handle_python(repl)

        case "/reset-python":
            handle_reset_python(repl)

        case "/deps":
            handle_deps(repl, parts)

        case "/impact":
            handle_impact(repl, parts)

        case "/save":
            handle_session_save(repl, parts)

        case "/load":
            handle_session_load(repl, parts)

        case "/sessions":
            handle_session_list(repl)

        case "/persona":
            handle_persona(repl, parts)

        case "/restart":
            repl.messages.clear()
            repl._turn_number = 0
            logger.info("Session restarted (messages cleared)")
            print(f"  {green('✓')} {bold('Restarted.')} {dim('Session reset to turn 1.')}")

        case "/q":
            print(f"  {dim('Exiting...')}")
            raise EOFError()

        case _:
            print(f"  {dim(f'Unknown command: {parts[0]}. Type /help for available commands.')}")
