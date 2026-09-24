#!/usr/bin/env python3
"""Controlador Daemon & CLI para el Bridge de WhatsApp (Grupo 'Chismoso').

Administra el ciclo de vida del microservicio Node.js (Baileys)
que captura audios y textos del grupo Chismoso y los envía al Portal Pro (puerto 8090).

Uso:
    python3 whatsapp_web.py start
    python3 whatsapp_web.py stop
    python3 whatsapp_web.py restart
    python3 whatsapp_web.py status
    python3 whatsapp_web.py logs
    python3 whatsapp_web.py qr
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

BASE_DIR: Path = Path(__file__).resolve().parent
BRIDGE_DIR: Path = BASE_DIR / "whatsapp_bridge"
PID_FILE: Path = BASE_DIR / ".whatsapp_bridge.pid"
LOG_FILE: Path = BASE_DIR / "whatsapp_bridge.log"


def _read_pid() -> int | None:
    if not PID_FILE.is_file():
        return None
    try:
        pid = int(PID_FILE.read_text().strip())
        return pid if pid > 0 else None
    except (ValueError, OSError):
        return None


def _is_running(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _install_bridge_deps() -> None:
    """Instala node_modules si no existen."""
    node_modules = BRIDGE_DIR / "node_modules"
    if not node_modules.is_dir():
        print("Instalando dependencias de Node.js en whatsapp_bridge...")
        subprocess.run(["npm", "install"], cwd=str(BRIDGE_DIR), check=True)


def start() -> None:
    pid = _read_pid()
    if _is_running(pid):
        print(f"El bridge de WhatsApp ya está en ejecución (PID: {pid}).")
        return

    _install_bridge_deps()

    with open(LOG_FILE, "a", encoding="utf-8") as log_f:
        proc = subprocess.Popen(
            ["node", "index.js"],
            cwd=str(BRIDGE_DIR),
            stdout=log_f,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

    PID_FILE.write_text(str(proc.pid))
    time.sleep(1.5)

    if _is_running(proc.pid):
        print("=" * 60)
        print("  WhatsApp Bridge (Grupo 'Chismoso') iniciado en segundo plano")
        print("=" * 60)
        print(f"  PID:      {proc.pid}")
        print(f"  Log:      {LOG_FILE}")
        print("  Para ver QR de vinculación: python3 whatsapp_web.py qr")
        print("  O consulta la pestaña en el Portal Pro: http://192.168.0.98:8090/whatsapp")
        print("=" * 60)
    else:
        print("Error: El bridge no pudo mantenerse en ejecución. Revisa whatsapp_bridge.log:")
        if LOG_FILE.is_file():
            print(LOG_FILE.read_text()[-500:])


def stop() -> None:
    pid = _read_pid()
    if not _is_running(pid):
        print("El bridge de WhatsApp no está en ejecución.")
        if PID_FILE.is_file():
            PID_FILE.unlink(missing_ok=True)
        return

    print(f"Deteniendo WhatsApp Bridge (PID {pid}) ...")
    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(30):
            time.sleep(0.2)
            if not _is_running(pid):
                break
        else:
            print("Forzando detención SIGKILL...")
            os.kill(pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass

    PID_FILE.unlink(missing_ok=True)
    print("WhatsApp Bridge detenido con éxito.")


def status() -> None:
    pid = _read_pid()
    if _is_running(pid):
        print(f"Estado: ACTIVO (WhatsApp Bridge en ejecución con PID {pid}).")
        print(f"  Log: {LOG_FILE}")
    else:
        print("Estado: DETENIDO (WhatsApp Bridge no se está ejecutando).")


def show_qr() -> None:
    """Muestra el QR del log más reciente."""
    if not LOG_FILE.is_file():
        print("No se encontró archivo de log aún.")
        return
    lines = LOG_FILE.read_text().splitlines()
    print("\nÚltimas líneas del log / Código QR:")
    print("-" * 60)
    print("\n".join(lines[-40:]))
    print("-" * 60)


def show_logs(lines_count: int = 50) -> None:
    if not LOG_FILE.is_file():
        print("No existe archivo de log.")
        return
    lines = LOG_FILE.read_text().splitlines()
    print("\n".join(lines[-lines_count:]))


def main() -> None:
    parser = argparse.ArgumentParser(description="Controlador WhatsApp Bridge")
    parser.add_argument(
        "action",
        choices=["start", "stop", "restart", "status", "qr", "logs"],
        help="Acción a realizar",
    )
    args = parser.parse_args()

    if args.action == "start":
        start()
    elif args.action == "stop":
        stop()
    elif args.action == "restart":
        stop()
        start()
    elif args.action == "status":
        status()
    elif args.action == "qr":
        show_qr()
    elif args.action == "logs":
        show_logs()


if __name__ == "__main__":
    main()
