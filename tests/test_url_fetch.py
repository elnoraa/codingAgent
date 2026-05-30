"""Tests for the URL fetch tool.

Uses mocked urllib requests to test without network access (DIP compliance).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.tools import ToolContext
from src.tools.url_fetch import execute, url_fetch_tool


def test_tool_definition() -> None:
    assert url_fetch_tool.name == "url_fetch"
    assert url_fetch_tool.read_only is True


def test_execute_missing_url() -> None:
    ctx = ToolContext(working_directory="/tmp")  # noqa: S108
    result = execute({}, ctx)
    assert "Error" in result
    assert "url" in result.lower()


def test_execute_url_too_long() -> None:
    ctx = ToolContext(working_directory="/tmp")  # noqa: S108
    long_url = "https://example.com/" + "x" * 9000  # exceeds MAX_URL_LENGTH (8192)
    result = execute({"url": long_url}, ctx)
    assert "Error" in result
    assert "too long" in result.lower()


def test_execute_ssrf_blocked_localhost() -> None:
    ctx = ToolContext(working_directory="/tmp")  # noqa: S108
    result = execute({"url": "http://127.0.0.1:8080/secret"}, ctx)
    assert "Error" in result
    assert "blocked" in result.lower() or "private" in result.lower()


def test_execute_ssrf_blocked_zero_ip() -> None:
    ctx = ToolContext(working_directory="/tmp")  # noqa: S108
    result = execute({"url": "http://0.0.0.0:8000/admin"}, ctx)
    assert "Error" in result
    assert "blocked" in result.lower() or "private" in result.lower()


def test_execute_content_truncation() -> None:
    """When content exceeds maxLength, it should be truncated."""
    ctx = ToolContext(working_directory="/tmp")  # noqa: S108
    long_content = "hello world " * 1000  # ~12KB

    # Mock urllib.request.urlopen context manager
    mock_response = MagicMock()
    mock_response.read.return_value = long_content.encode("utf-8")
    mock_response.headers = {"Content-Type": "text/plain"}
    # urlopen returns a context manager where __enter__ returns the response
    mock_context = MagicMock()
    mock_context.__enter__.return_value = mock_response

    with patch("urllib.request.urlopen", return_value=mock_context) as mock_urlopen:
        result = execute({"url": "https://example.com", "maxLength": 100}, ctx)
        assert "truncated" in result.lower() or "showing" in result.lower()
        assert "hello world" in result
        mock_urlopen.assert_called_once()


def test_execute_http_error() -> None:
    """HTTP errors should be caught and reported cleanly."""
    import urllib.error

    ctx = ToolContext(working_directory="/tmp")  # noqa: S108

    from http.client import HTTPMessage

    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.HTTPError(
            url="https://example.com",
            code=404,
            msg="Not Found",
            hdrs=HTTPMessage(),
            fp=None,
        ),
    ):
        result = execute({"url": "https://example.com"}, ctx)
        assert "Error" in result
        assert "404" in result or "Not Found" in result


def test_execute_connection_error() -> None:
    """Connection errors should be caught and reported cleanly."""
    import urllib.error

    ctx = ToolContext(working_directory="/tmp")  # noqa: S108

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError(reason="getaddrinfo failed")):
        result = execute({"url": "https://example.com"}, ctx)
        assert "Error" in result
        assert "getaddrinfo" in result or "Failed" in result
