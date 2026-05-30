from __future__ import annotations

from typing import Any

from src.logging_config import get_logger
from src.rag import RagConfig, RagIndex
from src.tools import Tool, ToolContext

logger = get_logger(__name__)


def execute(_args: dict[str, Any], ctx: ToolContext) -> str:
    """Show the status of the RAG index."""
    logger.info("rag_status called")

    # Get RagIndex from context
    rag_index: RagIndex | None = getattr(ctx, "rag_index", None)

    if rag_index is None:
        # Try to initialize from working directory
        rag_index = RagIndex(RagConfig(), ctx.working_directory)
        try:
            rag_index.initialize()
        except Exception as exc:
            logger.warning("Failed to initialize RAG index: %s", exc)
            return f"RAG index could not be initialised.\nWorking directory: {ctx.working_directory}\nError: {exc}"

    # Store back to context
    ctx.rag_index = rag_index

    return rag_index.status()


rag_status_tool = Tool(
    name="rag_status",
    description=(
        "Show the status of the RAG (Retrieval-Augmented Generation) index: "
        "number of chunks, files indexed, last indexed timestamp, vocabulary "
        "size, and configuration settings."
    ),
    input_schema={
        "type": "object",
        "properties": {},
    },
    execute=execute,
    read_only=True,
)
