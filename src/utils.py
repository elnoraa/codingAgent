"""Utility functions for the Coding Agent.

This module provides core utilities used across the codebase:
- Token estimation and message trimming
- Exponential backoff for retries
- Conversation summarization (slimmed down; formatting, validation,
  security, and rate-limiting utilities have been moved to their
  own modules).
"""

from __future__ import annotations

import json
import random as _random
from typing import Any, cast

from .logging_config import get_logger
from .security import redact_sensitive_content

logger = get_logger(__name__)

# Re-export common symbols from sub-modules for backward compatibility.
# New code should import directly from the appropriate module.
from .formatting import (  # noqa: F401
    R,
    Spinner,
    _code,
    blue,
    bold,
    color_json,
    cyan,
    dim,
    green,
    magenta,
    print_error,
    print_info,
    print_panel,
    print_separator,
    print_success,
    print_table,
    print_warning,
    red,
    show_diff_and_confirm,
    yellow,
)
from .markdown import (  # noqa: F401
    EXTENSION_LANG_MAP,
    detect_language,
    highlight_code,
    render_markdown,
)
from .rate_limiter import RateLimiter  # noqa: F401
from .security import (  # noqa: F401
    _EXFIL_NETWORK_COMMANDS,
    _EXFIL_SENSITIVE_FILES,
    _SCRIPT_FILE_READ_INDICATORS,
    _SCRIPT_INTERPRETERS,
    _SCRIPT_NETWORK_INDICATORS,
    strip_dangerous_ansi,
    validate_url_target,
)
from .validation import (  # noqa: F401
    MAX_CODE_LENGTH,
    MAX_COMMAND_LENGTH,
    MAX_FILE_CONTENT,
    MAX_PATH_LENGTH,
    MAX_QUERY_LENGTH,
    MAX_TEXT_LENGTH,
    MAX_URL_LENGTH,
    validate_length,
    validate_walk_path,
    validate_write_path,
    validate_write_path_atomic,
)

# ── Context management ─────────────────────────────────────────────────────

CHARS_PER_TOKEN = 4
TRIM_THRESHOLD = 0.75


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def _message_token_count(msg: dict[str, object]) -> int:
    content = msg.get("content", "")
    if isinstance(content, str):
        return estimate_tokens(content)
    if not isinstance(content, list):
        return 0
    content = cast("list[dict[str, object]]", content)
    total = 0
    for block in content:
        t = block.get("text")
        if isinstance(t, str):
            total += estimate_tokens(t)
        c = block.get("content")
        if isinstance(c, str):
            total += estimate_tokens(c)
        i = block.get("input")
        if i is not None:
            total += estimate_tokens(json.dumps(i))
    return total


def trim_messages(
    messages: list[dict[str, object]],
    max_tokens: int,
    system_tokens: int,
    client: Any | None = None,  # for summarization
    summarization_threshold: float = 0.9,
) -> list[dict[str, object]]:
    """Trim messages to fit within context window, optionally summarizing."""
    threshold = int(max_tokens * TRIM_THRESHOLD)
    available = threshold - system_tokens
    if available <= 0:
        return messages

    total = sum(_message_token_count(m) for m in messages)
    if total <= available:
        return messages

    # Optionally summarize oldest messages instead of dropping them
    if client is not None and total > int(max_tokens * summarization_threshold):
        # Try summarizing the earliest 50% of messages
        mid = len(messages) // 2
        early_msgs = messages[:mid]
        late_msgs = messages[mid:]

        summary = summarize_conversation(early_msgs, client)
        if summary:
            summary_msg: dict[str, object] = {
                "role": "user",
                "content": f"[Summary of earlier conversation: {summary}]",
            }
            combined: list[dict[str, object]] = [summary_msg] + late_msgs  # type: ignore[operator]
            return _strip_orphaned_tool_results(combined)

    # Fall back to standard trimming
    kept: list[dict[str, object]] = []
    budget = available

    for msg in reversed(messages):
        cost = _message_token_count(msg)
        if budget - cost >= 0 or not kept:
            kept.insert(0, msg)
            budget -= cost
        else:
            break

    if len(kept) < len(messages):
        dropped = len(messages) - len(kept)
        kept.insert(
            0,
            {
                "role": "user",
                "content": (
                    f"[System: {dropped} earlier message{' was' if dropped == 1 else 's were'}"
                    " removed to stay within context limits.]"
                ),
            },
        )

    return _strip_orphaned_tool_results(kept)


def _strip_orphaned_tool_results(
    messages: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Remove tool_result messages whose preceding tool_use was dropped by trimming."""
    cleaned: list[dict[str, object]] = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            blocks = cast("list[dict[str, object]]", content)
            is_tool_result = any(b.get("type") == "tool_result" for b in blocks)
            if is_tool_result and (not cleaned or cleaned[-1].get("role") != "assistant"):
                continue
        cleaned.append(msg)
    return cleaned


# ── Retry / backoff utilities ─────────────────────────────────────────────

DEFAULT_MAX_RETRIES = 5
DEFAULT_BASE_DELAY = 1.0
DEFAULT_MAX_DELAY = 60.0


def compute_backoff(
    attempt: int,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    jitter: bool = True,
) -> float:
    """Compute exponential backoff delay using full jitter.

    delay = random(0, min(base_delay * 2^attempt, max_delay))

    Full jitter (AWS recommended) is used when jitter=True:
    delay = random_uniform(0, cap)

    This spreads retries more evenly than additive jitter.
    """
    cap = min(base_delay * (2**attempt), max_delay)
    if jitter:
        return _random.uniform(0, cap)
    return cap


def is_transient_error(error: Exception) -> bool:
    """Return True if the error is likely transient and retryable."""
    from anthropic import (
        APIConnectionError,
        APIStatusError,
        InternalServerError,
        RateLimitError,
    )

    if isinstance(error, (APIConnectionError, RateLimitError, InternalServerError)):
        return True
    if isinstance(error, APIStatusError) and error.status_code in (429, 502, 503, 504):
        return True
    return False


# ── Conversation Summarization ──────────────────────────────────────────


def summarize_conversation(
    messages: list[dict[str, object]],
    client: Any,  # LlmClient instance
) -> str:
    """Summarize a list of messages into a condensed form using the LLM.

    Returns a summary string that can replace the original messages.

    Note: Sensitive content (API keys, passwords, etc.) is automatically
    redacted from the messages before sending to the LLM.
    """
    # Build a condensed version of the messages for the summarizer prompt
    text_parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, str):
            # Redact sensitive content before summarization
            redacted = redact_sensitive_content(content[:500])
            text_parts.append(f"[{role}]: {redacted}")
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    t = block.get("text") or block.get("content", "")
                    if isinstance(t, str):
                        redacted = redact_sensitive_content(t[:500])
                        text_parts.append(f"[{role}]: {redacted}")

    conversation_text = "\n".join(text_parts)

    prompt = (
        "Summarize the following conversation between a user and an AI coding assistant. "
        "Focus on: the user's goals, what files have been discussed or modified, "
        "key decisions made, and what the current state of work is. "
        "Keep the summary concise but informative (2-3 paragraphs).\n\n"
        f"{conversation_text}"
    )

    try:
        # Use a separate non-streaming call for summarization
        summary = client.chat_sync(prompt, max_tokens=500)
        return summary.strip()
    except Exception as e:
        logger.warning("Summarization failed: %s", e)
        return ""
