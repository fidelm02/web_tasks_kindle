#!/usr/bin/env python3
"""Kindle Tasks Daemon & CLI Controller.

Objective:
    Provide a unified CLI controller to run Kindle Tasks as a
    background daemon, stop it, inspect status, or execute it in the
    foreground for real-time debugging and tracebacks.

Author:
    Fidel Moreno Miranda <fidelm02@gmail.com>

Usage:
    python3 kindle_web.py start
    python3 kindle_web.py stop
    python3 kindle_web.py restart
    python3 kindle_web.py status
    python3 kindle_web.py foreground
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

BASE_DIR: Path = Path(__file__).resolve().parent
VENV_DIR: Path = BASE_DIR / ".venv"
REQUIREMENTS_FILE: Path = BASE_DIR / "requirements.txt"
INSTALLED_MARKER: Path = VENV_DIR / ".requirements_installed"
PID_FILE: Path = BASE_DIR / ".kindle_tasks.pid"
LOG_FILE: Path = BASE_DIR / "kindle_tasks.log"
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


def _get_running_pid() -> int | None:
    """Retrieve the PID of the currently running server instance.

    Reads the PID file if present, verifies that the process exists
    and that its command line contains the application module. Stale
    PID files are removed automatically.

    Args:
        None.

    Returns:
        int | None: The active process identifier, or None if not
            running.
    """
    if not PID_FILE.is_file():
        return None
    try:
        raw_pid: str = PID_FILE.read_text(encoding="utf-8").strip()
        pid: int = int(raw_pid)
    except (ValueError, OSError):
        PID_FILE.unlink(missing_ok=True)
        return None

    try:
        os.kill(pid, 0)
    except OSError:
        PID_FILE.unlink(missing_ok=True)
        return None

    cmdline_path: Path = Path(f"/proc/{pid}/cmdline")
    if cmdline_path.is_file():
        try:
            cmdline: str = cmdline_path.read_text(encoding="utf-8")
            if "uvicorn" not in cmdline and "app.main:app" not in cmdline:
                PID_FILE.unlink(missing_ok=True)
                return None
        except OSError:
            pass

    return pid


def cmd_start() -> None:
    """Start the Kindle Tasks server in background daemon mode.

    Verifies whether the server is already active. If not, sets up the
    environment and spawns the Uvicorn process detached from the
    terminal, directing stdout/stderr to a log file.

    Args:
        None.

    Returns:
        None.
    """
    existing_pid: int | None = _get_running_pid()
    ip: str = _local_ip()
    if existing_pid is not None:
        print("Kindle Tasks ya está en ejecución.")
        print(f"  PID:     {existing_pid}")
        print(f"  URL LAN: http://{ip}:{PORT}/")
        print("Para detenerlo ejecuta: python3 kindle_web.py stop")
        return

    _ensure_venv()
    _install_dependencies()

    log_handle = open(LOG_FILE, "a", encoding="utf-8")
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
        "--ws",
        "none",
    ]

    process = subprocess.Popen(
        args,
        cwd=str(BASE_DIR),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    PID_FILE.write_text(str(process.pid), encoding="utf-8")
    time.sleep(0.5)

    if process.poll() is not None:
        print("Error: El servidor falló al iniciar en segundo plano.")
        print(f"Revisa los logs en: {LOG_FILE}")
        PID_FILE.unlink(missing_ok=True)
        return

    print("=" * 60)
    print("Kindle Tasks iniciado en segundo plano (Daemon).")
    print(f"PID:     {process.pid}")
    print(f"URL LAN: http://{ip}:{PORT}/")
    print(f"Logs:    {LOG_FILE}")
    print("Para detener: python3 kindle_web.py stop")
    print("=" * 60)


def cmd_stop() -> None:
    """Stop the running Kindle Tasks server instance.

    Reads the active PID and issues SIGTERM for graceful shutdown,
    falling back to SIGKILL if the process fails to terminate within
    a timeout window.

    Args:
        None.

    Returns:
        None.
    """
    pid: int | None = _get_running_pid()
    if pid is None:
        print(
            "No se encontró ningún servidor de Kindle Tasks en ejecución."
        )
        return

    print(f"Deteniendo Kindle Tasks (PID: {pid}) ...")
    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(30):
            time.sleep(0.1)
            try:
                os.kill(pid, 0)
            except OSError:
                break
        else:
            print("El proceso no respondió a SIGTERM; forzando SIGKILL...")
            os.kill(pid, signal.SIGKILL)
            time.sleep(0.2)
    except OSError as err:
        print(f"Error al detener proceso: {err}")
    finally:
        PID_FILE.unlink(missing_ok=True)

    print("Servidor detenido correctamente.")


def cmd_status() -> None:
    """Display the current execution status of the server.

    Checks if a server process is currently running and prints its
    process ID and local network address.

    Args:
        None.

    Returns:
        None.
    """
    pid: int | None = _get_running_pid()
    if pid is not None:
        ip: str = _local_ip()
        print(f"Estado:  EN EJECUCIÓN (PID: {pid})")
        print(f"URL LAN: http://{ip}:{PORT}/")
        print(f"Logs:    {LOG_FILE}")
    else:
        print("Estado:  DETENIDO (No hay servidor en ejecución)")


def cmd_restart() -> None:
    """Restart the Kindle Tasks server daemon.

    Stops any active server instance and subsequently launches a fresh
    background daemon.

    Args:
        None.

    Returns:
        None.
    """
    cmd_stop()
    time.sleep(0.5)
    cmd_start()


def cmd_foreground() -> None:
    """Run the server in the foreground with live console logs.

    Ensures the environment is set up and checks for background
    daemons before executing Uvicorn directly on the current terminal
    to display tracebacks in real time.

    Args:
        None.

    Returns:
        None.
    """
    pid: int | None = _get_running_pid()
    if pid is not None:
        print("Atención: Ya hay una instancia corriendo en segundo plano.")
        print(f"PID: {pid}")
        print("Detén la instancia previa ejecutando:")
        print("    python3 kindle_web.py stop")
        return

    _ensure_venv()
    _install_dependencies()

    ip: str = _local_ip()
    print("=" * 60)
    print(f"Kindle Tasks en primer plano: http://{ip}:{PORT}/")
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
        "--ws",
        "none",
    ]
    os.execv(python_bin, args)


def main() -> None:
    """Parse CLI arguments and dispatch the requested command.

    Args:
        None.

    Returns:
        None.
    """
    parser = argparse.ArgumentParser(
        description="Kindle Tasks CLI controller & daemon manager.",
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="start",
        choices=["start", "stop", "restart", "status", "foreground"],
        help="Action to execute (default: start).",
    )
    args = parser.parse_args()

    actions = {
        "start": cmd_start,
        "stop": cmd_stop,
        "restart": cmd_restart,
        "status": cmd_status,
        "foreground": cmd_foreground,
    }
    actions[args.action]()


if __name__ == "__main__":
    main()
