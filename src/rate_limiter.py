"""Rate limiting for tool calls.

Provides a sliding-window rate limiter that tracks tool call frequency
across different categories (read, write, exec, network) and returns
an error message when limits are exceeded.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from threading import Lock
from typing import Tuple

logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple sliding-window rate limiter for tool calls.

    Tracks the number of tool calls within a configurable time window
    and returns an error if the limit is exceeded.

    Supports different limits for different categories of tools
    (read, write, exec, network).

    Usage::

        limiter = RateLimiter()
        error = limiter.check_limit("bash", category="exec")
        if error:
            return error
    """

    DEFAULT_LIMITS: dict[str, Tuple[int, float]] = {
        "read":    (60,  60.0),    # 60 read calls per minute
        "write":   (20,  60.0),    # 20 write calls per minute
        "exec":    (30,  60.0),    # 30 subprocess calls per minute
        "network": (15,  60.0),    # 15 network calls per minute
        "default": (50,  60.0),    # 50 calls per minute (fallback)
    }

    def __init__(self, limits: dict[str, Tuple[int, float]] | None = None) -> None:
        self._limits = {**self.DEFAULT_LIMITS, **(limits or {})}
        self._history: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def check_limit(self, tool_name: str, category: str = "default") -> str | None:
        """Check if the tool is within its rate limit.

        Args:
            tool_name: Name of the tool (for logging).
            category: Category of the tool (read, write, exec, network, default).

        Returns:
            ``None`` if within limit, or an error message if rate limited.
        """
        if category not in self._limits:
            category = "default"

        max_calls, window_seconds = self._limits[category]
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            history = self._history[category]
            while history and history[0] < cutoff:
                history.pop(0)

            if len(history) >= max_calls:
                oldest = history[0] if history else now
                retry_after = max(0, window_seconds - (now - oldest))
                logger.warning(
                    "Rate limit exceeded for '%s' (tool: %s): "
                    "%d calls in %ds window. Retry after %.1fs.",
                    category, tool_name, len(history), window_seconds, retry_after,
                )
                return (
                    f"Error: Rate limit exceeded for {category} operations "
                    f"(tool: {tool_name}). Maximum {max_calls} calls per "
                    f"{window_seconds:.0f}s. Please wait {retry_after:.1f}s "
                    f"before retrying."
                )

            history.append(now)

        return None

    def get_remaining(self, category: str = "default") -> int:
        """Get the number of remaining calls allowed in the current window."""
        if category not in self._limits:
            category = "default"
        max_calls, window_seconds = self._limits[category]
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            history = self._history[category]
            while history and history[0] < cutoff:
                history.pop(0)
            return max(0, max_calls - len(history))

    def reset(self, category: str | None = None) -> None:
        """Reset rate limit counters for a category (or all if ``None``)."""
        with self._lock:
            if category:
                self._history[category].clear()
            else:
                self._history.clear()
