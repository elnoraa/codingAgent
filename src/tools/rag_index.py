from __future__ import annotations

from typing import Any

from src.logging_config import get_logger
from src.rag import RagConfig, RagIndex
from src.tools import Tool, ToolContext

logger = get_logger(__name__)


def execute(args: dict[str, Any], ctx: ToolContext) -> str:
    """Build or update the RAG semantic search index."""
    mode = str(args.get("mode", "project"))
    path_arg = args.get("path")
    clear = bool(args.get("clear", False))

    logger.info("rag_index: mode=%s, path=%s, clear=%s", mode, path_arg, clear)

    # Get or create RagIndex from context
    rag_index: RagIndex | None = getattr(ctx, "rag_index", None)
    if rag_index is None:
        # Lazily create one
        rag_index = RagIndex(RagConfig(), ctx.working_directory)
        rag_index.initialize()

    if clear:
        rag_index.clear()
        # Store back to context for caller
        ctx.rag_index = rag_index
        return "RAG index cleared."

    if mode == "clear":
        rag_index.clear()
        ctx.rag_index = rag_index
        return "RAG index cleared."

    rag_index.initialize()

    if mode == "file":
        if not path_arg:
            return 'Error: mode="file" requires a "path" argument.'
        chunks = rag_index.index_file(path_arg)
        stats = rag_index.status()
        return f"Indexed file: {path_arg}\nChunks added: {chunks}\n\n{stats}"

    # mode == "project" or "auto"
    directory = path_arg if path_arg else None
    result = rag_index.index_project(directory)
    ctx.rag_index = rag_index

    if "error" in result:
        return f"Error: {result['error']}"

    return (
        f"Indexing complete.\n"
        f"  Files indexed: {result['indexed_files']}\n"
        f"  Files skipped: {result['skipped_files']}\n"
        f"  Chunks added:  {result['total_chunks']}\n"
        f"  Total chunks:  {result['total_documents']}\n"
        f"  Duration:      {result['duration_seconds']}s\n\n"
        f"{rag_index.status()}"
    )


rag_index_tool = Tool(
    name="rag_index",
    description=(
        "Build or update a semantic search index over project files. "
        "Use this to index your codebase for RAG (Retrieval-Augmented Generation). "
        "After indexing, use rag_query to semantically search your codebase. "
        "Can index the entire project ('project'), a single file ('file'), "
        "or clear the index ('clear')."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["project", "file", "clear"],
                "description": (
                    "'project' (default) — scan the working directory and index all files. "
                    "'file' — index a single file (requires 'path'). "
                    "'clear' — clear the entire index."
                ),
                "default": "project",
            },
            "path": {
                "type": "string",
                "description": (
                    "Relative or absolute path to a file or directory "
                    "(required for mode='file', optional for mode='project')."
                ),
            },
            "clear": {
                "type": "boolean",
                "description": "If True, clear the existing index before indexing.",
                "default": False,
            },
        },
    },
    execute=execute,
    read_only=True,
)
