"""Sensitive data redaction — single source of truth for all redaction patterns.

This module is the canonical location for ALL sensitive data redaction patterns
used across the codebase. It eliminates the duplication that previously existed
across ``security.py``, ``session.py``, and ``logging_config.py``.

Usage::

    from src.redaction import redact_text, redact_messages, SENSITIVE_REDACT_PATTERNS

    # Redact a single string
    safe = redact_text("my sk-xxx-api-key")

    # Redact message content (for session save)
    safe_msgs = redact_messages(messages)
"""

from __future__ import annotations

import re as _re

# ── Canonical redaction patterns ──────────────────────────────────────────────
# Each tuple is (regex_pattern, replacement_text).
# Applied case-insensitively to all text to redact.
# This is the SINGLE source of truth. Do NOT duplicate these patterns elsewhere.

SENSITIVE_REDACT_PATTERNS: list[tuple[str, str]] = [
    # Anthropic / OpenAI / generic API keys (sk-... with alphanumeric and dashes)
    (r"(sk-[a-zA-Z0-9\-]{20,})", "sk-***REDACTED***"),
    # API key env var assignments (e.g. ANTHROPIC_API_KEY=sk-...)
    (r'(ANTHROPIC_API_KEY[^a-zA-Z0-9]\s*["\x27]?)[a-zA-Z0-9_\-]+', r"\1***REDACTED***"),
    (r'(OPENAI_API_KEY[^a-zA-Z0-9]\s*["\x27]?)[a-zA-Z0-9_\-]+', r"\1***REDACTED***"),
    # AWS access keys
    (r"(AKIA[0-9A-Z]{16})", "AKIA***REDACTED***"),
    # GitHub tokens
    (r"(ghp_[a-zA-Z0-9]{36})", "ghp_***REDACTED***"),
    (r"(github_pat_[a-zA-Z0-9_]{80,})", "github_pat_***REDACTED***"),
    # Password/secret assignments
    (r'(password\s*[:=]\s*["\x27]?)[^"\x27,;\s}]+', r"\1***REDACTED***"),
    (r'(passwd\s*[:=]\s*["\x27]?)[^"\x27,;\s}]+', r"\1***REDACTED***"),
    (r'(secret\s*[:=]\s*["\x27]?)[^"\x27,;\s}]+', r"\1***REDACTED***"),
    # Database connection strings with credentials
    (r"((?:mongodb(?:\+srv)?|postgres(?:ql)?|mysql|redis)://)[^@\s]+@", r"\1***USER***@"),
    # JWT tokens
    (r"(eyJ[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,})", "eyJ***REDACTED***"),
    # Private key headers
    (r"-----BEGIN\s+(RSA|DSA|EC|OPENSSH|PGP)\s+PRIVATE\s+KEY-----", "-----BEGIN REDACTED PRIVATE KEY-----"),
    # Bearer tokens in headers
    (r"(Authorization:\s*Bearer\s+)[a-zA-Z0-9._\x2d]+", r"\1***REDACTED***"),
]

# Patterns used for LLM summarization (subset of full patterns).
# These focus on secrets that should not be transmitted to the LLM provider.
SUMMARIZATION_REDACT_PATTERNS: list[tuple[str, str]] = [
    # Anthropic / OpenAI / generic API keys
    (r"(sk-[a-zA-Z0-9\-]{20,})", "sk-***REDACTED***"),
    # AWS access keys
    (r"(AKIA[0-9A-Z]{16})", "AKIA***REDACTED***"),
    # GitHub tokens
    (r"(ghp_[a-zA-Z0-9]{36})", "ghp_***REDACTED***"),
    (r"(github_pat_[a-zA-Z0-9_]{80,})", "github_pat_***REDACTED***"),
    # Password/secret assignments
    (r'(password\s*[:=]\s*["\x27]?)[^"\x27,;\s}]+', r"\1***REDACTED***"),
    (r'(passwd\s*[:=]\s*["\x27]?)[^"\x27,;\s}]+', r"\1***REDACTED***"),
    (r'(secret\s*[:=]\s*["\x27]?)[^"\x27,;\s}]+', r"\1***REDACTED***"),
    # Database connection strings with credentials
    (r"((?:mongodb(?:\+srv)?|postgres(?:ql)?|mysql|redis)://)[^@\s]+@", r"\1***USER***@"),
    # JWT tokens
    (r"(eyJ[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,})", "eyJ***REDACTED***"),
    # Private key headers
    (r"-----BEGIN\s+(RSA|DSA|EC|OPENSSH|PGP)\s+PRIVATE\s+KEY-----", "-----BEGIN REDACTED PRIVATE KEY-----"),
    # Bearer tokens in headers
    (r"(Authorization:\s*Bearer\s+)[a-zA-Z0-9._\x2d]+", r"\1***REDACTED***"),
]


# ── Helper functions ──────────────────────────────────────────────────────────


def redact_text(text: str, patterns: list[tuple[str, str]] | None = None) -> str:
    """Redact known sensitive patterns from a text string.

    Args:
        text: The text to redact.
        patterns: The patterns to use (defaults to ``SENSITIVE_REDACT_PATTERNS``).

    Returns:
        Redacted text with sensitive values replaced.
    """
    if not text:
        return text
    patterns = patterns or SENSITIVE_REDACT_PATTERNS
    result = text
    for pattern, replacement in patterns:
        result = _re.sub(pattern, replacement, result, flags=_re.IGNORECASE)
    return result


def redact_messages(
    messages: list[dict[str, object]],
    patterns: list[tuple[str, str]] | None = None,
) -> list[dict[str, object]]:
    """Return a deep copy of messages with sensitive content redacted.

    The original messages list is not modified. This is used before saving
    session data to disk.

    Args:
        messages: The list of message dicts to redact.
        patterns: The patterns to use (defaults to ``SENSITIVE_REDACT_PATTERNS``).

    Returns:
        A new list of message dicts with sensitive values replaced.
    """
    patterns = patterns or SENSITIVE_REDACT_PATTERNS
    redacted: list[dict[str, object]] = []
    for msg in messages:
        msg_copy = dict(msg)
        content = msg_copy.get("content")
        if isinstance(content, str):
            msg_copy["content"] = redact_text(content, patterns)
        elif isinstance(content, list):
            redacted_blocks: list[dict[str, object]] = []
            for block in content:
                if isinstance(block, dict):
                    block_copy = dict(block)
                    for key in ("text", "content", "input"):
                        val = block_copy.get(key)
                        if isinstance(val, str):
                            block_copy[key] = redact_text(val, patterns)
                    redacted_blocks.append(block_copy)
                else:
                    redacted_blocks.append(block)  # type: ignore[typeddict-item]
            msg_copy["content"] = redacted_blocks  # type: ignore[assignment]
        redacted.append(msg_copy)
    return redacted


# ── Backward-compatible aliases ───────────────────────────────────────────────

#: Used by ``src.security`` and ``src.utils`` for LLM summarization redaction.
redact_sensitive_content = redact_text
"""Alias for :func:`redact_text` for backward compatibility.

This was previously defined in ``src.security`` and re-exported by ``src.utils``.
New code should use :func:`redact_text` directly.
"""
