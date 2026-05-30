"""Auxiliary REPL command handlers — search, cd, model, open, deps, plugins, etc."""

from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING, Any, cast

from src.formatting import Spinner, bold, cyan, dim, green, magenta, red, yellow
from src.utils import estimate_tokens

if TYPE_CHECKING:
    from src.repl.repl import Repl

logger = logging.getLogger(__name__)


def handle_cost(repl: Repl) -> None:
    """Show detailed cost breakdown."""
    from src.repl.help_text import MODEL_PRICING

    system_tokens = estimate_tokens(repl._get_system_prompt())

    pricing = MODEL_PRICING.get(repl.llm.model, {"input": 0.50, "output": 0.50})
    in_cost = (repl._input_tokens_total / 1_000_000) * pricing["input"]
    out_cost = (repl._output_tokens_total / 1_000_000) * pricing["output"]
    total_cost = in_cost + out_cost

    print(f"  {bold('Cost Breakdown')}")
    print(f"  {dim('Model:')}    {cyan(repl.llm.model)}")
    print(f"  {dim('Pricing:')}  {dim(f'${pricing["input"]}/1M in, ${pricing["output"]}/1M out')}")
    print()
    print(f"  {dim('Input tokens:')}  {repl._input_tokens_total}")
    print(f"  {dim('Output tokens:')} {repl._output_tokens_total}")
    print(f"  {dim('System tokens:')} {system_tokens}")
    print()
    print(f"  {dim('Input cost:')}   ${in_cost:.6f}")
    print(f"  {dim('Output cost:')}  ${out_cost:.6f}")
    print(f"  {bold('Total cost:')}  {bold(f'${total_cost:.4f}')}")


def estimated_cost(repl: Repl) -> float:
    """Return estimated total API cost in USD."""
    from src.repl.help_text import MODEL_PRICING

    pricing = MODEL_PRICING.get(repl.llm.model, {"input": 0.50, "output": 0.50})
    in_cost = (repl._input_tokens_total / 1_000_000) * pricing["input"]
    out_cost = (repl._output_tokens_total / 1_000_000) * pricing["output"]
    return in_cost + out_cost


def handle_stats(repl: Repl) -> None:
    """Handle /stats command — show session statistics."""
    elapsed = time.time() - repl._start_time
    hours, remainder = divmod(int(elapsed), 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{hours}h {minutes}m {seconds}s" if hours else f"{minutes}m {seconds}s"

    total_turns = sum(repl._turns_by_mode.values())
    total_tokens = sum(estimate_tokens(str(m.get("content", ""))) for m in repl.messages)
    system_prompt = repl._get_system_prompt()
    system_tokens = estimate_tokens(system_prompt)
    avg_tokens_per_turn = total_tokens // max(total_turns, 1)

    print(f"  {bold('Session Statistics')}")
    print()
    print(f"  {dim('Session duration:')}  {cyan(uptime_str)}")
    print(f"  {dim('Total turns:')}      {cyan(str(total_turns))}")
    print(f"  {dim('Total messages:')}   {cyan(str(len(repl.messages)))}")
    print(
        f"  {dim('Total tokens:')}     {cyan(str(total_tokens + system_tokens))} ({dim('~' + str(avg_tokens_per_turn) + ' avg/turn')})"
    )
    print(f"  {dim('Mode switches:')}    {cyan(str(repl._mode_switches))}")
    print()

    # Turns per mode
    print(f"  {bold('Turns by Mode')}")
    for mode_name in ("code", "plan", "ask"):
        count = repl._turns_by_mode.get(mode_name, 0)
        color_fn = green if mode_name == "code" else yellow if mode_name == "plan" else magenta
        bar_len = max(1, count) if count > 0 else 0
        bar = "█" * min(bar_len, 30)
        print(f"  {color_fn(mode_name.upper().ljust(6))} {dim(bar)} {cyan(str(count))}")
    print()

    # Tool usage
    if repl._tool_usage:
        print(f"  {bold('Tool Usage')}")
        max_count = max(repl._tool_usage.values())
        for tool_name, count in sorted(repl._tool_usage.items(), key=lambda x: -x[1]):
            bar_len = int((count / max(1, max_count)) * 20)
            bar = "█" * bar_len
            durations = repl._tool_durations.get(tool_name, [])
            avg_dur = sum(durations) / len(durations) if durations else 0
            errors = repl._tool_errors.get(tool_name, 0)
            error_str = f"  errors: {errors}" if errors else ""
            print(
                f"  {cyan(tool_name.ljust(20))} {dim(bar)} {cyan(str(count).ljust(4))} {dim(f'avg {avg_dur:.2f}s')} {red(error_str) if errors else dim(error_str)}"
            )
    else:
        print(f"  {dim('No tools have been called yet.')}")
    print()
    print(f"  {dim('Estimated cost:')}  {dim(f'${estimated_cost(repl):.4f}')}")


def handle_search(repl: Repl, parts: list[str]) -> None:
    """Handle /search command — search messages for a pattern."""
    import re as regex_module

    from src.repl.ui import search_preview

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
    for i, msg in enumerate(repl.messages):
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
            preview = search_preview(text_to_search, args, use_regex)
            results.append((i, role, preview))

    if not results:
        print(f"  {dim(f'No matches for: {args}')}")
        return

    print(f"  {bold(f'Search results for "{args}":')} {dim(f'({len(results)} matches)')}")
    print()
    for idx, role, preview in results:
        role_color = green if role == "user" else cyan
        print(f"  {dim(f'#{idx + 1}')} {role_color(role.title())} {preview}")


def handle_cd(repl: Repl, parts: list[str]) -> None:
    """Handle /cd command — change working directory."""
    if len(parts) < 2:
        wd = (
            repl.working_directory.replace(os.environ.get("HOME", "~"), "~")
            if "HOME" in os.environ
            else repl.working_directory
        )
        print(f"  {dim('Current directory:')} {cyan(wd)}")
        return

    path_str = " ".join(parts[1:]).strip()
    if not path_str:
        return

    new_path = os.path.abspath(os.path.join(repl.working_directory, path_str))
    if not os.path.isdir(new_path):
        print(f"  {red('✗')} {dim('Not a directory:')} {cyan(path_str)}")
        return

    old_wd = repl.working_directory
    repl.working_directory = new_path
    logger.info("Working directory changed: %s -> %s", old_wd, new_path)
    display_new = new_path.replace(os.environ.get("HOME", "~"), "~") if "HOME" in os.environ else new_path
    print(f"  {green('✓')} {dim('Changed directory:')} {cyan(display_new)}")


def handle_model(repl: Repl, parts: list[str]) -> None:
    """Handle /model command — show or switch the active model."""
    if len(parts) < 2:
        print(f"  {bold('Current Model:')} {cyan(repl.llm.model)}")
        print(f"  {dim('Usage: /model <model-name> to switch')}")
        print(f"  {dim('Example: /model claude-3-5-sonnet-20241022')}")
        return

    new_model = parts[1].strip()
    if not new_model:
        print(f"  {dim('Usage: /model <model-name>')}")
        return

    if new_model == repl.llm.model:
        print(f"  {dim('Already using')} {cyan(new_model)}")
        return

    old_model = repl.llm.model
    repl.llm.model = new_model
    logger.info("Model switched: %s -> %s", old_model, new_model)
    print(f"  {green('✓')} {dim('Model switched:')} {cyan(old_model)} {dim('→')} {cyan(new_model)}")


def handle_models(repl: Repl, args: str) -> None:
    """Show available model configurations."""
    model_mgr = getattr(repl, "_model_manager", None)
    if model_mgr is None:
        print(f"  Single model mode: {repl.llm.model}")
        print("  Configure multiple models in config.json under 'models' key.")
        return

    rows: list[list[str]] = [
        ["Current", model_mgr.current_model, ""],
    ]

    for mode, cfg in model_mgr.mode_configs.items():
        rows.append([mode.upper(), cfg.model, cfg.description])

    if model_mgr.read_only_config:
        ro = model_mgr.read_only_config
        rows.append(["read-only", ro.model, ro.description])

    print(f"\n  {bold('Model Configuration')}")
    print(f"  {'─' * 60}")
    print(f"  {'Mode':<20} {'Model':<35} {'Description'}")
    print(f"  {'─' * 60}")
    for row in rows:
        print(f"  {row[0]:<20} {cyan(row[1]):<35} {dim(row[2])}")


def handle_open(repl: Repl, parts: list[str]) -> None:
    """Handle /open command — interactive file finder with inline preview."""
    from src.repl.ui import format_size, get_file_icon, preview_file

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
        for root, dirs, files in os.walk(repl.working_directory):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for filename in files:
                if query_lower in filename.lower():
                    full_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(full_path, repl.working_directory)
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
        preview_file(full_path)
        return

    # Show numbered results with file icons and sizes
    print(f"\n  {bold(f'Files matching "{query}"')}  ({dim(str(len(matches)) + ' found')})")
    print(f"  {'─' * 60}")

    for i, (rel_path, full_path) in enumerate(matches[:20], 1):
        try:
            size = os.path.getsize(full_path)
            size_str = format_size(size)
        except OSError:
            size_str = "?"
        icon = get_file_icon(rel_path)
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
            preview_file(matches[idx][1])
        else:
            print(f"  {red('✗')} Invalid selection: {choice}")
    except ValueError:
        print(f"  {red('✗')} Invalid input")
    except EOFError, KeyboardInterrupt:
        print()


def handle_deps(repl: Repl, parts: list[str]) -> None:
    """Handle /deps command — show what a file imports."""
    _ensure_import_graph_built(repl)

    if len(parts) < 2:
        print(f"  {dim('Usage: /deps <file>')}")
        print(f"  {dim('Shows what the given Python file imports.')}")
        return

    raw_path = " ".join(parts[1:]).strip()
    filepath = _resolve_relative_path(repl, raw_path)
    if filepath is None:
        print(f"  {dim('File not found:')} {cyan(raw_path)}")
        return

    relpath = os.path.relpath(filepath, repl.working_directory)
    deps = repl._import_graph.get_dependencies(relpath) if repl._import_graph else []
    if not deps:
        print(f"  {dim('No project dependencies found for:')} {cyan(relpath)}")
        print(f"  {dim('(Standard library and third-party imports are excluded)')}")
        return

    print(f"  {bold(f'Dependencies of {relpath}:')}  {dim(f'({len(deps)} files)')}")
    print()
    for dep in deps:
        print(f"  {cyan('◈')} {dim(dep)}")


def handle_impact(repl: Repl, parts: list[str]) -> None:
    """Handle /impact command — show what imports a file (impact analysis)."""
    _ensure_import_graph_built(repl)

    if len(parts) < 2:
        print(f"  {dim('Usage: /impact <file>')}")
        print(f"  {dim('Shows which files import the given file (impact analysis).')}")
        return

    raw_path = " ".join(parts[1:]).strip()
    filepath = _resolve_relative_path(repl, raw_path)
    if filepath is None:
        print(f"  {dim('File not found:')} {cyan(raw_path)}")
        return

    relpath = os.path.relpath(filepath, repl.working_directory)
    dependents = repl._import_graph.get_dependents(relpath) if repl._import_graph else []
    if not dependents:
        print(f"  {dim('No files in the project import:')} {cyan(relpath)}")
        return

    print(f"  {bold(f'Impact analysis for {relpath}:')}  {dim(f'({len(dependents)} dependents)')}")
    print()
    for dep in dependents:
        print(f"  {yellow('◈')} {dim(dep)}")


def _resolve_relative_path(repl: Repl, raw_path: str) -> str | None:
    """Resolve a user-provided path relative to working_directory."""
    candidate = os.path.join(repl.working_directory, raw_path)
    if os.path.isfile(candidate):
        return os.path.abspath(candidate)
    # Try with .py extension
    candidate_py = candidate + ".py"
    if os.path.isfile(candidate_py):
        return os.path.abspath(candidate_py)
    return None


def _ensure_import_graph_built(repl: Repl) -> None:
    """Build the import graph if it hasn't been built yet."""
    if repl._import_graph is None or not repl._import_graph._built:
        spinner = Spinner("Building import graph...")
        spinner.start()
        try:
            repl._import_graph.build(repl.working_directory)  # type: ignore[union-attr]
            files = len(repl._import_graph.get_all_files())  # type: ignore[union-attr]
            spinner.stop(f"  {green('✓')} {dim(f'Import graph built ({files} files).')}")
        except Exception as exc:
            spinner.stop(f"  {red('✗ Error building import graph:')} {exc}")


def handle_python(repl: Repl) -> None:
    """Handle /python command — show Python REPL state."""
    repl_python = repl._get_or_create_python_repl()
    print(f"  {bold('Python REPL')}")
    print(f"  {dim('Executions:')} {cyan(str(repl_python.execution_count))}")
    print(f"  {dim('Errors:')}     {cyan(str(repl_python.error_count))}")
    print(f"  {dim('Variables:')}  {cyan(str(len(repl_python.get_variables())))}")
    print()
    print(f"  {dim('The python tool is available to the agent.')}")
    print(f"  {dim('Use the tool with: {"code": "print(1+1)"}')}")
    print(f"  {dim('Type /reset-python to clear REPL state.')}")


def handle_reset_python(repl: Repl) -> None:
    """Handle /reset-python command — reset the Python REPL."""
    repl_python = repl._get_or_create_python_repl()
    repl_python.reset()
    print(f"  {green('✓')} {dim('Python REPL reset. All variables cleared.')}")


def handle_plugins(repl: Repl, args: str) -> None:
    """Show loaded plugins and their status."""
    from pathlib import Path as _Path

    plugins_dir = _Path("plugins").resolve()
    if not plugins_dir.exists():
        print(f"  Plugins directory not found: {plugins_dir}")
        print("  Create a 'plugins/' directory and add plugins there.")
        return

    discovered: list[str] = []
    for entry in plugins_dir.iterdir():
        if entry.is_dir() and not entry.name.startswith(("__", ".")):
            plugin_file = entry / "plugin.py"
            if plugin_file.exists() or (entry / "__init__.py").exists():
                discovered.append(entry.name)

    if not discovered:
        print("  No plugins found in plugins/ directory.")
        return

    print(f"\n  {bold('Plugins')}")
    print(f"  {'─' * 60}")
    for name in discovered:
        print(f"  {green(name)}")
        # Try to read the description from the plugin file
        plugin_file = plugins_dir / name / "plugin.py"
        if plugin_file.exists():
            try:
                for line in plugin_file.read_text().split("\n"):
                    if line.startswith("__description__"):
                        desc = line.split("=")[1].strip().strip('"').strip("'")
                        print(f"    {dim(desc)}")
                        break
            except Exception:
                pass


def handle_changes(repl: Repl) -> None:
    """Handle /changes command — show session change log."""
    if not repl._change_log:
        print(f"  {dim('No changes recorded yet.')}")
        print(f"  {dim('File modifications via write_file, edit_file, or replace_in_files')}")
        print(f"  {dim('will appear here as they happen.')}")
        return

    print(f"  {bold('Session Change Log')}  {dim(f'({len(repl._change_log)} changes)')}")
    print()
    for entry in repl._change_log:
        ts = str(entry.get("timestamp", ""))
        if len(ts) > 19:
            ts = ts[:19]
        tool_name = str(entry.get("tool", "?"))
        path = str(entry.get("path", ""))
        summary = str(entry.get("summary", ""))
        rel_path = path
        if repl.working_directory and path:
            try:
                rel_path = os.path.relpath(str(path), repl.working_directory)
            except ValueError, OSError:
                pass
        print(f"  {dim(ts)} {cyan(tool_name):<18} {dim(rel_path)}")
        if summary:
            print(f"  {' ' * 20} {yellow(summary[:100])}")


def handle_timeline(repl: Repl) -> None:
    """Display the per-turn latency timeline (LLM vs tool execution times)."""
    if not repl._turn_timeline:
        print(f"  {dim('No timeline data yet.')}")
        return

    print(f"\n  {bold('Per-Turn Latency Timeline')}")
    print(f"  {'─' * 60}")

    max_total = max(e["total_duration"] for e in repl._turn_timeline)  # type: ignore[typeddict-item]
    bar_scale = 30 / max(max_total, 0.001)

    for entry in repl._turn_timeline:
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


def handle_reload(repl: Repl) -> None:
    """Re-discover and re-register all tools from disk."""
    from src.formatting import Spinner

    spinner = Spinner("Reloading tools...")
    spinner.start()
    try:
        count = repl.tools.rebuild()
        spinner.stop(f"  {green('✓')} {dim(f'Reloaded {count} tools.')}")
        # Show the freshly loaded tools
        for t in repl.tools.get_all():
            ro = f" {dim('(read-only)')}" if t.read_only else ""
            print(f"    {bold(t.name)}{dim(f' — {t.description}')}{ro}")
    except Exception as exc:
        spinner.stop(f"  {red('✗ Error reloading tools:')} {exc}")


def handle_config(repl: Repl) -> None:
    """Show current configuration."""
    print(f"  {bold('Configuration')}")
    print(f"  {dim('Model:')}       {cyan(repl.llm.model)}")
    print(f"  {dim('Max tokens:')}  {cyan(str(repl.max_tokens))}")
    print(f"  {dim('Temperature:')} {cyan(str(repl.llm.temperature))}")
    print(f"  {dim('Top-p:')}       {cyan(str(repl.llm.top_p))}")
    print(f"  {dim('Base URL:')}    {dim(str(repl.llm.client.base_url))}")
    if repl._custom_persona:
        print(f"  {dim('Persona:')}     {cyan(repl._custom_persona)}")
    else:
        print(f"  {dim('Persona:')}     {dim('(none)')}")

    # Show MCP server status
    if repl._mcp_bridge and repl._mcp_servers_config:
        print(f"  {dim('MCP servers:')}")
        for info in repl._mcp_bridge.get_server_info():
            status_label = f"{green('connected')}" if info["connected"] else f"{red('disconnected')}"
            transport: str = str(info["transport"])
            mcp_cfg_name: str = str(info["name"])
            print(f"    {dim('·')} {cyan(mcp_cfg_name)} {dim(f'({transport})')} {dim(status_label)}")


def handle_mcp(repl: Repl) -> None:
    """Show MCP server connection status and tools."""
    if not repl._mcp_bridge:
        print(f"  {dim('No MCP servers configured.')}")
        print(f"  {dim('Add mcpServers to config.json to connect.')}")
        return

    infos: list[dict[str, Any]] = repl._mcp_bridge.get_server_info()
    if not infos:
        print(f"  {dim('No MCP servers configured.')}")
        return

    total = int(sum(i["tool_count"] for i in infos))  # type: ignore[arg-type]
    connected = int(sum(1 for i in infos if i["connected"]))
    print(f"  {bold('MCP Servers')}  {dim(f'({connected}/{len(infos)} connected, {total} tools)')}")
    print()
    for info in infos:
        status_symbol = green("●") if info["connected"] else red("○")
        status_label = green("Connected") if info["connected"] else red("Disconnected")
        name: str = str(info["name"])
        print(f"  {status_symbol} {cyan(name)}  {dim(status_label)}")
        if info["connected"] and info["tools"]:
            tools_list: list[dict[str, Any]] = info["tools"]  # type: ignore[assignment]
            for t in tools_list:
                t_name: str = str(t.get("name", ""))
                t_desc: str = str(t.get("description", ""))
                print(f"     {dim('·')} {t_name}  {dim(t_desc[:60])}")
        if info.get("error"):
            err: str = str(info["error"])
            print(f"     {red('✗')} {dim(err)}")


def handle_budget(repl: Repl, args: str) -> None:
    """Handle /budget commands."""
    parts = args.strip().split()
    subcmd = parts[0].lower() if parts else ""

    if subcmd == "set":
        if len(parts) < 2:
            print("  Usage: /budget set <token_limit>")
            return
        try:
            limit = int(parts[1])
            if limit <= 0:
                print("  Budget must be positive.")
                return
            repl._token_budget = limit
            repl._token_budget_exceeded = False
            print(f"  Token budget set to {limit:,} tokens")
        except ValueError:
            print("  Invalid token limit.")

    elif subcmd == "reset":
        repl._total_tokens_used = 0
        repl._token_budget_exceeded = False
        print("  Token budget counter reset.")

    elif subcmd == "clear":
        repl._token_budget = None
        repl._token_budget_exceeded = False
        print("  Token budget cleared (unlimited).")

    else:
        # Show current status
        if repl._token_budget is None:
            print("  No token budget set (unlimited).")
        else:
            ratio = repl._total_tokens_used / repl._token_budget
            print(f"  Token budget: {repl._total_tokens_used:,} / {repl._token_budget:,} tokens ({ratio:.1%})")
            if repl._token_budget_exceeded:
                print(f"  {red('●')} Budget exceeded — in read-only mode")
        print("  Usage: /budget [set <limit>|reset|clear]")


def handle_summarize(repl: Repl, args: str) -> None:
    """Handle /summarize command."""
    if args.strip() == "on":
        repl._enable_summarization = True
        print(f"  {green('✓')} Automatic summarization enabled")
    elif args.strip() == "off":
        repl._enable_summarization = False
        print(f"  {dim('○')} Automatic summarization disabled")
    else:
        status = green("ON") if repl._enable_summarization else dim("OFF")
        print(f"  Automatic summarization: {status}")
        print("  Usage: /summarize on|off")


def handle_diff_review(repl: Repl, args: str = "") -> None:
    """Toggle interactive diff review mode."""
    parts = args.strip().split()
    if parts and parts[0].lower() == "on":
        repl._confirm_edits = True
    elif parts and parts[0].lower() == "off":
        repl._confirm_edits = False
    else:
        repl._confirm_edits = not repl._confirm_edits
    status = green("ON") if repl._confirm_edits else dim("OFF")
    print(f"  Diff review mode: {status}")


def handle_edit(repl: Repl) -> None:
    """Edit the last user message and re-send it."""
    from src.formatting import bold, cyan, dim, green, magenta

    idx = repl._get_last_user_index()
    if idx is None:
        print(f"  {dim('No previous user message to edit.')}")
        return

    old_content = cast("str", repl.messages[idx].get("content", ""))
    print(f"  {dim('Previous message:')}")
    print(f"  {dim('│')} {old_content[:200]}")
    if len(old_content) > 200:
        print(f"  {dim(f'└ [+{len(old_content) - 200} more chars]')}")
    print()

    try:
        mode_tag = (
            f"{magenta(repl.mode.upper())}"
            if repl.mode == "ask"
            else f"{yellow(repl.mode.upper())}"
            if repl.mode == "plan"
            else f"{cyan(repl.mode.upper())}"
        )
        wd = (
            repl.working_directory.replace(os.environ.get("HOME", "~"), "~")
            if "HOME" in os.environ
            else repl.working_directory
        )
        prompt = f"  {bold(mode_tag)} {cyan(wd)} {green('❯')} "
        new_line = input(prompt)
    except EOFError, KeyboardInterrupt:
        print()
        print(f"  {dim('Edit cancelled.')}")
        return

    new_line = new_line.strip()
    if not new_line:
        print(f"  {dim('Edit cancelled (empty input).')}")
        return

    # Replace the content
    repl.messages[idx]["content"] = new_line
    # Remove everything after the edited message (tool results, assistant responses)
    repl.messages = repl.messages[: idx + 1]

    print(f"  {dim('Message updated. Re-processing...')}")
    print()
    color_fn = repl._turn_separator_color()
    turn_label = f"  {color_fn('─ ')}Turn {repl._turn_number}{color_fn(' ' + '─' * (56 - len(str(repl._turn_number))))}"
    print(turn_label)
    repl._process_turn(new_line, color_fn)


def handle_retry(repl: Repl) -> None:
    """Re-send the last user message (same content)."""
    from src.formatting import dim

    idx = repl._get_last_user_index()
    if idx is None:
        print(f"  {dim('No previous user message to retry.')}")
        return

    content = cast("str", repl.messages[idx].get("content", ""))
    # Remove everything after the last user message
    repl.messages = repl.messages[: idx + 1]

    print(f"  {dim('Retrying last message...')}")
    print()
    color_fn = repl._turn_separator_color()
    turn_label = f"  {color_fn('─ ')}Turn {repl._turn_number}{color_fn(' ' + '─' * (56 - len(str(repl._turn_number))))}"
    print(turn_label)
    repl._process_turn(content, color_fn)


def handle_retry_auto(repl: Repl) -> None:
    """Re-send the last user message with an escalation prompt."""
    from src.formatting import dim, yellow

    idx = repl._get_last_user_index()
    if idx is None:
        print(f"  {dim('No previous user message to retry.')}")
        return

    content = cast("str", repl.messages[idx].get("content", ""))
    # Remove everything after the last user message
    repl.messages = repl.messages[: idx + 1]

    # Add an escalation instruction
    repl._task_attempts += 1
    escalation = (
        f"\n\n[IMPORTANT: Previous attempt(s) did not complete all requested tasks. "
        f"This is attempt #{repl._task_attempts}. Please be thorough, check your work, "
        f"and ensure ALL aspects of the request are completed. If a previous approach "
        f"failed, try a different strategy. Verify each step before proceeding.]"
    )
    repl.messages.append({"role": "user", "content": content + escalation})

    print(f"  {yellow('⟳')} {dim(f'Retrying with escalation (attempt {repl._task_attempts})...')}")
    print()
    color_fn = repl._turn_separator_color()
    turn_label = f"  {color_fn('─ ')}Turn {repl._turn_number}{color_fn(' ' + '─' * (56 - len(str(repl._turn_number))))}"
    print(turn_label)
    repl._process_turn(content + escalation, color_fn)
