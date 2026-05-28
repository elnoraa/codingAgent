"""Desktop notifications for the Coding Agent.

Sends OS-native desktop notifications when long-running tool calls complete.
Supports Windows (powershell), macOS (osascript), and Linux (notify-send).
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import time

from .logging_config import get_logger

logger = get_logger(__name__)

# Minimum duration in seconds before a notification is sent
DEFAULT_MIN_DURATION = 10


def _notify_windows(title: str, message: str) -> bool:
    """Send notification on Windows using PowerShell."""
    try:
        # Use a PowerShell popup as a simple notification
        ps_script = (
            f'[System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms") | Out-Null; '
            f'$popup = New-Object System.Windows.Forms.NotifyIcon; '
            f'$popup.Icon = [System.Drawing.SystemIcons]::Information; '
            f'$popup.BalloonTipIcon = "Info"; '
            f'$popup.BalloonTipTitle = "{title}"; '
            f'$popup.BalloonTipText = "{message}"; '
            f'$popup.Visible = $true; '
            f'$popup.ShowBalloonTip(5000); '
            f'Start-Sleep -Seconds 5; '
            f'$popup.Dispose()'
        )
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug("Windows notification failed: %s", e)
        return False


def _notify_macos(title: str, message: str) -> bool:
    """Send notification on macOS using osascript."""
    try:
        result = subprocess.run(
            ["osascript", "-e", f'display notification "{message}" with title "{title}"'],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug("macOS notification failed: %s", e)
        return False


def _notify_linux(title: str, message: str) -> bool:
    """Send notification on Linux using notify-send."""
    try:
        result = subprocess.run(
            ["notify-send", title, message],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug("Linux notification failed: %s", e)
        return False


def notify(title: str, message: str) -> bool:
    """Send a desktop notification using the OS-native mechanism.

    Returns True if notification was sent, False otherwise.
    Falls back silently if no notification mechanism is available.
    """
    system = platform.system()
    try:
        if system == "Windows":
            return _notify_windows(title, message)
        elif system == "Darwin":
            return _notify_macos(title, message)
        else:  # Linux and others
            return _notify_linux(title, message)
    except Exception as e:
        logger.debug("Desktop notification failed: %s", e)
        return False


def should_notify(elapsed: float, min_duration: int = DEFAULT_MIN_DURATION) -> bool:
    """Determine if a notification should be sent based on elapsed time."""
    return elapsed >= min_duration
