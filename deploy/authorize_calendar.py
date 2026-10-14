#!/usr/bin/env python3
"""Script local para autorizar Google Calendar API sin problemas de IP privada.

Usa http://localhost:8080/callback (permitido por Google OAuth para loopback),
recibe el código, obtiene el nuevo refresh_token con scope calendar.events,
actualiza app/constants.py y lo sincroniza al servidor de producción vía SFTP.

Uso:
    python3 deploy/authorize_calendar.py
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import re
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent
WORKSPACE_ROOT = REPO_ROOT.parent

# Cargar constantes locales
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from app.constants import GMAIL_OAUTH_CLIENT_ID, GMAIL_OAUTH_CLIENT_SECRET
except ImportError:
    print("Error: No se pudo importar app.constants")
    sys.exit(1)

REDIRECT_URI = "http://localhost:8080/callback"
SCOPE = "https://www.googleapis.com/auth/calendar.events"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

captured_code: str | None = None
server_should_stop = False


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global captured_code, server_should_stop
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/callback":
            if "code" in params:
                captured_code = params["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Autorizado</title></head>
<body style="font-family: sans-serif; background: #0f172a; color: white; display: flex; justify-content: center; align-items: center; height: 100vh;">
  <div style="background: #1e293b; padding: 2rem; border-radius: 10px; text-align: center;">
    <h1 style="color: #38bdf8;">\xe2\x9c\x93 \xc2\xa1C\xc3\xb3digo Recibido Exitosamente!</h1>
    <p>Puedes cerrar esta pesta\xc3\xb1a. La terminal est\xc3\xa1 procesando el token y sincronizando con el servidor...</p>
  </div>
</body>
</html>
                """)
                server_should_stop = True
            elif "error" in params:
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                err_msg = params["error"][0]
                self.wfile.write(f"<h2>Error de Google: {err_msg}</h2>".encode("utf-8"))
                server_should_stop = True
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Silencioso
        return


def main():
    print("=" * 70)
    print("  AUTORIZACIÓN DE GOOGLE CALENDAR API (LOCAL LOOPBACK 8080)")
    print("=" * 70)

    # 1. Generar URL de autorización de Google
    auth_params = {
        "client_id": GMAIL_OAUTH_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_link = f"{AUTH_URL}?{urllib.parse.urlencode(auth_params)}"

    print("\n1. Abre este enlace en tu navegador para autorizar con fidelm02@gmail.com:\n")
    print(auth_link)
    print("\n" + "=" * 70)

    # Intentar abrir el navegador automáticamente
    try:
        webbrowser.open(auth_link)
    except Exception:
        pass

    # 2. Iniciar servidor HTTP en localhost:8080 para recibir la redirección
    print("Esperando autorización en http://localhost:8080/callback ...")
    server = HTTPServer(("localhost", 8080), OAuthCallbackHandler)
    server.timeout = 1

    while not server_should_stop:
        server.handle_request()

    server.server_close()

    if not captured_code:
        print("\nError: No se recibió ningún código de autorización.")
        sys.exit(1)

    print("\n2. Código recibido. Obteniendo nuevo refresh_token de Google...")

    # 3. Canjear código por tokens
    token_payload = urllib.parse.urlencode({
        "client_id": GMAIL_OAUTH_CLIENT_ID,
        "client_secret": GMAIL_OAUTH_CLIENT_SECRET,
        "code": captured_code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
    }).encode("utf-8")

    req = urllib.request.Request(TOKEN_URL, data=token_payload, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            token_data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"\nError al canjear código con Google: {exc}")
        sys.exit(1)

    new_refresh = token_data.get("refresh_token")
    new_access = token_data.get("access_token")

    if not new_refresh:
        print("\nAviso: Google no devolvió un nuevo refresh_token (puede que ya existiera).")
        print("Respuesta de tokens:", token_data)
        sys.exit(1)

    print("\n✓ ¡Nuevo refresh_token de Google Calendar obtenido con éxito!")

    # 4. Guardar en data/google_calendar_token.json local y en constants.py
    data_dir = REPO_ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    with open(data_dir / "google_calendar_token.json", "w", encoding="utf-8") as f:
        json.dump(token_data, f, indent=2)

    constants_file = REPO_ROOT / "app" / "constants.py"
    if constants_file.is_file():
        content = constants_file.read_text(encoding="utf-8")
        # Actualizar GMAIL_OAUTH_REFRESH_TOKEN en constants.py
        if 'GMAIL_OAUTH_REFRESH_TOKEN' in content:
            content = re.sub(
                r'GMAIL_OAUTH_REFRESH_TOKEN:\s*str\s*=\s*os\.getenv\(\s*"GMAIL_OAUTH_REFRESH_TOKEN",[\s\S]*?\n\)',
                f'GMAIL_OAUTH_REFRESH_TOKEN: str = os.getenv(\n    "GMAIL_OAUTH_REFRESH_TOKEN",\n    "{new_refresh}",\n)',
                content,
            )
        if 'GMAIL_OAUTH_ACCESS_TOKEN' in content and new_access:
            content = re.sub(
                r'GMAIL_OAUTH_ACCESS_TOKEN:\s*str\s*=\s*os\.getenv\(\s*"GMAIL_OAUTH_ACCESS_TOKEN",[\s\S]*?\n\)',
                f'GMAIL_OAUTH_ACCESS_TOKEN: str = os.getenv(\n    "GMAIL_OAUTH_ACCESS_TOKEN",\n    "{new_access}",\n)',
                content,
            )
        constants_file.write_text(content, encoding="utf-8")
        print("✓ Actualizado app/constants.py con el nuevo refresh_token.")

    # 5. Sincronizar al servidor remoto
    print("\n3. Sincronizando credenciales al servidor local (deploy/sync_to_server.py)...")
    try:
        from deploy.sync_to_server import main as sync_main
        sync_main()
        print("\n" + "=" * 70)
        print("  ¡VINCULACIÓN COMPLETADA Y DESPLEGADA EN EL SERVIDOR EXITOSAMENTE!")
        print("  Ahora tus eventos de WhatsApp se insertarán directamente por API.")
        print("=" * 70)
    except Exception as sync_exc:
        print(f"Error al sincronizar al servidor: {sync_exc}")
        print("Por favor ejecuta manualmente: python3 deploy/sync_to_server.py")


if __name__ == "__main__":
    main()
