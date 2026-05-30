from __future__ import annotations

from typing import Any

from src.logging_config import get_logger
from src.rag import RagConfig, RagIndex, format_query_results
from src.tools import Tool, ToolContext

logger = get_logger(__name__)


def execute(args: dict[str, Any], ctx: ToolContext) -> str:
    """Semantically search the project codebase using natural language."""
    query = args.get("query")
    max_results = int(args.get("maxResults", 5))
    min_score = float(args.get("minScore", 0.05))
    file_filter = args.get("fileFilter")

    logger.info(
        "rag_query: query=%s, maxResults=%d, minScore=%f, fileFilter=%s",
        query,
        max_results,
        min_score,
        file_filter,
    )

    if not query:
        return 'Error: missing required argument "query".'

    # Get RagIndex from context
    rag_index: RagIndex | None = getattr(ctx, "rag_index", None)

    if rag_index is None:
        # Try to initialize from working directory
        rag_index = RagIndex(RagConfig(), ctx.working_directory)
        try:
            rag_index.initialize()
        except Exception as exc:
            logger.warning("Failed to initialize RAG index: %s", exc)

    if rag_index is None or not rag_index._initialized:
        return (
            "RAG index is not available. "
            "Use the rag_index tool to build an index first:\n"
            "  rag_index(mode='project')\n\n"
            "This will scan your project files and build a search index."
        )

    if not rag_index.documents:
        return (
            "The RAG index is empty. "
            "Use the rag_index tool to build an index first:\n"
            "  rag_index(mode='project')\n\n"
            "This will scan your project files and build a search index."
        )

    results = rag_index.query(
        text=query,
        top_k=max_results,
        min_score=min_score,
        file_filter=file_filter,
    )

    return format_query_results(results, query)


rag_query_tool = Tool(
    name="rag_query",
    description=(
        "Semantically search the project codebase using natural language. "
        "Returns relevant code chunks with file paths, line numbers, and "
        "relevance scores. Requires the index to be built first using rag_index. "
        "This is more powerful than grep for finding code by concept or meaning."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language query describing what code you are looking for",
            },
            "maxResults": {
                "type": "number",
                "description": "Maximum number of results to return (default: 5)",
            },
            "minScore": {
                "type": "number",
                "description": "Minimum similarity score threshold (0.0-1.0, default: 0.05)",
            },
            "fileFilter": {
                "type": "string",
                "description": (
                    "Optional glob pattern to filter results by file path (e.g. '**/*.py' for Python files only)"
                ),
            },
        },
        "required": ["query"],
    },
    execute=execute,
    read_only=True,
)
