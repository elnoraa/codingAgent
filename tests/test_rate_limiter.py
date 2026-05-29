"""Tests for rate limiter."""

from __future__ import annotations

import time

from src.utils import RateLimiter


class TestRateLimiter:
    """Verify rate limiter behavior."""

    def test_initial_state_allows_calls(self) -> None:
        """Initial state should allow calls up to the limit."""
        limiter = RateLimiter(limits={"test": (5, 60.0)})
        for _ in range(5):
            assert limiter.check_limit("test_tool", "test") is None

    def test_exceeding_limit_blocks(self) -> None:
        """Exceeding the limit should return an error."""
        limiter = RateLimiter(limits={"test": (3, 60.0)})
        for _ in range(3):
            assert limiter.check_limit("test_tool", "test") is None
        assert limiter.check_limit("test_tool", "test") is not None

    def test_unknown_category_falls_back_to_default(self) -> None:
        """Unknown categories should use default limits."""
        limiter = RateLimiter(limits={"default": (2, 60.0)})
        assert limiter.check_limit("weird_tool", "nonexistent") is None
        assert limiter.check_limit("weird_tool", "nonexistent") is None
        assert limiter.check_limit("weird_tool", "nonexistent") is not None

    def test_window_expires(self) -> None:
        """After the window expires, calls should be allowed again."""
        limiter = RateLimiter(limits={"quick": (1, 0.1)})
        assert limiter.check_limit("tool", "quick") is None
        assert limiter.check_limit("tool", "quick") is not None
        time.sleep(0.15)
        assert limiter.check_limit("tool", "quick") is None

    def test_get_remaining(self) -> None:
        """get_remaining should return the correct count."""
        limiter = RateLimiter(limits={"test": (5, 60.0)})
        assert limiter.get_remaining("test") == 5
        limiter.check_limit("tool", "test")
        assert limiter.get_remaining("test") == 4
        limiter.check_limit("tool", "test")
        assert limiter.get_remaining("test") == 3

    def test_reset_category(self) -> None:
        """Resetting a category should clear its history."""
        limiter = RateLimiter(limits={"test": (1, 60.0)})
        limiter.check_limit("tool", "test")
        assert limiter.get_remaining("test") == 0
        limiter.reset("test")
        assert limiter.get_remaining("test") == 1

    def test_reset_all(self) -> None:
        """Resetting all categories should clear all history."""
        limiter = RateLimiter(limits={"a": (1, 60.0), "b": (1, 60.0)})
        limiter.check_limit("tool1", "a")
        limiter.check_limit("tool2", "b")
        limiter.reset()
        assert limiter.get_remaining("a") == 1
        assert limiter.get_remaining("b") == 1

    def test_different_categories_independent(self) -> None:
        """Different categories should have independent rate limits."""
        limiter = RateLimiter(limits={"read": (2, 60.0), "write": (1, 60.0)})
        assert limiter.check_limit("write_file", "write") is None
        assert limiter.check_limit("write_file", "write") is not None
        assert limiter.check_limit("read_file", "read") is None
        assert limiter.check_limit("read_file", "read") is None
        assert limiter.check_limit("read_file", "read") is not None

    def test_custom_limits(self) -> None:
        """Custom limits should override defaults."""
        limiter = RateLimiter(limits={"custom": (10, 5.0)})
        for _ in range(10):
            assert limiter.check_limit("tool", "custom") is None
        assert limiter.check_limit("tool", "custom") is not None

    def test_concurrent_safety(self) -> None:
        """Rate limiter should handle concurrent access."""
        import threading

        limiter = RateLimiter(limits={"test": (50, 60.0)})
        errors: list[str] = []

        def worker() -> None:
            for _ in range(10):
                result = limiter.check_limit("test_tool", "test")
                if result:
                    errors.append(result)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
