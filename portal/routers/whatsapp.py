"""Enrutador de integración y control de WhatsApp (Grupo 'Chismoso').

Provee:
- Vista Web en el Portal (/whatsapp) con monitor de estado y log de actividad.
- Webhook (/api/whatsapp/webhook) para recibir mensajes del bridge Node.js.
- Simulador (/api/whatsapp/simulate) para probar interpretación con Gemini.
"""

from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from portal.core.templates import portal_templates
from portal.services import whatsapp_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["whatsapp"])

# Estado de conexión en memoria actualizado por el bridge
_bridge_status = {
    "connected": False,
    "last_seen": None,
    "qr_code": None,
    "group_name": "Chismoso",
    "phone": None,
}


class WhatsAppWebhookPayload(BaseModel):
    """Payload enviado por el microservicio bridge de WhatsApp."""
    sender_name: str = "Fidel"
    sender_phone: str = ""
    group_name: str = "Chismoso"
    message_type: str = "text"  # 'text' o 'audio'
    text_content: str | None = None
    audio_base64: str | None = None
    audio_mimetype: str = "audio/ogg"


@router.get("/whatsapp", response_class=HTMLResponse)
async def whatsapp_dashboard(request: Request):
    """Renderiza el panel de monitoreo y configuración de WhatsApp en Portal Pro."""
    recent_activity = whatsapp_service.get_recent_activity()
    return portal_templates.TemplateResponse(
        request,
        "whatsapp.html",
        {
            "active_tab": "whatsapp",
            "bridge_status": _bridge_status,
            "recent_activity": recent_activity,
            "page_title": "Integración WhatsApp Chismoso | Kindle Tasks Pro",
        },
    )


@router.post("/api/whatsapp/webhook")
async def whatsapp_incoming_webhook(payload: WhatsAppWebhookPayload):
    """Endpoint llamado por el servicio bridge cuando se recibe un mensaje en WhatsApp."""
    try:
        result = whatsapp_service.process_whatsapp_message(
            sender_name=payload.sender_name,
            sender_phone=payload.sender_phone,
            group_name=payload.group_name,
            message_type=payload.message_type,
            text_content=payload.text_content,
            audio_base64=payload.audio_base64,
            audio_mimetype=payload.audio_mimetype,
        )
        return JSONResponse(result)
    except Exception as exc:
        logger.error("Error al procesar webhook de WhatsApp: %s", exc)
        return JSONResponse(
            {
                "status": "error",
                "reply": "⚠️ Ocurrió un error inesperado al procesar el mensaje con IA.",
                "detail": str(exc),
            },
            status_code=500,
        )


@router.post("/api/whatsapp/status/update")
async def update_bridge_status(
    connected: bool = Form(...),
    qr_code: str | None = Form(None),
    phone: str | None = Form(None),
):
    """Actualiza el estado de conexión del bridge."""
    from datetime import datetime

    _bridge_status["connected"] = connected
    _bridge_status["qr_code"] = qr_code
    _bridge_status["phone"] = phone
    _bridge_status["last_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {"status": "ok", "bridge_status": _bridge_status}


@router.get("/api/whatsapp/status")
async def get_bridge_status():
    """Consulta el estado actual de la conexión de WhatsApp."""
    return JSONResponse(_bridge_status)


@router.post("/api/whatsapp/simulate")
async def simulate_whatsapp_message(
    sender_name: str = Form("Fidel"),
    message_text: str = Form(...),
):
    """Simula un mensaje de WhatsApp para validar la clasificación con Gemini desde la UI."""
    result = whatsapp_service.process_whatsapp_message(
        sender_name=sender_name,
        sender_phone="simulation",
        group_name="Chismoso",
        message_type="text",
        text_content=message_text,
    )
    return JSONResponse(result)
