"""Export commands — /export."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from src.formatting import bold, dim, green, cyan, red
from src.repl.ui import format_size

if TYPE_CHECKING:
    from src.repl.repl import Repl

logger = logging.getLogger(__name__)


def handle_export(repl: "Repl", parts: list[str]) -> None:
    """Handle /export command — export conversation as Markdown, JSON, or full .agent-session."""
    from src.exporter import export_as_markdown, export_as_json
    from src.exporter import export_full_session, load_session_file, export_summary
    from datetime import datetime as _dt

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

    if not repl.messages:
        print(f"  {dim('No messages to export.')}")
        return

    try:
        if fmt == "session":
            filename = output_path or f"session_{_dt.now().strftime('%Y%m%d_%H%M%S')}.agent-session"
            if not filename.endswith(".agent-session"):
                filename += ".agent-session"

            # Gather session data
            metadata: dict[str, Any] = {
                "model": repl.llm.model,
                "mode": repl.mode,
                "messages": len(repl.messages),
            }

            result = export_full_session(
                output_path=os.path.join(os.getcwd(), filename),
                messages=list(repl.messages),
                metadata=metadata,
                working_directory=repl.working_directory,
            )

            if result.endswith(".agent-session"):
                size = format_size(os.path.getsize(result))
                print(f"  {green('✓')} Session exported: {result} ({size})")
                # Show summary
                data = load_session_file(result)
                if data:
                    print(export_summary(data))
            else:
                print(f"  {red('✗')} {result}")
        elif fmt == "json":
            filepath = export_as_json(repl.messages, repl.mode, repl.llm.model, output_path)
            print(f"  {green('✓')} {dim('Exported to')} {cyan(filepath)}")
        else:
            filepath = export_as_markdown(repl.messages, repl.mode, repl.llm.model, output_path)
            print(f"  {green('✓')} {dim('Exported to')} {cyan(filepath)}")
    except Exception as exc:
        print(f"  {red('✗ Export failed:')} {exc}")
