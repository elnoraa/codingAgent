"""Security utilities for the Coding Agent.

Provides protection against:
- SSRF (Server-Side Request Forgery) attacks
- Data exfiltration via bash commands
- Terminal ANSI escape code injection
- Sensitive data leakage (API keys, passwords) in LLM summarization
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re as _re_module
import socket as _socket
from typing import Any, Callable
from urllib.parse import urlparse as _urlparse

logger = logging.getLogger(__name__)


# ── ANSI Terminal Escape Sanitization ──────────────────────────────────────────


# Dangerous ANSI sequences that should be stripped from output before rendering.
# These can be used for terminal injection attacks (cursor positioning, screen
# clearing, title setting, keyboard remapping, etc.).
_DANGEROUS_ANSI_PATTERNS: list[Any] = [
    _re_module.compile(r'\x1b\[2J'),        # Clear entire screen
    _re_module.compile(r'\x1b\[3J'),        # Clear scrollback
    _re_module.compile(r'\x1b\[0J'),        # Clear from cursor to end of screen
    _re_module.compile(r'\x1b\[1J'),        # Clear from beginning to cursor
    _re_module.compile(r'\x1b\[\d*(?:;\d*)?[Hf]'),  # Cursor positioning
    _re_module.compile(r'\x1b\[\?25[lh]'),   # Hide/show cursor
    _re_module.compile(r'\x1b\]0;.+?\x07'),  # Set terminal title
    _re_module.compile(r'\x1b\]2;.+?\x07'),  # Set terminal title (alternative)
    _re_module.compile(r'\x1b\[\d*[n]'),    # Device status reports
    _re_module.compile(r'\x1b\[[0-9;]*[t]'),    # XTerm window ops
    _re_module.compile(r'\x1bc', _re_module.ASCII),      # RIS (Reset to Initial State)
    _re_module.compile(r'\x1b][\\_\[\]]'),  # String terminators
]


def strip_dangerous_ansi(text: str) -> str:
    """Strip dangerous ANSI escape sequences from text.

    Preserves common formatting sequences (colors, bold, dim) but removes
    sequences that could be used for terminal injection attacks.

    Args:
        text: The text to sanitize.

    Returns:
        Sanitized text with dangerous sequences removed.
    """
    if not text:
        return text
    result = text
    for pattern in _DANGEROUS_ANSI_PATTERNS:
        result = pattern.sub('', result)
    return result


# ── Sensitive data redaction ─────────────────────────────────────────────────


# Sensitive patterns to redact before sending message content to LLM
# for summarization. This prevents secrets from being transmitted to
# the LLM provider.
_SUMMARIZATION_REDACT_PATTERNS: list[tuple[str, str]] = [
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


def redact_sensitive_content(text: str) -> str:
    """Redact known sensitive patterns from text content.

    This is used before sending message content to the LLM for
    summarization to prevent secrets from being transmitted to
    the LLM provider.

    Args:
        text: The text to redact.

    Returns:
        Redacted text with sensitive values replaced.
    """
    if not text:
        return text

    result = text
    for pattern, replacement in _SUMMARIZATION_REDACT_PATTERNS:
        result = _re_module.sub(pattern, replacement, result, flags=_re_module.IGNORECASE)
    return result


# ── Data exfiltration detection constants ──────────────────────────────────────

# Files that should never be read and sent over the network
_EXFIL_SENSITIVE_FILES: frozenset = frozenset({
    ".env", ".env.example", ".env.local", ".env.production",
    "config.json",  # may contain credentials
    ".git-credentials", ".gitconfig",
    ".ssh/id_rsa", ".ssh/id_rsa.pub", ".ssh/id_ed25519", ".ssh/id_ed25519.pub",
    ".ssh/config", ".ssh/authorized_keys",
    "id_rsa", "id_ed25519",
    "credentials.json", "credentials.yml", "credentials.yaml",
    "service-account.json", "service-account-key.json",
    ".npmrc", ".netrc",
})

# Commands that can send data to remote servers (exfiltration vectors)
_EXFIL_NETWORK_COMMANDS: frozenset = frozenset({
    "curl", "wget", "nc", "ncat", "netcat", "socat",
    "ftp", "sftp", "scp", "rsync",
    "telnet",
})

# Script interpreters that can execute inline code and bypass the command scanner
# Format: (interpreter_binary, flag_that_takes_inline_code, description)
_SCRIPT_INTERPRETERS: list[tuple[str, str, str]] = [
    ("python", "-c", "Python inline code execution"),
    ("python3", "-c", "Python 3 inline code execution"),
    ("node", "-e", "Node.js inline code execution"),
    ("node", "-p", "Node.js inline print execution"),
    ("ruby", "-e", "Ruby inline code execution"),
    ("perl", "-e", "Perl inline code execution"),
    ("php", "-r", "PHP inline code execution"),
    ("php", "-R", "PHP inline code processing"),
]

# Dangerous function/module calls that indicate file operations in script code
_SCRIPT_FILE_READ_INDICATORS: frozenset = frozenset({
    "open(", ".read(", ".read_text(", ".read_bytes(",
    "readFile(", "readFileSync(", "readFileSync (",
    "createReadStream(", "createReadStream (",
    "File.read(", "File.open(",
    "fread(", "file_get_contents(",
})

# Dangerous function/module calls that indicate network operations in script code
_SCRIPT_NETWORK_INDICATORS: frozenset = frozenset({
    "urllib.request.urlopen(", "urllib.request.Request(",
    "requests.get(", "requests.post(", "requests.put(", "requests.delete(",
    "urlopen(", "urlretrieve(",
    "fetch(", "http.", "https.",
    "net/http", "net::HTTP",
    "curl ", "wget ",
})


# ── SSRF protection ─────────────────────────────────────────────────────────

# Private/reserved IP ranges that should be blocked for SSRF prevention
_PRIVATE_NETWORKS: list[Any] = [
    # IPv4 private/reserved
    ipaddress.ip_network("0.0.0.0/8"),          # Current network (RFC 1122)
    ipaddress.ip_network("10.0.0.0/8"),         # Private (RFC 1918)
    ipaddress.ip_network("100.64.0.0/10"),      # Carrier-grade NAT (RFC 6598)
    ipaddress.ip_network("127.0.0.0/8"),        # Loopback (RFC 1122)
    ipaddress.ip_network("169.254.0.0/16"),     # Link-local (RFC 3927)
    ipaddress.ip_network("172.16.0.0/12"),      # Private (RFC 1918)
    ipaddress.ip_network("192.0.0.0/24"),       # IETF Protocol Assignments (RFC 6890)
    ipaddress.ip_network("192.0.2.0/24"),       # TEST-NET-1 (RFC 5737)
    ipaddress.ip_network("192.88.99.0/24"),     # 6to4 Relay Anycast (RFC 7526)
    ipaddress.ip_network("192.168.0.0/16"),     # Private (RFC 1918)
    ipaddress.ip_network("198.18.0.0/15"),      # Benchmarking (RFC 2544)
    ipaddress.ip_network("198.51.100.0/24"),    # TEST-NET-2 (RFC 5737)
    ipaddress.ip_network("203.0.113.0/24"),     # TEST-NET-3 (RFC 5737)
    ipaddress.ip_network("224.0.0.0/4"),        # Multicast (RFC 5771)
    ipaddress.ip_network("240.0.0.0/4"),        # Reserved (RFC 1112)
    ipaddress.ip_network("255.255.255.255/32"), # Limited Broadcast

    # IPv6 private/reserved
    ipaddress.ip_network("::1/128"),            # Loopback
    ipaddress.ip_network("::/96"),              # IPv4-compatible (deprecated)
    ipaddress.ip_network("::ffff:0:0/96"),      # IPv4-mapped addresses
    ipaddress.ip_network("64:ff9b::/96"),       # IPv4/IPv6 translation (RFC 6052)
    ipaddress.ip_network("100::/64"),           # Discard-only (RFC 6666)
    ipaddress.ip_network("2001:db8::/32"),      # Documentation (RFC 3849)
    ipaddress.ip_network("2002::/16"),          # 6to4 (RFC 3056)
    ipaddress.ip_network("fc00::/7"),           # Unique local (RFC 4193)
    ipaddress.ip_network("fe80::/10"),          # Link-local (RFC 4291)
    ipaddress.ip_network("ff00::/8"),           # Multicast (RFC 4291)
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
    except (_socket.gaierror, OSError):
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
    except (_socket.gaierror, OSError):
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
            hostname, first_ips, second_ips,
        )
        return rebind_error

    # Check second resolution against private ranges (redundant but safe)
    if second_ips:
        second_blocked = _check_ips_against_blocklist(hostname, url, second_ips)
        if second_blocked:
            return second_blocked

    return None
