#!/usr/bin/env python3
"""Kindle Tasks legacy launcher wrapper.

Objective:
    Provide backwards compatibility for existing shortcuts and scripts
    by delegating execution to the kindle_web.py CLI manager.

Author:
    Fidel Moreno Miranda <fidelm02@gmail.com>

Usage:
    python3 run.py [start|stop|restart|status|foreground]
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

BASE_DIR: Path = Path(__file__).resolve().parent
CLI_SCRIPT: Path = BASE_DIR / "kindle_web.py"


def main() -> None:
    """Delegate execution to kindle_web.py CLI controller.

    Defaults to foreground mode if no arguments are provided, or
    passes supplied CLI arguments through to kindle_web.py.

    Args:
        None.

    Returns:
        None.
    """
    args: list[str] = (
        sys.argv[1:] if len(sys.argv) > 1 else ["foreground"]
    )
    cmd: list[str] = [sys.executable, str(CLI_SCRIPT), *args]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
