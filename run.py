#!/usr/bin/env python3
"""Kindle Tasks launcher script.

Objective:
    Provide a robust, lightweight entry point to manage tasks across
    devices, specifically designed and optimized for electronic ink
    screens (such as Kindle Scribe) over a local network. This script
    ensures the virtual environment exists, verifies and installs
    dependencies, and starts the Uvicorn ASGI server.

Author:
    Fidel Moreno Miranda <fidelm02@gmail.com>

Usage:
    python3 run.py
"""

from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys

BASE_DIR: Path = Path(__file__).resolve().parent
VENV_DIR: Path = BASE_DIR / ".venv"
REQUIREMENTS_FILE: Path = BASE_DIR / "requirements.txt"
INSTALLED_MARKER: Path = VENV_DIR / ".requirements_installed"
PORT: int = 8080

IS_WINDOWS: bool = os.name == "nt"
VENV_PYTHON: Path = (
    VENV_DIR / "Scripts" / "python.exe"
    if IS_WINDOWS
    else VENV_DIR / "bin" / "python"
)


def _ensure_venv() -> None:
    """Ensure the project virtual environment exists.

    Checks if the virtual environment Python binary exists; if it
    does not, initializes a new virtual environment using the current
    Python interpreter.

    Args:
        None.

    Returns:
        None.

    Raises:
        subprocess.CalledProcessError: If virtual environment creation
            fails.
    """
    if VENV_PYTHON.is_file():
        return
    print(f"Creando entorno virtual en {VENV_DIR} ...")
    subprocess.run(
        [sys.executable, "-m", "venv", str(VENV_DIR)],
        check=True,
    )


def _dependencies_up_to_date() -> bool:
    """Verify if installed dependencies are up to date.

    Compares the modification timestamp of the installation marker
    file against requirements.txt.

    Args:
        None.

    Returns:
        bool: True if marker exists and is newer than or equal to
            requirements.txt modification timestamp, False otherwise.
    """
    if not (INSTALLED_MARKER.is_file() and REQUIREMENTS_FILE.is_file()):
        return False
    marker_mtime: float = INSTALLED_MARKER.stat().st_mtime
    reqs_mtime: float = REQUIREMENTS_FILE.stat().st_mtime
    return marker_mtime >= reqs_mtime


def _install_dependencies() -> None:
    """Install project dependencies into the virtual environment.

    Upgrades pip and installs packages specified in requirements.txt
    if dependencies are determined to be outdated. Upon successful
    installation, writes a marker file.

    Args:
        None.

    Returns:
        None.

    Raises:
        subprocess.CalledProcessError: If package installation fails.
        OSError: If writing the marker file fails.
    """
    if _dependencies_up_to_date():
        return
    print(
        "Instalando dependencias (fastapi, uvicorn, jinja2, filelock) ..."
    )
    python_bin: str = str(VENV_PYTHON)
    subprocess.run(
        [python_bin, "-m", "pip", "install", "--upgrade", "pip"],
        check=True,
    )
    subprocess.run(
        [
            python_bin,
            "-m",
            "pip",
            "install",
            "-r",
            str(REQUIREMENTS_FILE),
        ],
        check=True,
    )
    INSTALLED_MARKER.write_text("ok", encoding="utf-8")


def _local_ip() -> str:
    """Retrieve the primary local IP address of this machine.

    Attempts to determine the network IP by creating a UDP socket
    connection toward a public DNS resolver (without sending data).
    Falls back to localhost if offline or on network error.

    Args:
        None.

    Returns:
        str: The local IP address (e.g., '192.168.1.50') or
            '127.0.0.1' on failure.
    """
    sock: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        ip: str = str(sock.getsockname()[0])
        return ip
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def main() -> None:
    """Prepare environment and execute the web server.

    Ensures the virtual environment is present, verifies that
    dependencies are satisfied, prints access instructions, and
    replaces the current process with Uvicorn serving the FastAPI
    application.

    Args:
        None.

    Returns:
        None.
    """
    _ensure_venv()
    _install_dependencies()

    ip: str = _local_ip()
    print("=" * 60)
    print(f"Kindle Tasks disponible en la LAN: http://{ip}:{PORT}/")
    print("Abre esa dirección desde el navegador del Kindle Scribe.")
    print("Presiona Ctrl+C para detener el servidor.")
    print("=" * 60)

    os.chdir(BASE_DIR)
    python_bin: str = str(VENV_PYTHON)
    args: list[str] = [
        python_bin,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        str(PORT),
    ]
    os.execv(python_bin, args)


if __name__ == "__main__":
    main()
