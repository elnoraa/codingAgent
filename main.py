"""Entry point for the Coding Agent.

Run with: python main.py
or:       python -m src.main
"""

from __future__ import annotations

import signal

from src.main import _handle_sigint
from src.main import main as _main

if __name__ == "__main__":
    signal.signal(signal.SIGINT, _handle_sigint)
    _main()
