"""Logging configuration for the Coding Agent.

Uses Python's built-in logging module with AEST timezone (UTC+10:00) timestamps.
Logs are written to ``logs/agent.log`` with rotation, and optionally to the console.

Security: A ``SensitiveDataFilter`` is automatically applied to all log output
to redact API keys, passwords, secrets, and other sensitive patterns before
they are written to disk.
"""

from __future__ import annotations

import datetime
import logging
import re as _re
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .redaction import SENSITIVE_REDACT_PATTERNS

LOG_FORMAT = "%(asctime)s AEST | %(levelname)-5s | %(name)-15s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
MAX_LOG_BYTES = 5 * 1024 * 1024  # 5 MB per log file
BACKUP_COUNT = 3  # keep 3 rotated log files

_AEST_TZ = datetime.timezone(datetime.timedelta(hours=10))

# NOTE: The canonical redaction patterns have been moved to ``src/redaction.py``
# to eliminate duplication. They are imported at the top of this module.


class SensitiveDataFilter(logging.Filter):
    """Filter that redacts sensitive data from log records before they are written.

    Applied automatically by ``setup_logging()``. Scans ``record.msg`` and
    ``record.args`` for known sensitive patterns and replaces them with
    redacted markers.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact sensitive patterns in the log record. Always returns True."""
        patterns = SENSITIVE_REDACT_PATTERNS
        if isinstance(record.msg, str):
            for pattern, replacement in patterns:
                record.msg = _re.sub(pattern, replacement, record.msg, flags=_re.IGNORECASE)

        if record.args:
            sanitized_args: list[object] = []
            for arg in record.args:
                if isinstance(arg, str):
                    for pattern, replacement in patterns:
                        arg = _re.sub(pattern, replacement, arg, flags=_re.IGNORECASE)
                sanitized_args.append(arg)
            record.args = tuple(sanitized_args)

        return True


class AestFormatter(logging.Formatter):
    """Custom formatter that converts UTC timestamps to AEST (UTC+10)."""

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        """Format the record's timestamp in AEST."""
        created_utc = datetime.datetime.fromtimestamp(record.created, tz=datetime.UTC)
        aest_time = created_utc.astimezone(_AEST_TZ)
        if datefmt:
            return aest_time.strftime(datefmt)
        return aest_time.strftime(DATE_FORMAT)


def setup_logging(
    level: int | str = logging.INFO,
    log_dir: str = "logs",
) -> None:
    """Configure the root logger with a rotating file handler and AEST timestamps.

    Args:
        level: Logging level (e.g. ``logging.INFO``, ``logging.DEBUG``, or ``"DEBUG"``).
        log_dir: Directory to store log files in.
    """
    # Resolve level from string if needed
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    # Ensure the log directory exists
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    log_file = log_path / "agent.log"

    # Create formatter
    formatter = AestFormatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # File handler with rotation
    file_handler = RotatingFileHandler(
        str(log_file),
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    # Add sensitive data redaction filter
    file_handler.addFilter(SensitiveDataFilter())

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove any existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """Get a logger for the given module name.

    Args:
        name: Usually ``__name__`` from the calling module.

    Returns:
        A :class:`logging.Logger` instance.
    """
    return logging.getLogger(name)
