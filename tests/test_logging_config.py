"""Tests for logging configuration."""

from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Iterator

import pytest

from src.logging_config import setup_logging, get_logger, AestFormatter, LOG_FORMAT, DATE_FORMAT


def _cleanup_root_logger() -> None:
    """Remove and close all handlers on the root logger."""
    root = logging.getLogger()
    for handler in root.handlers[:]:
        try:
            handler.close()
        except Exception:
            pass
        root.removeHandler(handler)


@pytest.fixture
def tmp_log_dir() -> Iterator[str]:
    """Create a temp directory for log files."""
    _cleanup_root_logger()
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir
    _cleanup_root_logger()


def test_setup_logging_creates_directory(tmp_log_dir: str) -> None:
    """Log directory should be created if it doesn't exist."""
    log_dir = os.path.join(tmp_log_dir, "my-logs")
    assert not os.path.isdir(log_dir)
    setup_logging(level=logging.INFO, log_dir=log_dir)
    assert os.path.isdir(log_dir)
    _cleanup_root_logger()


def test_setup_logging_creates_file(tmp_log_dir: str) -> None:
    """Log file should exist after setup."""
    setup_logging(level=logging.INFO, log_dir=tmp_log_dir)
    log_file = os.path.join(tmp_log_dir, "agent.log")
    assert os.path.isfile(log_file)
    _cleanup_root_logger()


def test_setup_logging_accepts_string_level(tmp_log_dir: str) -> None:
    """String level like 'DEBUG' should work."""
    setup_logging(level="DEBUG", log_dir=tmp_log_dir)
    root_logger = logging.getLogger()
    assert root_logger.level == logging.DEBUG
    _cleanup_root_logger()


def test_setup_logging_accepts_int_level(tmp_log_dir: str) -> None:
    """Integer level like logging.WARNING should work."""
    setup_logging(level=logging.WARNING, log_dir=tmp_log_dir)
    root_logger = logging.getLogger()
    assert root_logger.level == logging.WARNING
    _cleanup_root_logger()


def test_get_logger_returns_logger() -> None:
    """get_logger should return a Logger instance."""
    logger = get_logger("test-module")
    assert isinstance(logger, logging.Logger)


def test_get_logger_name() -> None:
    """Logger name should match the argument."""
    logger = get_logger("my.custom.module")
    assert logger.name == "my.custom.module"


def test_aest_formatter_format_time() -> None:
    """AestFormatter should convert UTC to AEST (UTC+10)."""
    # Create a LogRecord with a known UTC timestamp
    # Unix timestamp 0 = 1970-01-01 00:00:00 UTC
    # In AEST (UTC+10) this should be 1970-01-01 10:00:00
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=42,
        msg="test message",
        args=(),
        exc_info=None,
    )
    # Set created to 0 (epoch)
    record.created = 0.0

    formatter = AestFormatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    formatted = formatter.formatTime(record, datefmt=DATE_FORMAT)

    # Should be 1970-01-01 10:00:00 (UTC+10 from epoch)
    assert formatted == "1970-01-01 10:00:00"


def test_aest_formatter_without_datefmt() -> None:
    """AestFormatter should work without a custom datefmt."""
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=42,
        msg="test",
        args=(),
        exc_info=None,
    )
    record.created = 3600.0  # 1970-01-01 01:00:00 UTC
    # In AEST: 1970-01-01 11:00:00

    formatter = AestFormatter(LOG_FORMAT)
    formatted = formatter.formatTime(record)

    # Should contain AEST time (11:00:00)
    assert "11:00:00" in formatted
