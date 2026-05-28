from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, cast

from anthropic import Anthropic
from anthropic.types import MessageParam, ToolParam
from tools import ToolContext, ToolRegistry

from .logging_config import get_logger

logger = get_logger(__name__)


class LlmClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        max_tokens: int,
        temperature: float = 0.7,
        top_p: float = 1.0,
    ) -> None:
        self.client = Anthropic(api_key=api_key, base_url=base_url)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p
        logger.info(
            "Client initialized: model=%s, max_tokens=%s, temperature=%s, top_p=%s",
            model,
            max_tokens,
            temperature,
            top_p,
        )

    def chat_stream(
        self,
        messages: list[dict[str, object]],
        system: str,
        on_text: Callable[[str], None],
    ) -> str:
        with self.client.messages.stream(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=cast("list[MessageParam]", messages),
        ) as stream:
            full_text = ""
            for text in stream.text_stream:
                full_text += text
                on_text(text)
            return full_text

    def chat_with_tools(
        self,
        messages: list[dict[str, object]],
        system: str,
        tools: ToolRegistry,
        context: ToolContext,
        on_text: Callable[[str], None],
        on_tool_call: Callable[[str, dict[str, object]], None],
        on_tool_result: Callable[[str, str], None],
        read_only: bool = False,
    ) -> None:
        tool_defs = tools.to_anthropic_tools(read_only=read_only)

        # Build extra body params if non-default
        extra: dict[str, Any] = {}
        if self.temperature != 0.7:
            extra["temperature"] = self.temperature
        if self.top_p != 1.0:
            extra["top_p"] = self.top_p

        logger.info("Starting chat (read_only=%s, messages=%d, tools=%d)", read_only, len(messages), len(tool_defs))
        loop_count = 0

        while True:
            loop_count += 1
            logger.debug("API request loop=%d (messages=%d)", loop_count, len(messages))

            with self.client.messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=cast("list[MessageParam]", messages),
                tools=cast("list[ToolParam]", tool_defs),
                **extra,  # type: ignore[arg-type]
            ) as stream:
                for text in stream.text_stream:
                    on_text(text)
                response = stream.get_final_message()

            messages.append({"role": "assistant", "content": response.model_dump()["content"]})

            tool_blocks = [b for b in response.content if b.type == "tool_use"]
            if not tool_blocks:
                logger.info("Chat completed (loop=%d, no more tool calls)", loop_count)
                return

            logger.info("Tool call round %d: %d tool(s) requested", loop_count, len(tool_blocks))

            tool_results: list[dict[str, object]] = []
            for block in tool_blocks:
                name = block.name
                args: dict[str, object] = dict(block.input) if hasattr(block.input, "items") else block.input  # type: ignore[assignment]
                on_tool_call(name, args)

                tool = tools.get(name)
                if tool is None:
                    available = ", ".join(t.name for t in tools.get_all())
                    result = f'Error: unknown tool "{name}". Available tools: {available}'
                    logger.warning("Unknown tool called: %s", name)
                else:
                    try:
                        logger.debug("Executing tool: %s with args=%s", name, _summarize_args(args))
                        result = tool.execute(args, context)
                        logger.info("Tool %s completed (result_len=%d)", name, len(result))
                    except Exception as exc:
                        result = f"Error executing {name}: {exc}"
                        logger.error("Tool %s raised exception: %s", name, exc)

                on_tool_result(name, result)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }
                )

            messages.append({"role": "user", "content": tool_results})


def _summarize_args(args: dict[str, object]) -> str:
    """Return a concise summary of tool arguments (for logging)."""
    parts: list[str] = []
    for k, v in args.items():
        if isinstance(v, str):
            if len(v) > 80:
                parts.append(f"{k}={v[:80]}...")
            else:
                parts.append(f"{k}={v}")
        else:
            parts.append(f"{k}={v!r}")
    return ", ".join(parts)
