"""Servicio de Integración Directa con la API REST de Google Calendar v3.

Permite:
1. Generar la URL de autorización OAuth 2.0 (scope calendar.events).
2. Intercambiar el código por tokens y guardar refresh_token.
3. Refrescar access_token automáticamente.
4. Crear eventos directamente en el Google Calendar principal de Fidel con invitaciones
   automáticas enviadas por Google a Laura (Lau/Lalis) u otros participantes (sendUpdates=all).
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import logging
from pathlib import Path
from typing import Any
import urllib.parse
import urllib.request
import urllib.error

from app.constants import GMAIL_OAUTH_CLIENT_ID, GMAIL_OAUTH_CLIENT_SECRET

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
TOKEN_FILE = DATA_DIR / "google_calendar_token.json"

TIMEZONE = "America/Toronto"
CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"
OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
OAUTH_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
CALENDAR_SCOPES = "https://www.googleapis.com/auth/calendar.events"


def get_auth_url(redirect_uri: str) -> str:
    """Genera la URL de consentimiento OAuth 2.0 para Google Calendar."""
    params = {
        "client_id": GMAIL_OAUTH_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": CALENDAR_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{OAUTH_AUTH_URL}?{urllib.parse.urlencode(params)}"


def exchange_code_for_token(code: str, redirect_uri: str) -> dict[str, Any]:
    """Intercambia el código de autorización por tokens de acceso y refresco."""
    data = urllib.parse.urlencode({
        "client_id": GMAIL_OAUTH_CLIENT_ID,
        "client_secret": GMAIL_OAUTH_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }).encode("utf-8")

    req = urllib.request.Request(OAUTH_TOKEN_URL, data=data, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            token_data = json.loads(resp.read().decode("utf-8"))
            save_tokens(token_data)
            return token_data
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8")
        logger.error("Error al intercambiar código OAuth: %s", err_body)
        raise RuntimeError(f"Fallo al autenticar con Google: {err_body}")


def save_tokens(token_data: dict[str, Any]) -> None:
    """Guarda los tokens en data/google_calendar_token.json."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if TOKEN_FILE.is_file():
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = {}

    # Si la respuesta no incluye refresh_token, preservamos el anterior
    if not token_data.get("refresh_token") and existing.get("refresh_token"):
        token_data["refresh_token"] = existing["refresh_token"]

    token_data["updated_at"] = datetime.now().isoformat()
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(token_data, f, indent=2)


def load_tokens() -> dict[str, Any] | None:
    """Carga los tokens guardados."""
    if not TOKEN_FILE.is_file():
        return None
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def get_valid_access_token() -> str | None:
    """Obtiene un token de acceso válido, refrescándolo si es necesario."""
    tokens = load_tokens()
    if not tokens:
        return None

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        return None

    # Intentar refrescar siempre para garantizar validez inmediata
    data = urllib.parse.urlencode({
        "client_id": GMAIL_OAUTH_CLIENT_ID,
        "client_secret": GMAIL_OAUTH_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode("utf-8")

    req = urllib.request.Request(OAUTH_TOKEN_URL, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            fresh = json.loads(resp.read().decode("utf-8"))
            tokens["access_token"] = fresh["access_token"]
            tokens["expires_in"] = fresh.get("expires_in", 3600)
            tokens["updated_at"] = datetime.now().isoformat()
            save_tokens(tokens)
            return fresh["access_token"]
    except Exception as exc:
        logger.warning("No se pudo refrescar token de Google Calendar: %s", exc)
        return None


def is_connected() -> bool:
    """Verifica si la API de Google Calendar está lista para usarse."""
    tokens = load_tokens()
    return bool(tokens and tokens.get("refresh_token"))


def create_calendar_event(
    title: str,
    description: str,
    start_dt: datetime,
    end_dt: datetime,
    attendee_emails: list[str] | None = None,
) -> tuple[bool, str, str | None]:
    """Crea un evento directamente en el calendario principal de Google Calendar.

    Args:
        title: Título del evento.
        description: Descripción o notas.
        start_dt: Fecha y hora de inicio.
        end_dt: Fecha y hora de fin.
        attendee_emails: Lista de correos de invitados (Lau, etc.).

    Returns:
        tuple[bool, str, str | None]: (Éxito, Mensaje, URL del evento en Google Calendar)
    """
    token = get_valid_access_token()
    if not token:
        return False, "Google Calendar no está vinculado por OAuth aún.", None

    attendees = []
    if attendee_emails:
        for em in attendee_emails:
            clean = em.strip()
            if clean and "@" in clean:
                attendees.append({"email": clean})

    payload = {
        "summary": title,
        "description": description,
        "start": {
            "dateTime": start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": TIMEZONE,
        },
        "end": {
            "dateTime": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": TIMEZONE,
        },
        "attendees": attendees,
        "reminders": {
            "useDefault": True,
        },
    }

    # sendUpdates=all envía notificaciones oficiales de Google a todos los invitados
    url = f"{CALENDAR_API_BASE}/calendars/primary/events?sendUpdates=all"
    req_body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            html_link = res_data.get("htmlLink")
            event_id = res_data.get("id")
            logger.info("Evento creado en Google Calendar exitosamente: %s (%s)", title, event_id)
            return True, "Evento creado exitosamente en Google Calendar", html_link
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8")
        logger.error("Error HTTP de Google Calendar API (%d): %s", exc.code, err_body)
        return False, f"Error Google Calendar ({exc.code}): {err_body}", None
    except Exception as exc:
        logger.error("Excepción al llamar Google Calendar API: %s", exc)
        return False, str(exc), None
