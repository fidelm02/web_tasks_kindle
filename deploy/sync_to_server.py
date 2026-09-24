#!/usr/bin/env python3
"""Script de sincronización y despliegue hacia el servidor local (Kindle Web Tasks).

Uso:
    python3 deploy/sync_to_server.py
"""

from __future__ import annotations

from pathlib import Path
import sys

# Agregar ruta para cargar configuración del servidor
CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent
WORKSPACE_ROOT = REPO_ROOT.parent
TESTS_DIR = WORKSPACE_ROOT / "tests"

if str(TESTS_DIR) not in sys.path:
    sys.path.append(str(TESTS_DIR))

try:
    from data_mini_server import data as server_config  # type: ignore
except ImportError:
    print("Error: No se pudo encontrar tests/data_mini_server.py")
    sys.exit(1)

import paramiko


def execute_ssh_command(client: paramiko.SSHClient, cmd: str) -> tuple[int, str, str]:
    """Execute command over SSH and return exit status, stdout and stderr."""
    stdin, stdout, stderr = client.exec_command(cmd)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8").strip()
    err = stderr.read().decode("utf-8").strip()
    return exit_code, out, err


def main() -> None:
    print("[1/4] Conectando por SSH al servidor...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            server_config["ip"],
            username=server_config["user"],
            password=server_config["pass"],
            timeout=10,
        )
    except Exception as exc:
        print(f"Error al conectar por SSH: {exc}")
        sys.exit(1)

    repo_path = server_config.get("repo_path", "/home/fmoreno/Dev/web_tasks_kindle")

    try:
        # Paso 1: Detener los servicios en el servidor
        print("[2/4] Deteniendo servicios en el servidor...")
        code, out, err = execute_ssh_command(
            client, f"cd {repo_path} && python3 kindle_web.py stop && python3 portal_web.py stop && (python3 whatsapp_web.py stop || true)"
        )
        if out:
            print(f"       {out}")
        if err:
            print(f"       [Aviso]: {err}")

        # Paso 2: Git pull y sincronización de constants.py
        print("[3/4] Ejecutando git pull y sincronizando archivos...")
        code, out, err = execute_ssh_command(
            client, f"cd {repo_path} && git pull origin main"
        )
        if out:
            print(f"       Git: {out}")
        if err:
            print(f"       Git info/err: {err}")

        # Sincronizar app/constants.py y data/health_data.json hacia el servidor remoto vía SFTP
        sftp = client.open_sftp()
        local_constants = REPO_ROOT / "app" / "constants.py"
        if local_constants.exists():
            remote_constants = f"{repo_path}/app/constants.py"
            sftp.put(str(local_constants), remote_constants)
            print("       Sincronizado app/constants.py vía SFTP exitosamente.")

        local_health = REPO_ROOT / "data" / "health_data.json"
        if local_health.exists():
            remote_health = f"{repo_path}/data/health_data.json"
            sftp.put(str(local_health), remote_health)
            print("       Sincronizado data/health_data.json vía SFTP exitosamente.")
        sftp.close()

        # Paso 3: Volver a iniciar los servicios
        print("[4/4] Iniciando los servicios en el servidor (Kindle 8080 y Portal 8090)...")
        code, out, err = execute_ssh_command(
            client, f"cd {repo_path} && python3 kindle_web.py start && python3 portal_web.py start"
        )
        if out:
            print(f"       {out}")
        if err:
            print(f"       [Aviso]: {err}")

        # Verificar estados finales
        code, kindle_status, _ = execute_ssh_command(
            client, f"cd {repo_path} && python3 kindle_web.py status"
        )
        code, portal_status, _ = execute_ssh_command(
            client, f"cd {repo_path} && python3 portal_web.py status"
        )
        code, whatsapp_status, _ = execute_ssh_command(
            client, f"cd {repo_path} && (python3 whatsapp_web.py status || true)"
        )
        print("\nEstado final de los servicios:")
        print("--- Kindle Tasks (8080) ---")
        print(kindle_status)
        print("\n--- Portal Pro (8090) ---")
        print(portal_status)
        print("\n--- WhatsApp Bridge (Chismoso) ---")
        print(whatsapp_status)

        print("\n✓ ¡Sincronización y despliegue completados con éxito!")

    finally:
        client.close()


if __name__ == "__main__":
    main()
