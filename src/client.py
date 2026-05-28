from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from anthropic import Anthropic
from anthropic.types import MessageParam, ToolParam
from tools import ToolContext, ToolRegistry


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

        while True:
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
                return

            tool_results: list[dict[str, object]] = []
            for block in tool_blocks:
                name = block.name
                args: dict[str, object] = dict(block.input) if hasattr(block.input, "items") else block.input  # type: ignore[assignment]
                on_tool_call(name, args)

                tool = tools.get(name)
                if tool is None:
                    available = ", ".join(t.name for t in tools.get_all())
                    result = f'Error: unknown tool "{name}". Available tools: {available}'
                else:
                    try:
                        result = tool.execute(args, context)
                    except Exception as exc:
                        result = f"Error executing {name}: {exc}"

                on_tool_result(name, result)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }
                )

            messages.append({"role": "user", "content": tool_results})
