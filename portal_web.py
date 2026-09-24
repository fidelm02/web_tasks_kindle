#!/usr/bin/env python3
"""Controlador Daemon & CLI para el Portal Pro de Kindle Tasks.

Administra el ciclo de vida del segundo portal (puerto 8090) optimizado
para iPad, celular y laptop, integrando Tablero Jira, Crones y Estimador IA.

Uso:
    python3 portal_web.py start
    python3 portal_web.py stop
    python3 portal_web.py restart
    python3 portal_web.py status
    python3 portal_web.py foreground
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
PID_FILE: Path = BASE_DIR / ".portal_web.pid"
LOG_FILE: Path = BASE_DIR / "portal.log"
PORT: int = 8090

IS_WINDOWS: bool = os.name == "nt"
VENV_PYTHON: Path = (
    VENV_DIR / "Scripts" / "python.exe"
    if IS_WINDOWS
    else VENV_DIR / "bin" / "python"
)


def _ensure_venv() -> None:
    if VENV_PYTHON.is_file():
        return
    print(f"Creando entorno virtual en {VENV_DIR} ...")
    subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)


def _dependencies_up_to_date() -> bool:
    if not (INSTALLED_MARKER.is_file() and REQUIREMENTS_FILE.is_file()):
        return False
    return INSTALLED_MARKER.stat().st_mtime >= REQUIREMENTS_FILE.stat().st_mtime


def _install_dependencies() -> None:
    if _dependencies_up_to_date():
        return
    print("Instalando dependencias requeridas...")
    python_bin = str(VENV_PYTHON)
    subprocess.run([python_bin, "-m", "pip", "install", "--upgrade", "pip"], check=True)
    subprocess.run([python_bin, "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)], check=True)
    INSTALLED_MARKER.write_text("ok", encoding="utf-8")


def _local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return str(sock.getsockname()[0])
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def _get_running_pid() -> int | None:
    if not PID_FILE.is_file():
        return None
    try:
        raw_pid = PID_FILE.read_text(encoding="utf-8").strip()
        pid = int(raw_pid)
    except (ValueError, OSError):
        PID_FILE.unlink(missing_ok=True)
        return None

    try:
        os.kill(pid, 0)
    except OSError:
        PID_FILE.unlink(missing_ok=True)
        return None

    cmdline_path = Path(f"/proc/{pid}/cmdline")
    if cmdline_path.is_file():
        try:
            cmdline = cmdline_path.read_text(encoding="utf-8")
            if "uvicorn" not in cmdline and "portal.main:app" not in cmdline:
                PID_FILE.unlink(missing_ok=True)
                return None
        except OSError:
            pass

    return pid


def cmd_start() -> None:
    existing_pid = _get_running_pid()
    ip = _local_ip()
    if existing_pid is not None:
        print("El Portal Pro ya está en ejecución.")
        print(f"  PID:     {existing_pid}")
        print(f"  URL LAN: http://{ip}:{PORT}/")
        print("Para detenerlo ejecuta: python3 portal_web.py stop")
        return

    _ensure_venv()
    _install_dependencies()

    log_handle = open(LOG_FILE, "a", encoding="utf-8")
    python_bin = str(VENV_PYTHON)
    args = [
        python_bin,
        "-m",
        "uvicorn",
        "portal.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        str(PORT),
    ]

    popen_kwargs = {
        "stdout": log_handle,
        "stderr": subprocess.STDOUT,
        "cwd": str(BASE_DIR),
    }

    if IS_WINDOWS:
        flags = (
            subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
            | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        )
        proc = subprocess.Popen(args, creationflags=flags, **popen_kwargs)
    else:
        proc = subprocess.Popen(args, start_new_session=True, **popen_kwargs)

    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    time.sleep(1.0)

    active_pid = _get_running_pid()
    if active_pid is None:
        print("[ERROR] El portal no pudo iniciar. Revisa 'portal.log':")
        if LOG_FILE.is_file():
            print(LOG_FILE.read_text(encoding="utf-8")[-1000:])
        sys.exit(1)

    print("============================================================")
    print("  Kindle Tasks Pro Portal (iPad / Laptop / Mobile)")
    print("============================================================")
    print(f"  PID:      {active_pid}")
    print(f"  Puerto:   {PORT}")
    print(f"  URL LAN:  http://{ip}:{PORT}/")
    print(f"  Log:      {LOG_FILE}")
    print("============================================================")


def cmd_stop() -> None:
    pid = _get_running_pid()
    if pid is None:
        print("El Portal Pro no está en ejecución.")
        PID_FILE.unlink(missing_ok=True)
        return

    print(f"Deteniendo Portal Pro (PID {pid}) ...")
    if IS_WINDOWS:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False)
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass

        for _ in range(30):
            try:
                os.kill(pid, 0)
                time.sleep(0.1)
            except OSError:
                break
        else:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass

    PID_FILE.unlink(missing_ok=True)
    print("Portal Pro detenido con éxito.")


def cmd_restart() -> None:
    print("Reiniciando Portal Pro...")
    cmd_stop()
    time.sleep(0.5)
    cmd_start()


def cmd_status() -> None:
    pid = _get_running_pid()
    ip = _local_ip()
    if pid is None:
        print("Estado: DETENIDO (Portal Pro no está corriendo en puerto 8090).")
    else:
        print("Estado: ACTIVO (Portal Pro en ejecución).")
        print(f"  PID:      {pid}")
        print(f"  Puerto:   {PORT}")
        print(f"  URL LAN:  http://{ip}:{PORT}/")
        print(f"  Log:      {LOG_FILE}")


def cmd_foreground() -> None:
    _ensure_venv()
    _install_dependencies()
    ip = _local_ip()
    print("============================================================")
    print("  Ejecutando Portal Pro en primer plano (Ctrl+C para salir)")
    print(f"  URL: http://{ip}:{PORT}/")
    print("============================================================")
    python_bin = str(VENV_PYTHON)
    subprocess.run(
        [
            python_bin,
            "-m",
            "uvicorn",
            "portal.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(PORT),
            "--reload",
        ],
        cwd=str(BASE_DIR),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Controlador CLI del Portal Pro")
    parser.add_argument(
        "action",
        choices=["start", "stop", "restart", "status", "foreground"],
        help="Acción a realizar sobre el servidor del portal",
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
