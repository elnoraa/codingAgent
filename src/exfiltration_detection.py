"""Data exfiltration detection constants for the Coding Agent.

Provides the canonical lists of sensitive files, network commands, script
interpreters, and dangerous function indicators used by the bash command
scanner and other security checks.

Extracted from ``src/security.py`` to give exfiltration detection its own
module (Single Responsibility Principle).
"""

from __future__ import annotations

# Files that should never be read and sent over the network
_EXFIL_SENSITIVE_FILES: frozenset = frozenset(
    {
        ".env",
        ".env.example",
        ".env.local",
        ".env.production",
        "config.json",  # may contain credentials
        ".git-credentials",
        ".gitconfig",
        ".ssh/id_rsa",
        ".ssh/id_rsa.pub",
        ".ssh/id_ed25519",
        ".ssh/id_ed25519.pub",
        ".ssh/config",
        ".ssh/authorized_keys",
        "id_rsa",
        "id_ed25519",
        "credentials.json",
        "credentials.yml",
        "credentials.yaml",
        "service-account.json",
        "service-account-key.json",
        ".npmrc",
        ".netrc",
        "/proc/self/environ",  # H2: contains all environment variables including leaked secrets
        "/proc/self/fd",  # can be used to read open file descriptors
    }
)

# Commands that can send data to remote servers (exfiltration vectors)
_EXFIL_NETWORK_COMMANDS: frozenset = frozenset(
    {
        "curl",
        "wget",
        "nc",
        "ncat",
        "netcat",
        "socat",
        "ftp",
        "sftp",
        "scp",
        "rsync",
        "telnet",
    }
)

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
_SCRIPT_FILE_READ_INDICATORS: frozenset = frozenset(
    {
        "open(",
        ".read(",
        ".read_text(",
        ".read_bytes(",
        "readFile(",
        "readFileSync(",
        "readFileSync (",
        "createReadStream(",
        "createReadStream (",
        "File.read(",
        "File.open(",
        "fread(",
        "file_get_contents(",
    }
)

# Dangerous function/module calls that indicate network operations in script code
_SCRIPT_NETWORK_INDICATORS: frozenset = frozenset(
    {
        "urllib.request.urlopen(",
        "urllib.request.Request(",
        "requests.get(",
        "requests.post(",
        "requests.put(",
        "requests.delete(",
        "urlopen(",
        "urlretrieve(",
        "fetch(",
        "http.",
        "https.",
        "net/http",
        "net::HTTP",
        "curl ",
        "wget ",
    }
)
