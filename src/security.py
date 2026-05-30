"""SSRF (Server-Side Request Forgery) protection for the Coding Agent.

Provides URL target validation to block requests to private/internal IP
addresses and detect DNS rebinding attacks.

NOTE: Earlier versions of this module also contained ANSI sanitization,
data exfiltration detection, and sensitive data redaction. Those have been
split into their own modules (``ansi_sanitizer.py``, ``exfiltration_detection.py``,
``redaction.py``) to follow the Single Responsibility Principle.
They are re-exported here for backward compatibility.
"""

from __future__ import annotations

import ipaddress
import logging
import socket as _socket
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse as _urlparse

# Backward-compatibility re-exports
from src.ansi_sanitizer import strip_dangerous_ansi  # noqa: F401
from src.exfiltration_detection import (  # noqa: F401
    _EXFIL_NETWORK_COMMANDS,
    _EXFIL_SENSITIVE_FILES,
    _SCRIPT_FILE_READ_INDICATORS,
    _SCRIPT_INTERPRETERS,
    _SCRIPT_NETWORK_INDICATORS,
)
from src.redaction import redact_sensitive_content  # noqa: F401

logger = logging.getLogger(__name__)


# Private/reserved IP ranges that should be blocked for SSRF prevention
_PRIVATE_NETWORKS: list[Any] = [
    # IPv4 private/reserved
    ipaddress.ip_network("0.0.0.0/8"),  # Current network (RFC 1122)
    ipaddress.ip_network("10.0.0.0/8"),  # Private (RFC 1918)
    ipaddress.ip_network("100.64.0.0/10"),  # Carrier-grade NAT (RFC 6598)
    ipaddress.ip_network("127.0.0.0/8"),  # Loopback (RFC 1122)
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local (RFC 3927)
    ipaddress.ip_network("172.16.0.0/12"),  # Private (RFC 1918)
    ipaddress.ip_network("192.0.0.0/24"),  # IETF Protocol Assignments (RFC 6890)
    ipaddress.ip_network("192.0.2.0/24"),  # TEST-NET-1 (RFC 5737)
    ipaddress.ip_network("192.88.99.0/24"),  # 6to4 Relay Anycast (RFC 7526)
    ipaddress.ip_network("192.168.0.0/16"),  # Private (RFC 1918)
    ipaddress.ip_network("198.18.0.0/15"),  # Benchmarking (RFC 2544)
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2 (RFC 5737)
    ipaddress.ip_network("203.0.113.0/24"),  # TEST-NET-3 (RFC 5737)
    ipaddress.ip_network("224.0.0.0/4"),  # Multicast (RFC 5771)
    ipaddress.ip_network("240.0.0.0/4"),  # Reserved (RFC 1112)
    ipaddress.ip_network("255.255.255.255/32"),  # Limited Broadcast
    # IPv6 private/reserved
    ipaddress.ip_network("::1/128"),  # Loopback
    ipaddress.ip_network("::/96"),  # IPv4-compatible (deprecated)
    ipaddress.ip_network("::ffff:0:0/96"),  # IPv4-mapped addresses
    ipaddress.ip_network("64:ff9b::/96"),  # IPv4/IPv6 translation (RFC 6052)
    ipaddress.ip_network("100::/64"),  # Discard-only (RFC 6666)
    ipaddress.ip_network("2001:db8::/32"),  # Documentation (RFC 3849)
    ipaddress.ip_network("2002::/16"),  # 6to4 (RFC 3056)
    ipaddress.ip_network("fc00::/7"),  # Unique local (RFC 4193)
    ipaddress.ip_network("fe80::/10"),  # Link-local (RFC 4291)
    ipaddress.ip_network("ff00::/8"),  # Multicast (RFC 4291)
]


def _default_resolver(hostname: str) -> list[str]:
    """Default DNS resolver: get all IP addresses for a hostname."""
    result: list[str] = []
    addrinfo = _socket.getaddrinfo(hostname, None)
    for family, _, _, _, sockaddr in addrinfo:
        ip = sockaddr[0]
        if isinstance(ip, str) and ip not in result:
            result.append(ip)
    return result


def _is_private_ip(ip_str: str) -> bool:
    """Check if an IP string is in any private/reserved network."""
    try:
        ip = ipaddress.ip_address(ip_str)
        for net in _PRIVATE_NETWORKS:
            if ip in net:
                return True
    except ValueError:
        pass
    return False


def _check_ips_against_blocklist(hostname: str, url: str, ips: list[str]) -> str | None:
    """Check a list of IPs against the private network blocklist.

    Returns an error message if any IP is blocked, None otherwise.
    """
    for ip_str in ips:
        try:
            ip = ipaddress.ip_address(ip_str)
            for private_net in _PRIVATE_NETWORKS:
                if ip in private_net:
                    return (
                        f"Error: URL '{url}' resolves to private IP {ip}. "
                        f"Requests to private/internal networks are blocked "
                        f"for security (SSRF protection)."
                    )
        except ValueError:
            continue
    return None


def _detect_dns_rebinding(
    hostname: str,
    first_ips: list[str],
    resolver: Callable[[str], list[str]],
) -> tuple[list[str], str | None]:
    """Detect DNS rebinding by double-resolving the hostname.

    Only flags as rebinding if one resolution set contains a private IP
    and the other contains a public IP. Round-robin DNS (all public IPs
    that differ between resolutions) is allowed.

    Returns (second_ips, error_message_or_None).
    """
    try:
        second_ips = resolver(hostname)
    except _socket.gaierror, OSError:
        return first_ips, None

    if not second_ips:
        return first_ips, None

    if second_ips == first_ips:
        return second_ips, None

    # IPs differ — check if either set contains a private IP
    first_has_private = any(_is_private_ip(ip) for ip in first_ips)
    second_has_private = any(_is_private_ip(ip) for ip in second_ips)

    if first_has_private != second_has_private:
        # One resolution had a private IP, the other didn't — possible rebinding
        return second_ips, (
            f"Error: URL '{hostname}' resolved to different IPs on consecutive "
            f"lookups, and one set included a private/internal IP "
            f"(possible DNS rebinding attack). Blocking for safety."
        )

    # Both are public or both are private — allow (round-robin or consistent)
    return second_ips, None


def validate_url_target(
    url: str,
    *,
    _resolver: Callable[[str], list[str]] | None = None,
) -> str | None:
    """Validate that a URL target does not point to a private/internal IP.

    Protects against:
    - Direct requests to private/internal IPs
    - DNS rebinding attacks (by double-resolving the hostname)
    - IPv4-mapped IPv6 address bypasses

    Args:
        url: The URL to validate.
        _resolver: Optional custom resolver for testing (default: socket.getaddrinfo).

    Returns ``None`` if the URL is safe, or an error message string if blocked.
    """
    parsed = _urlparse(url)
    if not parsed.scheme:
        return "Error: URL must have a scheme (http:// or https://)"
    if parsed.scheme not in ("http", "https"):
        return f"Error: Unsupported URL scheme '{parsed.scheme}'. Only http/https allowed."

    hostname = parsed.hostname
    if not hostname:
        return "Error: URL has no valid hostname"

    resolver = _resolver or _default_resolver

    # ── First resolution ────────────────────────────────────────────────
    try:
        first_ips = resolver(hostname)
    except _socket.gaierror, OSError:
        return None  # Can't resolve — let the request proceed

    if not first_ips:
        return None

    # Check first resolution against private ranges
    first_blocked = _check_ips_against_blocklist(hostname, url, first_ips)
    if first_blocked:
        return first_blocked

    # ── Second resolution (DNS rebinding detection) ──────────────────────
    second_ips, rebind_error = _detect_dns_rebinding(hostname, first_ips, resolver)
    if rebind_error:
        logger.warning(
            "DNS rebinding detected for '%s': first=%s, second=%s",
            hostname,
            first_ips,
            second_ips,
        )
        return rebind_error

    # Check second resolution against private ranges (redundant but safe)
    if second_ips:
        second_blocked = _check_ips_against_blocklist(hostname, url, second_ips)
        if second_blocked:
            return second_blocked

    return None
