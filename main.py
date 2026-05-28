"""Entry point for the Coding Agent.

Run with: python main.py
or:       python -m src.main
"""

from __future__ import annotations

import signal
import sys

from src.main import main as _main, _handle_sigint

if __name__ == "__main__":
    signal.signal(signal.SIGINT, _handle_sigint)
    _main()
