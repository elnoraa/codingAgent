"""Agent class — a reusable, self-contained AI agent loop.

An ``Agent`` owns its own message buffer, tool registry, and configuration.
It is designed to be spawned by an ``Orchestrator`` (see :mod:`src.orchestrator`)
but can also run standalone.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import anthropic

from src.tools import Tool, ToolContext, ToolRegistry

from .client import LlmClient
from .logging_config import get_logger
from .utils import estimate_tokens, trim_messages

logger = get_logger(__name__)


# ── Data types ─────────────────────────────────────────────────────────────────


@dataclass
class AgentConfig:
    """Configuration for an Agent instance."""

    llm: LlmClient
    system_prompt: str
    max_tokens: int
    mode: str = "code"
    working_directory: str = "."
    custom_persona: str = ""
    tools: ToolRegistry | None = None
    context_files: list[str] | None = None
    role: str = "code"
    """Agent role: 'code', 'plan', 'ask', 'worker', 'observer'.

    - code / worker: all tools available
    - plan / ask / observer: read-only tools only
    """


@dataclass
class AgentResult:
    """Structured result from a completed agent run."""

    summary: str = ""
    output: str = ""
    files_changed: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None


@dataclass
class AgentCallbacks:
    """Callbacks the Agent uses to communicate with the outside world.

    All callbacks are optional — pass ``None`` for any you do not need.
    """

    on_text: Callable[[str], None] | None = None
    on_tool_call: Callable[[str, dict[str, object]], None] | None = None
    on_tool_result: Callable[[str, str], None] | None = None
    on_llm_round_start: Callable[[], None] | None = None
    on_interactive_tool: Callable[[Tool, dict[str, object]], str] | None = None
    on_error: Callable[[str], None] | None = None
    on_trim_warning: Callable[[int], None] | None = None


# ── Agent class ────────────────────────────────────────────────────────────────


class Agent:
    """A reusable agent instance with its own message history and tools."""

    def __init__(
        self,
        agent_id: str,
        config: AgentConfig,
    ) -> None:
        self.agent_id = agent_id
        self.config = config
        self.messages: list[dict[str, object]] = []
        self.tool_registry: ToolRegistry = config.tools or ToolRegistry()
        self._start_time: float = 0.0
        self._input_tokens: int = 0
        self._output_tokens: int = 0
        self._change_log: list[dict[str, object]] = []
        self._file_snapshots: dict[str, list[tuple[str, str]]] = {}

        logger.info(
            "Agent initialized: id=%s, role=%s, mode=%s, model=%s",
            agent_id,
            config.role,
            config.mode,
            config.llm.model,
        )

    # ── Public API ─────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Clear messages and reset cumulative state."""
        self.messages.clear()
        self._input_tokens = 0
        self._output_tokens = 0
        self._change_log.clear()
        self._file_snapshots.clear()

    def send_message(self, content: str, role: str = "user") -> None:
        """Append a message to this agent's buffer."""
        self.messages.append({"role": role, "content": content})

    def get_last_assistant_text(self) -> str:
        """Return the most recent assistant response as plain text."""
        for msg in reversed(self.messages):
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    texts: list[str] = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            t = block.get("text", "")
                            if isinstance(t, str):
                                texts.append(t)
                    return "\n".join(texts)
        return ""

    @property
    def is_read_only(self) -> bool:
        """Return True if this agent's role is read-only."""
        return self.config.role in ("plan", "ask", "observer")

    # ── Core run method ───────────────────────────────────────────────────

    def run(
        self,
        user_input: str,
        context: ToolContext,
        callbacks: AgentCallbacks | None = None,
    ) -> AgentResult:
        """Execute one task from ``user_input`` through the LLM loop.

        Parameters
        ----------
        user_input:
            The user message that starts this run.
        context:
            Shared tool execution context (working directory, snapshots, …).
        callbacks:
            Optional hooks for streaming output, tool display, etc.

        Returns
        -------
        AgentResult
            Structured result with output text, token usage, and error info.
        """
        result = AgentResult()
        self._start_time = time.time()

        # ── Append the user message ────────────────────────────────────────
        self.messages.append({"role": "user", "content": user_input})

        # ── Build system prompt ────────────────────────────────────────────
        system_prompt = self._build_system_prompt()

        # ── Trim messages to fit context window ────────────────────────────
        current_system_tokens = estimate_tokens(system_prompt)
        trimmed = trim_messages(self.messages, self.config.max_tokens, current_system_tokens)
        dropped = len(self.messages) - len(trimmed)
        if dropped > 0 and callbacks and callbacks.on_trim_warning:
            callbacks.on_trim_warning(dropped)
        self.messages = trimmed

        try:
            # ── Token tracking ─────────────────────────────────────────────
            tokens_before = sum(estimate_tokens(str(m.get("content", ""))) for m in self.messages)

            # ── Environment variables for tools ────────────────────────────
            os.environ["CODING_AGENT_MODE"] = self.config.mode
            os.environ["CODING_AGENT_MODEL"] = self.config.llm.model
            os.environ["CODING_AGENT_MAX_TOKENS"] = str(self.config.max_tokens)
            os.environ["CODING_AGENT_TEMPERATURE"] = str(self.config.llm.temperature)
            os.environ["CODING_AGENT_PERSONA"] = self.config.custom_persona or ""

            # ── Run the LLM chat loop ──────────────────────────────────────
            self.config.llm.chat_with_tools(
                messages=self.messages,
                system=system_prompt,
                tools=self.tool_registry,
                context=context,
                on_text=callbacks.on_text if callbacks and callbacks.on_text else _noop_on_text,
                on_tool_call=callbacks.on_tool_call if callbacks and callbacks.on_tool_call else _noop_on_tool_call,
                on_tool_result=(
                    lambda name, r: (
                        callbacks.on_tool_result(name, r) if callbacks and callbacks.on_tool_result else None
                    )
                ),
                read_only=self.is_read_only,
                on_llm_round_start=(callbacks.on_llm_round_start if callbacks else None),
                on_interactive_tool=(callbacks.on_interactive_tool if callbacks else None),
            )

            # ── Token accounting ───────────────────────────────────────────
            tokens_after = sum(estimate_tokens(str(m.get("content", ""))) for m in self.messages)
            turn_tokens = tokens_after - tokens_before
            estimated_input = turn_tokens // 2
            estimated_output = turn_tokens - estimated_input
            self._input_tokens += estimated_input
            self._output_tokens += estimated_output
            result.input_tokens = estimated_input
            result.output_tokens = estimated_output

            # ── Build result ───────────────────────────────────────────────
            result.output = self.get_last_assistant_text()
            result.summary = result.output[:200] if result.output else ""
            result.files_changed = self._collect_changed_files()

        except anthropic.APIConnectionError as exc:
            error_msg = f"Connection error: {exc}"
            logger.error("Agent %s: %s", self.agent_id, error_msg)
            result.error = error_msg
            if callbacks and callbacks.on_error:
                callbacks.on_error(error_msg)
        except anthropic.RateLimitError:
            error_msg = "Rate limit exceeded"
            logger.error("Agent %s: %s", self.agent_id, error_msg)
            result.error = error_msg
            if callbacks and callbacks.on_error:
                callbacks.on_error(error_msg)
        except anthropic.InternalServerError as exc:
            error_msg = f"Server error: {exc}"
            logger.error("Agent %s: %s", self.agent_id, error_msg)
            result.error = error_msg
            if callbacks and callbacks.on_error:
                callbacks.on_error(error_msg)
        except anthropic.APIError as exc:
            error_msg = f"API error: {exc}"
            logger.error("Agent %s: %s", self.agent_id, error_msg)
            result.error = error_msg
            if callbacks and callbacks.on_error:
                callbacks.on_error(error_msg)
        except Exception as exc:
            error_msg = f"Unexpected error: {exc}"
            logger.error("Agent %s: %s", self.agent_id, error_msg, exc_info=True)
            result.error = error_msg
            if callbacks and callbacks.on_error:
                callbacks.on_error(error_msg)

        return result

    # ── Internal helpers ───────────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        """Build the full system prompt for this agent's role and config."""
        from .mode import ASK_MODE_SYSTEM_PROMPT, PLAN_MODE_SYSTEM_PROMPT

        if self.config.role == "plan":
            base = PLAN_MODE_SYSTEM_PROMPT
        elif self.config.role == "ask":
            base = ASK_MODE_SYSTEM_PROMPT
        else:
            base = self.config.system_prompt

        persona = f"\n\n{self.config.custom_persona}" if self.config.custom_persona else ""

        # ── Context files injection ────────────────────────────────────────
        context_section = ""
        if self.config.context_files:
            import glob as _glob

            injected: list[str] = []
            for pattern in self.config.context_files:
                matched = _glob.glob(os.path.join(self.config.working_directory, pattern))
                for filepath in matched:
                    if not os.path.isfile(filepath):
                        continue
                    try:
                        with open(filepath, encoding="utf-8", errors="replace") as f:
                            content = f.read(2000)
                        relpath = os.path.relpath(filepath, self.config.working_directory)
                        injected.append(f"### `{relpath}`\n```\n{content}\n```")
                    except OSError:
                        continue
            if injected:
                context_section = "\n\n## Project Context Files\n" + "\n\n".join(injected)

        return (
            f"Current working directory: {self.config.working_directory}\n"
            f"Project root: {self.config.working_directory}\n\n"
            f"{base}\n\n"
            f"Remember to explore the codebase with read-only tools before making changes."
            f"{persona}"
            f"{context_section}"
        )

    def _collect_changed_files(self) -> list[str]:
        """Return list of file paths modified during this run."""
        return [str(entry.get("path", "")) for entry in self._change_log if entry.get("path")]


# ── No-op callbacks (prevent NoneType errors) ──────────────────────────────────


def _noop_on_text(text: str) -> None:
    pass


def _noop_on_tool_call(name: str, args: dict[str, object]) -> None:
    pass
