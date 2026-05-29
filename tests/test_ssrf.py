"""Tests for SSRF protection — DNS rebinding detection and private IP blocking."""

from __future__ import annotations

import socket
from src.utils import validate_url_target


class TestSSRFProtection:
    """Verify SSRF protection blocks private/internal IPs."""

    def test_block_loopback_ipv4(self) -> None:
        """127.0.0.1 should be blocked."""
        result = validate_url_target("http://127.0.0.1:8000/admin")
        assert result is not None
        assert "private" in result.lower() or "blocked" in result.lower()

    def test_block_private_10_dot(self) -> None:
        """10.x.x.x should be blocked."""
        result = validate_url_target("http://10.0.0.1/secret")
        assert result is not None

    def test_block_private_172_16(self) -> None:
        """172.16.x.x should be blocked."""
        result = validate_url_target("http://172.16.0.1/admin")
        assert result is not None

    def test_block_private_192_168(self) -> None:
        """192.168.x.x should be blocked."""
        result = validate_url_target("http://192.168.1.1/router")
        assert result is not None

    def test_allow_public_ip(self) -> None:
        """Public IPs should be allowed."""
        result = validate_url_target("http://93.184.216.34")
        assert result is None

    def test_allow_public_hostname(self) -> None:
        """Public hostnames should be allowed."""
        result = validate_url_target("https://api.github.com")
        assert result is None

    def test_block_ipv6_loopback(self) -> None:
        """IPv6 loopback ::1 should be blocked."""
        result = validate_url_target("http://[::1]:8080/")
        assert result is not None

    def test_block_ipv6_unique_local(self) -> None:
        """IPv6 unique local fc00:: should be blocked."""
        result = validate_url_target("http://[fc00::1]/")
        assert result is not None

    def test_block_ipv4_mapped_ipv6(self) -> None:
        """IPv4-mapped IPv6 ::ffff:10.0.0.1 should be blocked."""
        result = validate_url_target("http://[::ffff:10.0.0.1]:8000/")
        assert result is not None

    def test_block_ipv4_mapped_127(self) -> None:
        """IPv4-mapped IPv6 ::ffff:127.0.0.1 should be blocked."""
        result = validate_url_target("http://[::ffff:127.0.0.1]:8000/")
        assert result is not None

    def test_unsupported_scheme(self) -> None:
        """Non-http/https schemes should be rejected."""
        result = validate_url_target("file:///etc/passwd")
        assert result is not None
        assert "scheme" in result.lower()

    def test_no_scheme(self) -> None:
        """URLs without a scheme should be rejected."""
        result = validate_url_target("localhost:8000")
        assert result is not None

    def test_link_local_169_254(self) -> None:
        """169.254.x.x (link-local) should be blocked."""
        result = validate_url_target("http://169.254.169.254/latest/meta-data/")
        assert result is not None

    def test_block_0_0_0_0(self) -> None:
        """0.0.0.0 should be blocked."""
        result = validate_url_target("http://0.0.0.0:8080/")
        assert result is not None


class TestDnsRebindingDetection:
    """Verify DNS rebinding protection via double-resolution."""

    def test_dns_rebinding_private_second(self) -> None:
        """Simulate DNS rebinding: first public, second private."""
        call_count: list[int] = [0]

        def _rebinding_resolver(hostname: str) -> list[str]:
            call_count[0] += 1
            if call_count[0] == 1:
                return ["93.184.216.34"]  # First: public IP
            return ["10.0.0.1"]  # Second: private IP

        result = validate_url_target(
            "http://rebind.example.com",
            _resolver=_rebinding_resolver,
        )
        assert result is not None
        assert "rebinding" in result.lower()
        assert call_count[0] == 2

    def test_dns_rebinding_private_first(self) -> None:
        """If first resolution is private, it's blocked immediately (not rebinding)."""
        call_count: list[int] = [0]

        def _rebinding_resolver(hostname: str) -> list[str]:
            call_count[0] += 1
            if call_count[0] == 1:
                return ["10.0.0.1"]  # First: private IP
            return ["93.184.216.34"]  # Second: public IP

        result = validate_url_target(
            "http://rebind2.example.com",
            _resolver=_rebinding_resolver,
        )
        assert result is not None
        # Should be blocked as private, not specifically as rebinding
        assert "private" in result.lower()

    def test_consistent_dns_allowed(self) -> None:
        """Consistent DNS resolution should be allowed."""
        def _consistent_resolver(hostname: str) -> list[str]:
            return ["93.184.216.34"]

        result = validate_url_target(
            "http://example.com",
            _resolver=_consistent_resolver,
        )
        assert result is None

    def test_round_robin_dns_allowed(self) -> None:
        """Round-robin DNS (different public IPs) should be allowed."""
        call_count: list[int] = [0]

        def _round_robin_resolver(hostname: str) -> list[str]:
            call_count[0] += 1
            if call_count[0] == 1:
                return ["93.184.216.34"]
            return ["93.184.216.35"]  # Different, but still public

        result = validate_url_target(
            "http://roundrobin.example.com",
            _resolver=_round_robin_resolver,
        )
        assert result is None  # Round-robin should not be blocked

    def test_empty_resolution_allowed(self) -> None:
        """Unresolvable hostnames should be allowed (let connection fail naturally)."""
        def _empty_resolver(hostname: str) -> list[str]:
            raise socket.gaierror("Name or service not known")

        result = validate_url_target(
            "http://nonexistent-host-xyz.example.com",
            _resolver=_empty_resolver,
        )
        assert result is None  # Can't resolve — allow to let it fail naturally

    def test_first_resolution_private_blocked(self) -> None:
        """If first resolution is private, it should be blocked immediately."""
        def _private_resolver(hostname: str) -> list[str]:
            return ["192.168.1.1"]

        result = validate_url_target(
            "http://internal.example.com",
            _resolver=_private_resolver,
        )
        assert result is not None
        assert "private" in result.lower()
