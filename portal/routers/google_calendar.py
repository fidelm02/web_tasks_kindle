"""Router FastAPI para Autenticación OAuth 2.0 con Google Calendar."""

from __future__ import annotations

import logging
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from portal.services import google_calendar_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/google", tags=["Google Calendar"])


@router.get("/login")
async def google_login(request: Request):
    """Inicia el flujo de autorización OAuth para Google Calendar."""
    # Usar host de la petición actual (ej. 192.168.0.98:8090)
    base_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/google/callback"
    auth_url = google_calendar_service.get_auth_url(redirect_uri)
    logger.info("Iniciando OAuth Google Calendar con redirect_uri: %s", redirect_uri)
    return RedirectResponse(auth_url)


@router.get("/callback", response_class=HTMLResponse)
async def google_callback(
    request: Request,
    code: str | None = Query(None),
    error: str | None = Query(None),
):
    """Recibe el código de autorización y guarda los tokens."""
    if error:
        return HTMLResponse(
            f"<h2>Error en autorización de Google</h2><p>{error}</p>",
            status_code=400,
        )

    if not code:
        return HTMLResponse("<h2>No se recibió código de autorización.</h2>", status_code=400)

    base_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/google/callback"

    try:
        tokens = google_calendar_service.exchange_code_for_token(code, redirect_uri)
        return HTMLResponse("""
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Google Calendar Conectado</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
    .card { background: #1e293b; padding: 2.5rem; border-radius: 1rem; border: 1px solid #334155; text-align: center; max-width: 480px; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.5); }
    .icon { font-size: 3.5rem; margin-bottom: 1rem; }
    h1 { margin: 0 0 0.5rem 0; font-size: 1.5rem; color: #38bdf8; }
    p { color: #94a3b8; line-height: 1.6; margin-bottom: 1.5rem; font-size: 0.95rem; }
    .btn { background: #0284c7; color: white; padding: 0.75rem 1.5rem; border-radius: 0.5rem; text-decoration: none; font-weight: 500; display: inline-block; transition: background 0.2s; }
    .btn:hover { background: #0369a1; }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">📅✨</div>
    <h1>¡Google Calendar Conectado!</h1>
    <p>Tu cuenta <strong>fidelm02@gmail.com</strong> ha sido vinculada exitosamente con permisos para gestionar eventos de calendario.</p>
    <p>A partir de ahora, cuando pidas agendar eventos en WhatsApp, se crearán <strong>directamente en tu Google Calendar</strong> y Google enviará la invitación automática a Lau (<strong>lalisgallego@hotmail.com</strong>).</p>
    <a href="/whatsapp" class="btn">Volver al Panel de WhatsApp</a>
  </div>
</body>
</html>
        """)
    except Exception as exc:
        return HTMLResponse(
            f"<h2>Error al vincular Google Calendar</h2><p>{exc}</p>",
            status_code=500,
        )


@router.get("/status")
async def google_status():
    """Estado de conexión con Google Calendar."""
    return JSONResponse({
        "connected": google_calendar_service.is_connected(),
    })
