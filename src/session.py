"""Session save/load functionality for the Coding Agent.

Sessions are stored as JSON files in the working_directory/sessions/ folder.
Each session captures: messages, mode, working_directory, model, timestamp.

If the ``CODING_AGENT_SESSION_KEY`` environment variable is set, session
files are encrypted with AES-GCM (via ``cryptography.fernet``) and stored
with a ``.encrypted`` extension instead of ``.json``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from .logging_config import get_logger

logger = get_logger(__name__)

SESSION_DIR = "sessions"

# Environment variable for optional session encryption
SESSION_KEY_ENV = "CODING_AGENT_SESSION_KEY"

# Patterns that may indicate sensitive content in messages
_SENSITIVE_PATTERNS: list[tuple[str, str]] = [
    (r'[\'"]?(?:sk-[a-zA-Z0-9]{20,})[\'"]?', "API key (e.g. sk-...)"),
    (r'(?:ANTHROPIC_API_KEY|OPENAI_API_KEY|API_KEY)', "API key environment variable"),
    (r'(?:password|passwd|secret)\s*[:=]\s*[\'"]?\S+', "potential password/secret"),
]

# Sensitive patterns to redact from session data before saving to disk
_SESSION_REDACT_PATTERNS: list[tuple[str, str]] = [
    # Anthropic / OpenAI / generic API keys
    (r'(sk-[a-zA-Z0-9\-]{20,})', 'sk-***REDACTED***'),
    # AWS access keys
    (r'(AKIA[0-9A-Z]{16})', 'AKIA***REDACTED***'),
    # GitHub tokens
    (r'(ghp_[a-zA-Z0-9]{36})', 'ghp_***REDACTED***'),
    (r'(github_pat_[a-zA-Z0-9_]{80,})', 'github_pat_***REDACTED***'),
    # Password/secret assignments
    (r'(password\s*[:=]\s*["\x27]?)[^"\x27,;\s}]+', r'\1***REDACTED***'),
    (r'(passwd\s*[:=]\s*["\x27]?)[^"\x27,;\s}]+', r'\1***REDACTED***'),
    (r'(secret\s*[:=]\s*["\x27]?)[^"\x27,;\s}]+', r'\1***REDACTED***'),
    # Database connection strings with credentials
    (r'((?:mongodb(?:\+srv)?|postgres(?:ql)?|mysql|redis)://)[^@\s]+@', r'\1***USER***@'),
    # JWT tokens
    (r'(eyJ[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,})', 'eyJ***REDACTED***'),
    # Private key headers
    (r'-----BEGIN\s+(RSA|DSA|EC|OPENSSH|PGP)\s+PRIVATE\s+KEY-----', '-----BEGIN REDACTED PRIVATE KEY-----'),
    # Bearer tokens in headers
    (r'(Authorization:\s*Bearer\s+)[a-zA-Z0-9._\x2d]+', r'\1***REDACTED***'),
]


def _redact_text(text: str) -> str:
    """Redact sensitive patterns from a text string.

    Used before saving session data to disk.
    """
    if not isinstance(text, str):
        return text
    result = text
    for pattern, replacement in _SESSION_REDACT_PATTERNS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def _redact_messages(messages: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return a deep copy of messages with sensitive content redacted.

    The original messages list is not modified.
    """
    redacted: list[dict[str, object]] = []
    for msg in messages:
        msg_copy = dict(msg)
        content = msg_copy.get("content")
        if isinstance(content, str):
            msg_copy["content"] = _redact_text(content)
        elif isinstance(content, list):
            redacted_blocks: list[dict[str, object]] = []
            for block in content:
                if isinstance(block, dict):
                    block_copy = dict(block)
                    for key in ("text", "content", "input"):
                        val = block_copy.get(key)
                        if isinstance(val, str):
                            block_copy[key] = _redact_text(val)
                    redacted_blocks.append(block_copy)
                else:
                    redacted_blocks.append(block)  # type: ignore[typeddict-item]
            msg_copy["content"] = redacted_blocks  # type: ignore[assignment]
        redacted.append(msg_copy)
    return redacted


def _sessions_dir(working_directory: str) -> str:
    return os.path.join(working_directory, SESSION_DIR)


def _get_cipher() -> Any | None:
    """Return a Fernet cipher if SESSION_KEY_ENV is set, else None."""
    key = os.environ.get(SESSION_KEY_ENV)
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
        # If key is not a raw 44-char Fernet key, derive one via SHA-256
        if len(key) != 44:
            import base64
            import hashlib
            derived = hashlib.sha256(key.encode()).digest()
            key = base64.urlsafe_b64encode(derived)
        return Fernet(key)
    except Exception as exc:
        logger.warning("Invalid %s, sessions will be unencrypted: %s", SESSION_KEY_ENV, exc)
        return None


def _check_sensitive_content(messages: list[dict[str, object]]) -> list[str]:
    """Scan messages for potentially sensitive content patterns.

    Returns a list of warning strings (empty if none found).
    This is a best-effort scan and may produce false positives/negatives.
    """
    warnings: list[str] = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            for pattern, desc in _SENSITIVE_PATTERNS:
                if re.search(pattern, content, re.IGNORECASE):
                    warnings.append(
                        f"Potential {desc} detected in message content. "
                        f"Set {SESSION_KEY_ENV} for encryption."
                    )
                    break  # One warning per message
        elif isinstance(content, list):
            # Check tool result content blocks
            for block in cast("list[dict[str, object]]", content):
                block_content = block.get("content") or block.get("text", "")
                if isinstance(block_content, str):
                    for pattern, desc in _SENSITIVE_PATTERNS:
                        if re.search(pattern, block_content, re.IGNORECASE):
                            warnings.append(
                                f"Potential {desc} detected in tool output. "
                                f"Set {SESSION_KEY_ENV} for encryption."
                            )
                            break
    return warnings


def save_session(
    name: str,
    messages: list[dict[str, object]],
    mode: str,
    working_directory: str,
    model: str,
    is_autosave: bool = False,
) -> str:
    """Save the current session to a JSON file. Returns the file path."""
    s_dir = _sessions_dir(working_directory)
    Path(s_dir).mkdir(parents=True, exist_ok=True)

    safe_name = name.strip().replace(" ", "-")
    safe_name = "".join(c for c in safe_name if c.isalnum() or c in "-_.")
    if not safe_name:
        return "Error: invalid session name. Use alphanumeric characters, dashes, or underscores."

    session_data = {
        "name": safe_name,
        "saved_at": datetime.now().isoformat(),
        "mode": mode,
        "working_directory": working_directory,
        "model": model,
        "messages": _redact_messages(messages),
        "is_autosave": is_autosave,
    }

    cipher = _get_cipher()
    if cipher:
        # Encrypted save
        filepath = os.path.join(s_dir, f"{safe_name}.encrypted")
        json_bytes = json.dumps(session_data, indent=2, ensure_ascii=False).encode("utf-8")
        encrypted = cipher.encrypt(json_bytes)
        with open(filepath, "wb") as f:
            f.write(encrypted)
        logger.info("Session saved (encrypted): name=%s, mode=%s, messages=%d, file=%s", safe_name, mode, len(messages), filepath)
    else:
        # Plain JSON save
        filepath = os.path.join(s_dir, f"{safe_name}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=2, ensure_ascii=False)
        logger.info("Session saved: name=%s, mode=%s, messages=%d, file=%s", safe_name, mode, len(messages), filepath)

    return filepath


def load_session(name: str, working_directory: str) -> dict[str, object] | None:
    """Load a session by name. Returns the session dict or None if not found."""
    s_dir = _sessions_dir(working_directory)
    safe_name = name.strip().replace(" ", "-")
    safe_name = "".join(c for c in safe_name if c.isalnum() or c in "-_.")
    if not safe_name:
        return None

    # Try plain JSON first
    filepath = os.path.join(s_dir, f"{safe_name}.json")
    if os.path.isfile(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data: dict[str, object] = json.load(f)
            msg_count = len(cast("list[object]", data.get("messages", [])))
            logger.info("Session loaded: name=%s, messages=%d, mode=%s", safe_name, msg_count, data.get("mode", "?"))
            return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load session %s: %s", safe_name, exc)
            return None

    # Try encrypted
    filepath_enc = os.path.join(s_dir, f"{safe_name}.encrypted")
    if os.path.isfile(filepath_enc):
        cipher = _get_cipher()
        if cipher is None:
            logger.warning("Cannot load encrypted session %s: %s not set", safe_name, SESSION_KEY_ENV)
            return None
        try:
            with open(filepath_enc, "rb") as f:
                decrypted = cipher.decrypt(f.read())
            data = json.loads(decrypted.decode("utf-8"))
            msg_count = len(cast("list[object]", data.get("messages", [])))
            logger.info("Session loaded (encrypted): name=%s, messages=%d, mode=%s", safe_name, msg_count, data.get("mode", "?"))
            return data
        except Exception as exc:
            logger.warning("Failed to load encrypted session %s: %s", safe_name, exc)
            return None

    return None


def list_sessions(working_directory: str) -> list[dict[str, object]]:
    """List all saved sessions with metadata. Returns list of dicts sorted by save time (newest first)."""
    s_dir = _sessions_dir(working_directory)
    if not os.path.isdir(s_dir):
        return []

    sessions: list[dict[str, object]] = []
    for fname in os.listdir(s_dir):
        if not (fname.endswith(".json") or fname.endswith(".encrypted")):
            continue
        filepath = os.path.join(s_dir, fname)
        try:
            if fname.endswith(".encrypted"):
                # For listing, try to load metadata (may fail without key)
                cipher = _get_cipher()
                if cipher:
                    with open(filepath, "rb") as f:
                        decrypted = cipher.decrypt(f.read())
                    data = json.loads(decrypted.decode("utf-8"))
                else:
                    # Can't read encrypted files without key, show basic info
                    sessions.append({
                        "name": fname[:-10],  # Remove .encrypted
                        "saved_at": "unknown (encrypted)",
                        "mode": "unknown",
                        "model": "unknown",
                        "message_count": 0,
                        "filepath": filepath,
                        "encrypted": True,
                    })
                    continue
            else:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)

            sessions.append({
                "name": data.get("name", fname[:-5] if fname.endswith(".json") else fname[:-10]),
                "saved_at": data.get("saved_at", "unknown"),
                "mode": data.get("mode", "unknown"),
                "model": data.get("model", "unknown"),
                "message_count": len(cast("list[object]", data.get("messages", []))),
                "filepath": filepath,
                "encrypted": fname.endswith(".encrypted"),
            })
        except (json.JSONDecodeError, OSError):
            continue

    # Sort newest first
    sessions.sort(key=lambda s: s.get("saved_at", ""), reverse=True)  # type: ignore[arg-type, return-value]
    logger.debug("Listed %d sessions from %s", len(sessions), s_dir)
    return sessions


def delete_session(name: str, working_directory: str) -> bool:
    """Delete a saved session by name. Returns True if successful."""
    s_dir = _sessions_dir(working_directory)
    safe_name = name.strip().replace(" ", "-")
    safe_name = "".join(c for c in safe_name if c.isalnum() or c in "-_.")
    # Try plain JSON
    filepath = os.path.join(s_dir, f"{safe_name}.json")
    if os.path.isfile(filepath):
        os.remove(filepath)
        logger.info("Session deleted: %s", safe_name)
        return True
    # Try encrypted
    filepath_enc = os.path.join(s_dir, f"{safe_name}.encrypted")
    if os.path.isfile(filepath_enc):
        os.remove(filepath_enc)
        logger.info("Session deleted (encrypted): %s", safe_name)
        return True
    logger.warning("Session not found for deletion: %s", safe_name)
    return False
