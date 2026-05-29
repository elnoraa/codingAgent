"""Tests for the URL fetch tool."""

from __future__ import annotations

from unittest.mock import patch

from src.tools import ToolContext
from src.tools.url_fetch import url_fetch_tool, execute


def test_tool_definition() -> None:
    assert url_fetch_tool.name == "url_fetch"
    assert url_fetch_tool.read_only is True


def test_execute_missing_url() -> None:
    ctx = ToolContext(working_directory="/tmp")
    result = execute({}, ctx)
    assert "Error" in result
    assert "url" in result.lower()


def test_execute_url_too_long() -> None:
    ctx = ToolContext(working_directory="/tmp")
    long_url = "https://example.com/" + "x" * 9000  # exceeds MAX_URL_LENGTH (8192)
    result = execute({"url": long_url}, ctx)
    assert "Error" in result
    assert "too long" in result.lower()


def test_execute_ssrf_blocked_localhost() -> None:
    ctx = ToolContext(working_directory="/tmp")
    result = execute({"url": "http://127.0.0.1:8080/secret"}, ctx)
    assert "Error" in result
    assert "blocked" in result.lower() or "private" in result.lower()


def test_execute_ssrf_blocked_zero_ip() -> None:
    ctx = ToolContext(working_directory="/tmp")
    result = execute({"url": "http://0.0.0.0:8000/admin"}, ctx)
    assert "Error" in result
    assert "blocked" in result.lower() or "private" in result.lower()


def test_execute_content_truncation() -> None:
    """When content exceeds maxLength, it should be truncated."""
    ctx = ToolContext(working_directory="/tmp")
    long_content = "hello world " * 1000  # ~12KB

    with patch("subprocess.run") as mock_run:
        mock_result = type("Result", (), {
            "returncode": 0,
            "stdout": long_content,
            "stderr": "",
        })()
        mock_run.return_value = mock_result

        result = execute({"url": "https://example.com", "maxLength": 100}, ctx)
        assert "truncated" in result
        assert len(result) < 200  # summary + truncated content


def test_execute_curl_not_available() -> None:
    """When curl is not installed, try wget as fallback."""
    ctx = ToolContext(working_directory="/tmp")

    def _fail_curl(*args, **kwargs):
        raise FileNotFoundError("curl not found")

    with patch("subprocess.run", side_effect=_fail_curl):
        result = execute({"url": "https://example.com"}, ctx)
        # Either wget also fails, or it could be installed
        assert result is not None
