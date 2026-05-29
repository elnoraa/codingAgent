from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from anthropic import Anthropic
from anthropic.types import MessageParam, ToolParam
from src.tools import Tool, ToolContext, ToolRegistry

from .logging_config import get_logger
from .utils import compute_backoff, is_transient_error

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
        # Budget check callback — if set and returns False, LLM calls are blocked
        self.on_budget_check: Callable[[], bool] | None = None
        logger.info(
            "Client initialized: model=%s, max_tokens=%s, temperature=%s, top_p=%s",
            model,
            max_tokens,
            temperature,
            top_p,
        )

    def chat_sync(self, prompt: str, max_tokens: int = 500) -> str:
        """Make a non-streaming synchronous chat completion (for summarization)."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        if response.content:
            first_block = response.content[0]
            # Handle TextBlock or similar response types
            text = getattr(first_block, "text", str(first_block))
            return str(text) if text else ""
        return ""

    def chat_stream(
        self,
        messages: list[dict[str, object]],
        system: str,
        on_text: Callable[[str], None],
        on_retry: Callable[[int, float], None] | None = None,
    ) -> str:
        """Stream a chat completion with retry on transient errors.

        Args:
            messages: The conversation messages.
            system: The system prompt.
            on_text: Callback for each text chunk.
            on_retry: Optional callback with (attempt_number, delay_seconds)
                called before each retry. Useful for showing user-facing messages.
        """
        last_exception: Exception | None = None
        for attempt in range(5):  # max 5 retries
            try:
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
            except Exception as exc:
                if attempt < 4 and is_transient_error(exc):
                    delay = compute_backoff(attempt)
                    logger.warning(
                        "Transient API error (attempt %d/5): %s. Retrying in %.1fs...",
                        attempt + 1, exc, delay,
                    )
                    if on_retry:
                        on_retry(attempt + 1, delay)
                    time.sleep(delay)
                    last_exception = exc
                else:
                    raise
        raise last_exception  # type: ignore[misc] — will only be None if loop never ran

    def _send_with_retry(
        self,
        messages: list[dict[str, object]],
        system: str,
        tool_defs: list[dict[str, object]],
        **extra: Any,
    ) -> Any:
        """Send a messages API request with retry on transient errors.

        Returns the stream context manager for use with ``with``.
        """
        last_exception: Exception | None = None
        for attempt in range(5):
            try:
                return self.client.messages.stream(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=system,
                    messages=cast("list[MessageParam]", messages),
                    tools=cast("list[ToolParam]", tool_defs),
                    **extra,  # type: ignore[arg-type]
                )
            except Exception as exc:
                if attempt < 4 and is_transient_error(exc):
                    delay = compute_backoff(attempt)
                    logger.warning(
                        "Transient API error (attempt %d/5): %s. Retrying in %.1fs...",
                        attempt + 1, exc, delay,
                    )
                    time.sleep(delay)
                    last_exception = exc
                else:
                    raise
        raise last_exception  # type: ignore[misc]

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
        on_llm_round_start: Callable[[], None] | None = None,
        on_interactive_tool: Callable[[Tool, dict[str, object]], str] | None = None,
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

            # Check token budget before each API call
            if self.on_budget_check and not self.on_budget_check():
                logger.warning("Token budget exceeded, stopping LLM calls")
                return

            if on_llm_round_start is not None:
                on_llm_round_start()

            with self._send_with_retry(messages, system, tool_defs, **extra) as stream:
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
                elif read_only and not tool.read_only:
                    result = (
                        f'Error: tool "{name}" is not available in read-only mode. '
                        f"Switch to CODE mode (use /code) to use this tool."
                    )
                    logger.warning(
                        "Blocked write tool '%s' in read-only mode (agent=%s)",
                        name, context.agent_id if context else "?",
                    )
                elif tool.interactive and on_interactive_tool is not None:
                    # Interactive tool: pause and get user input via callback
                    logger.info("Interactive tool %s called, requesting user input", name)
                    result = on_interactive_tool(tool, args)
                    logger.info("Interactive tool %s completed (result_len=%d)", name, len(result))
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


# ── Multi-Model Routing ────────────────────────────────────────────────


@dataclass
class ModelConfig:
    """Configuration for a single model."""
    model: str
    max_tokens: int = 8192
    temperature: float = 0.7
    top_p: float = 1.0
    description: str = ""


class MultiModelClient:
    """Client that can switch between multiple models based on routing strategy."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        default_config: ModelConfig,
        mode_configs: dict[str, ModelConfig] | None = None,
        read_only_config: ModelConfig | None = None,
        strategy: str = "mode",
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.default_config = default_config
        self.mode_configs = mode_configs or {}
        self.read_only_config = read_only_config
        self.strategy = strategy
        self._current_config: ModelConfig = default_config

    def get_client_for_mode(self, mode: str, read_only: bool = False) -> LlmClient:
        """Get an LlmClient configured for the given mode."""
        if read_only and self.read_only_config:
            config = self.read_only_config
        else:
            config = self.mode_configs.get(mode, self.default_config)

        self._current_config = config
        return LlmClient(
            api_key=self.api_key,
            base_url=self.base_url,
            model=config.model,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            top_p=config.top_p,
        )

    @property
    def current_model(self) -> str:
        return self._current_config.model

    @property
    def current_max_tokens(self) -> int:
        return self._current_config.max_tokens


# Parameter names whose values should be redacted in logs
SENSITIVE_PARAMS = frozenset({
    "password", "passwd", "secret", "api_key", "apiKey",
    "token", "auth_token", "access_token", "private_key",
    "apikey", "api-key", "api.token",
})


def _summarize_args(args: dict[str, object]) -> str:
    """Return a concise summary of tool arguments (for logging).

    Sensitive parameter values (passwords, keys, tokens) are
    automatically redacted as ``****``.
    """
    parts: list[str] = []
    for k, v in args.items():
        if k in SENSITIVE_PARAMS:
            parts.append(f"{k}=****")
        elif isinstance(v, str):
            if len(v) > 80:
                parts.append(f"{k}={v[:80]}...")
            else:
                parts.append(f"{k}={v}")
        else:
            parts.append(f"{k}={v!r}")
    return ", ".join(parts)
