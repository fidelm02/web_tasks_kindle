"""Servicio de Procesamiento Inteligente de Mensajes y Audios de WhatsApp (Grupo 'Chismoso').

Recibe eventos del bridge de WhatsApp (audios en formato opus/ogg o mensajes de texto),
los procesa directamente con la API multimodal de Google Gemini (gemini-3.6-flash / fallback)
y ejecuta automáticamente la acción requerida:
1. Crear Tarea para Fidel o Lau en storage.py
2. Generar Documento Markdown para Kindle en docs/ o docs_lau/
3. Registrar métricas de salud (peso corporal o hábitos de gym/caminata) en health_service.py
4. Responder consultas o dudas en el grupo de WhatsApp.
"""

from __future__ import annotations

import base64
from datetime import date, datetime, timedelta
import json
import logging
from pathlib import Path
import re
from typing import Any
import urllib.parse
import uuid

from app import storage
from app.constants import GEMINI_TOKEN, MEMBERS_INFO
from app.services import reader_service
from portal.services import health_service, pdf_service, vault_service

logger = logging.getLogger(__name__)

# Modelos candidatos en orden de preferencia y velocidad
GEMINI_MODELS = [
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
]

# Historial reciente de mensajes procesados para auditoría y visualización en el Portal
_MAX_HISTORY_ITEMS = 50
_whatsapp_activity_log: list[dict[str, Any]] = []


WHATSAPP_PROMPT_TEMPLATE = """Eres el Asistente Inteligente del grupo de WhatsApp "Chismoso", integrado por Fidel, su novia Lau y Martha.
Tu labor es escuchar/analizar el mensaje (audio o texto) con máxima atención, entender la intención de quien habla y clasificarla para ejecutar la acción correspondiente.

CONTEXTO TEMPORAL:
- Fecha de hoy: {today_date} ({day_name})

INTEGRANTES Y CONTACTOS:
- "fidel": Fidel Moreno (usuario principal, dueño del Kindle Scribe) - Correo: fidelm02@gmail.com
- "lau": Lau / Laura / Lalis (novia de Fidel) - Correo: lalisgallego@hotmail.com
- "martha": Martha Elena Gallego (mamá de Lau / familiar) - Correo: marthaelena.gallego@mamh.gouv.qc.ca


TAXONOMÍA DE ACCIONES (Elige con máxima precisión):

1. "calendar_event" (Evento / Cita / Tarea por hora en Google Calendar):
   - CUÁNDO USAR: Cuando se mencione una HORA o compromiso temporal específico (ej: "cita con el dentista el viernes a las 4pm", "reunión mañana a las 10:00", "vuelo a las 6:30", "compromiso a las 15:00").
   - "target": "fidel", "lau", o "martha".
   - "requester": Quién solicitó el evento ("fidel", "lau", o "martha").
     * Si Laura lo pidió -> se guardará en su calendario "LauraG"
     * Si Martha lo pidió -> se guardará en su calendario "MarthaG"
     * Si Fidel lo pidió -> se guardará en el calendario normal default ("primary")
   - "title": Título claro y conciso del evento.
   - "description": Notas o detalles del evento.
   - "event_date": Fecha en formato YYYY-MM-DD.
   - "start_time": Hora de inicio en formato HH:MM (24 horas, ej. "16:00" o "10:30"). Si no indican hora específica, usar "09:00".
   - "duration_minutes": Duración estimada en minutos (por defecto 60).
   - "attendees": Lista de nombres de los involucrados a invitar (ej. ["Laura", "Fidel", "Martha"]).

2. "kindle_task" (Tarea EXCLUSIVA para la pantalla E-ink del Kindle Scribe de Fidel):
   - CUÁNDO USAR: ÚNICA Y EXCLUSIVAMENTE si el usuario dice de forma explícita palabras como "tarea para el kindle", "para el kindle", "tarea de kindle", o "agrega al kindle".
   - Si NO dicen esas palabras exactas, NO uses esta acción (usa "reminder").
   - "target": "fidel" (por defecto) o "lau" / "martha".
   - "title": Título conciso de la tarea.
   - "description": Detalles o notas.
   - "priority": "high", "normal", o "low".
   - "due_date": Fecha YYYY-MM-DD o null.

3. "reminder" (Recordatorio / Compromiso para el Cron de las 6:00 AM en WhatsApp):
   - CUÁNDO USAR: Es la acción POR DEFECTO para cualquier tarea, encargo, trámite, compra o cosa por hacer en una fecha que NO tenga hora fija ni diga explícitamente "para el kindle" (ej: "recuérdame comprar leche mañana", "el viernes hay que renovar el pasaporte", "recuérdale a Lau llamar al doctor", "tenemos que pagar la renta el 1").
   - REGLA: Los recordatorios NO van a la pantalla del Kindle. Se almacenan para que el Cron de las 6:00 AM envíe un mensaje al grupo de WhatsApp etiquetando con @ a la persona solicitante y destinataria.
   - "target": "fidel", "lau", o "martha".
   - "requester": Nombre de quien habla ("fidel", "lau", "martha").
   - "reminder_date": Fecha calculada en formato YYYY-MM-DD para la cual se debe recordar (ej. si dicen "mañana", "el viernes", "en 3 días"). Si no especifican fecha, calcular para mañana.
   - "title": Descripción clara y accionable de lo que hay que recordar.

4. "vault_doc" (Documento / Guía / Resumen / Reporte / Nota para la Base de Conocimiento en Obsidian y WhatsApp):
   - CUÁNDO USAR: Cuando pidan crear, redactar o guardar un documento, reporte, guía, resumen, trámite, notas clínicas de pacientes (de Laura), trámites de Quebec/gobierno (de Martha), artículos o información extensa.
   - Si dicen expresamente "en txt", "archivo de texto", "en texto plano" -> "format": "txt"
   - Si dicen expresamente "para el kindle", "lectura kindle", "para leer en el kindle" -> "for_kindle": true
   - Por defecto para cualquier otro documento -> "format": "pdf", "for_kindle": false (se compilará a PDF y se enviará como adjunto al chat de WhatsApp).
   - "target": "fidel", "lau", o "martha".
   - "category": Subcarpeta ("Pacientes", "Tramites", "Notas", "Documentos", "Lecturas_Kindle", "General").
   - "title": Título claro y profesional del documento.
   - "markdown_content": Contenido completo y detallado en Markdown bien formateado (con títulos ##, viñetas, tablas estructuradas si aplica, negritas) listo para Obsidian y para ser compilado en PDF/TXT.
   - "tags": Lista de 2-4 etiquetas en minúsculas (ej. ["salud", "pacientes"], ["tramites", "quebec"]).
   - "format": "pdf" | "txt"
   - "for_kindle": boolean (true ÚNICAMENTE si dijeron expresamente "para el kindle" o "lectura de kindle")

5. "email" (Redactar y Enviar Correo Electrónico vía Gmail SMTP):
   - CUÁNDO USAR: Cuando pidan explícitamente enviar, mandar o redactar un correo o email (ej: "mándale un correo a Lau...", "envía un email a Martha con...", "manda correo a Fidel...").
   - "recipient_name": "Laura", "Fidel", "Martha" u otro.
   - "recipient_email": Correo destino ("lalisgallego@hotmail.com", "fidelm02@gmail.com", "marthaelena.gallego@mamh.gouv.qc.ca", o el indicado).
   - "subject": Asunto claro.
   - "body": Redacción completa, educada y estructurada.

6. "health_log" (Salud & Fitness):
   - CUÁNDO USAR: Pesaje ("pesé 92.5 kg") o hábitos ("gym", "walk", "water").
   - "target": "fidel" o "lau".
   - "metric_type": "weight" o "habit".
   - "weight_value": número flotante o null.
   - "habit_id": "gym", "walk", o "water".

7. "chat_response" (Respuesta / Consulta general o Pregunta sobre la Base de Conocimiento):
   - CUÁNDO USAR: Preguntas directas, cálculos, saludos o dudas sobre información guardada previamente.
   - "reply_text": Respuesta clara, empática y precisa en español.

DEBES RESPONDER EXCLUSIVAMENTE CON UN OBJETO JSON VÁLIDO CON ESTA ESTRUCTURA EXACTA (sin backticks extraños):
{{
  "action": "calendar_event" | "kindle_task" | "reminder" | "vault_doc" | "email" | "health_log" | "chat_response",
  "target": "fidel" | "lau" | "martha",
  "transcription": "Transcripción textual de lo que se dijo en el audio o mensaje recibido",
  "summary": "Resumen en una frase de la acción comprendida",
  "calendar_event": {{
    "title": "Cita con el dentista",
    "description": "Limpieza dental",
    "event_date": "YYYY-MM-DD",
    "start_time": "16:00",
    "duration_minutes": 60,
    "attendees": ["Laura", "Fidel"],
    "requester": "lau"
  }},
  "kindle_task": {{
    "title": "Título de la tarea para el Kindle",
    "description": "Detalles o notas",
    "priority": "normal",
    "due_date": "YYYY-MM-DD"
  }},
  "reminder": {{
    "title": "Renovar pasaporte en el consulado",
    "reminder_date": "YYYY-MM-DD",
    "target": "fidel",
    "requester": "lau"
  }},
  "vault_doc": {{
    "title": "Título del documento",
    "category": "Documentos",
    "markdown_content": "# Título\\n\\nContenido...",
    "tags": ["pacientes", "salud"],
    "format": "pdf",
    "for_kindle": false
  }},
  "email": {{
    "recipient_name": "Martha",
    "recipient_email": "marthaelena.gallego@mamh.gouv.qc.ca",
    "subject": "Asunto",
    "body": "Cuerpo..."
  }},
  "health_log": {{
    "metric_type": "weight",
    "weight_value": 92.5,
    "habit_id": "gym"
  }},
  "chat_response": {{
    "reply_text": "Texto de respuesta para enviar al grupo"
  }}
}}
"""


def _clean_json_response(raw_text: str) -> dict[str, Any]:
    """Limpia etiquetas markdown y parsea JSON."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()
    return json.loads(cleaned)


def _get_day_name(d: date) -> str:
    """Devuelve el nombre del día en español."""
    dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    return dias[d.weekday()]


def _send_whatsapp_email(
    to_email: str, subject: str, body: str, sender_name: str
) -> tuple[bool, str]:
    """Envía un correo electrónico vía Gmail SMTP con las credenciales de constants.py."""
    from email.message import EmailMessage
    import smtplib
    from app.constants import GMAIL_SENDER_EMAIL, GMAIL_APP_PASSWORD

    sender = GMAIL_SENDER_EMAIL or "fidelm02@gmail.com"
    app_pwd = GMAIL_APP_PASSWORD or ""
    if not app_pwd:
        return False, "GMAIL_APP_PASSWORD no está configurado en app/constants.py"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{sender_name} (vía Kindle Tasks) <{sender}>"
    msg["To"] = to_email
    footer = (
        f"\n\n---\n"
        f"✉️ Mensaje redactado y despachado automáticamente desde el grupo de WhatsApp 'Chismoso' "
        f"por solicitud de {sender_name}."
    )
    msg.set_content(body + footer)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=25) as s:
            s.login(sender, app_pwd)
            s.send_message(msg)
        return True, "Enviado exitosamente"
    except Exception as exc:
        logger.error("Error al enviar correo desde WhatsApp: %s", exc)
        return False, str(exc)


def _send_calendar_invite(
    to_emails: list[str],
    organizer_email: str,
    organizer_name: str,
    title: str,
    description: str,
    start_dt: datetime,
    end_dt: datetime,
) -> tuple[bool, str]:
    """Envía una invitación formal de calendario (.ics) vía Gmail SMTP.

    Google Calendar y Outlook/Hotmail detectan el método REQUEST y
    agregan el evento automáticamente a los calendarios de los destinatarios.
    """
    from email.message import EmailMessage
    import smtplib
    import uuid
    from app.constants import GMAIL_SENDER_EMAIL, GMAIL_APP_PASSWORD

    sender = GMAIL_SENDER_EMAIL or "fidelm02@gmail.com"
    app_pwd = GMAIL_APP_PASSWORD or ""
    if not app_pwd:
        return False, "GMAIL_APP_PASSWORD no configurado en app/constants.py"

    clean_to = [e.strip() for e in to_emails if e and "@" in e]
    if not clean_to:
        return False, "No hay correos de destino válidos"

    uid = f"{uuid.uuid4()}@kindletasks.local"
    dtstamp = datetime.now().strftime("%Y%m%dT%H%M%SZ")
    dtstart = start_dt.strftime("%Y%m%dT%H%M%S")
    dtend = end_dt.strftime("%Y%m%dT%H%M%S")

    attendee_lines = []
    for em in clean_to:
        if "fidel" in em.lower():
            name = "Fidel Moreno"
        elif any(k in em.lower() for k in ("martha", "marta", "mamh")):
            name = "Martha Elena Gallego"
        else:
            name = "Laura (Lalis)"
        attendee_lines.append(
            f"ATTENDEE;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE;CN={name}:mailto:{em}"
        )
    attendees_str = "\r\n".join(attendee_lines)

    ics_content = (
        "BEGIN:VCALENDAR\r\n"
        "PRODID:-//Kindle Tasks Pro//ES\r\n"
        "VERSION:2.0\r\n"
        "METHOD:REQUEST\r\n"
        "CALSCALE:GREGORIAN\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"DTSTAMP:{dtstamp}\r\n"
        f"ORGANIZER;CN={organizer_name}:mailto:{organizer_email}\r\n"
        f"{attendees_str}\r\n"
        f"DTSTART:{dtstart}\r\n"
        f"DTEND:{dtend}\r\n"
        f"SUMMARY:{title}\r\n"
        f"DESCRIPTION:{description}\r\n"
        "STATUS:CONFIRMED\r\n"
        "SEQUENCE:0\r\n"
        "BEGIN:VALARM\r\n"
        "TRIGGER:-PT15M\r\n"
        "ACTION:DISPLAY\r\n"
        "DESCRIPTION:Recordatorio de Evento\r\n"
        "END:VALARM\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )

    msg = EmailMessage()
    msg["Subject"] = f"Invitación: {title}"
    msg["From"] = f"{organizer_name} <{sender}>"
    msg["To"] = ", ".join(clean_to)
    msg.set_content(
        f"Has recibido una invitación de calendario para:\n\n"
        f"📌 Evento: {title}\n"
        f"🕒 Horario: {start_dt.strftime('%Y-%m-%d %H:%M')} - {end_dt.strftime('%H:%M')}\n"
        f"📝 Detalles: {description}\n\n"
        f"Se adjunta la tarjeta iCalendar (.ics) para sincronización automática en Google Calendar y Hotmail/Outlook.\n\n"
        f"---\n"
        f"Enviado automáticamente por el Asistente Chismoso (Kindle Tasks Pro)."
    )

    msg.add_attachment(
        ics_content.encode("utf-8"),
        maintype="text",
        subtype="calendar",
        filename="invite.ics",
        params={"method": "REQUEST", "name": "invite.ics"},
    )

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=25) as s:
            s.login(sender, app_pwd)
            s.send_message(msg)
        return True, "Invitación enviada exitosamente"
    except Exception as exc:
        logger.error("Error al enviar invitación de calendario: %s", exc)
        return False, str(exc)



def process_whatsapp_message(
    sender_name: str,
    sender_phone: str,
    group_name: str,
    message_type: str = "text",
    text_content: str | None = None,
    audio_base64: str | None = None,
    audio_mimetype: str = "audio/ogg",
) -> dict[str, Any]:
    """Procesa un mensaje recibido en el grupo 'Chismoso' de WhatsApp.

    Args:
        sender_name: Nombre visible del remitente en WhatsApp.
        sender_phone: Número de teléfono o identificador de WhatsApp.
        group_name: Nombre del grupo donde se originó el mensaje.
        message_type: 'audio' o 'text'.
        text_content: Texto del mensaje si message_type == 'text'.
        audio_base64: Cadena base64 del audio si message_type == 'audio'.
        audio_mimetype: Tipo MIME del audio (audio/ogg, audio/mp4, audio/webm, etc.).

    Returns:
        dict[str, Any]: Resultado con acción ejecutada y respuesta a enviar al grupo.
    """
    now = datetime.now()
    today = date.today()
    log_id = str(uuid.uuid4())[:8]

    # Validar que tengamos contenido
    if message_type == "text" and not (text_content and text_content.strip()):
        return {"status": "error", "message": "Mensaje de texto vacío."}
    if message_type == "audio" and not audio_base64:
        return {"status": "error", "message": "Audio base64 no proporcionado."}

    prompt = WHATSAPP_PROMPT_TEMPLATE.format(
        today_date=today.isoformat(),
        day_name=_get_day_name(today),
    )

    # Preparar llamada a Gemini
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_TOKEN)
    except Exception as exc:
        logger.error("Error al inicializar cliente Google GenAI: %s", exc)
        return {
            "status": "error",
            "reply": "⚠️ Error interno: No se pudo contactar con el servicio de IA.",
            "detail": str(exc),
        }

    # Armar los contenidos (multimodal si es audio)
    contents: list[Any] = []
    if message_type == "audio" and audio_base64:
        try:
            audio_bytes = base64.b64decode(audio_base64)
            # Asegurar tipo mime limpio
            clean_mime = audio_mimetype.split(";")[0].strip() or "audio/ogg"
            contents.append(
                types.Part.from_bytes(data=audio_bytes, mime_type=clean_mime)
            )
            contents.append(
                "Por favor analiza este audio del grupo 'Chismoso' de WhatsApp y responde estrictamente con el JSON de acción indicado:"
            )
        except Exception as b64_err:
            logger.error("Error al decodificar audio base64: %s", b64_err)
            return {
                "status": "error",
                "reply": "⚠️ No se pudo procesar el archivo de audio recibido.",
            }
    else:
        contents.append(
            f"Mensaje de texto de {sender_name}: '{text_content}'\nAnaliza la intención y responde con el JSON:"
        )

    contents.append(prompt)

    # Invocar Gemini con reintentos de modelo
    parsed_ai: dict[str, Any] | None = None
    ai_raw = ""
    for model_name in GEMINI_MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
            )
            ai_raw = response.text or ""
            parsed_ai = _clean_json_response(ai_raw)
            break
        except Exception as api_err:
            logger.warning("Fallo con modelo %s: %s", model_name, api_err)
            continue

    if not parsed_ai:
        return {
            "status": "error",
            "reply": "⚠️ No pude interpretar la nota de voz. Por favor intenta de nuevo con más claridad.",
            "raw": ai_raw,
        }

    action = parsed_ai.get("action", "chat_response")
    target = (parsed_ai.get("target") or "fidel").lower()
    if target not in ("fidel", "lau", "martha"):
        target = "fidel"

    target_display = "Fidel" if target == "fidel" else ("Lau" if target == "lau" else "Martha")
    transcription = parsed_ai.get("transcription") or (text_content or "")
    summary = parsed_ai.get("summary") or "Procesado por Asistente Chismoso"
    reply_text = ""
    attachment_data: dict[str, Any] | None = None

    # =========================================================================
    # EJECUTOR 1: ENVIAR CORREO ELECTRÓNICO (GMAIL SMTP)
    # =========================================================================
    if action == "email":
        email_info = parsed_ai.get("email") or {}
        recip_name = email_info.get("recipient_name") or "Destinatario"
        recip_email = email_info.get("recipient_email") or ""
        subject = email_info.get("subject") or "Mensaje desde WhatsApp (Chismoso)"
        body = email_info.get("body") or transcription

        # Resolución inteligente de contactos conocidos si no viene correo exacto
        recip_name_lower = recip_name.lower()
        if any(k in recip_name_lower for k in ("martha", "marta", "elena", "86313")):
            recip_email = "marthaelena.gallego@mamh.gouv.qc.ca"
            recip_name = "Martha Elena Gallego"
        elif "lau" in recip_name_lower or "lalis" in recip_name_lower:
            recip_email = "lalisgallego@hotmail.com"
            recip_name = "Laura (Lalis)"
        elif "fidel" in recip_name_lower:
            recip_email = "fidelm02@gmail.com"
            recip_name = "Fidel"
        elif not recip_email or "@" not in recip_email:
            recip_email = "lalisgallego@hotmail.com"
            recip_name = "Laura (Lalis)"

        ok, err_msg = _send_whatsapp_email(recip_email, subject, body, sender_name)
        if ok:
            reply_text = (
                f"✉️ *Correo enviado exitosamente a {recip_name}* (`{recip_email}`)\n\n"
                f"📌 *Asunto:* {subject}\n"
                f"📝 *Mensaje:* {body}"
            )
        else:
            reply_text = f"⚠️ Error al enviar correo a {recip_name} ({recip_email}): {err_msg}"

    # =========================================================================
    # EJECUTOR 2: AGENDAR EN GOOGLE CALENDAR (TAREAS CON HORA ESPECÍFICA)
    # =========================================================================
    elif action == "calendar_event":
        cal_info = parsed_ai.get("calendar_event") or {}
        title = cal_info.get("title") or transcription[:60]
        desc = cal_info.get("description") or f"Agendado desde WhatsApp por {sender_name}"
        event_date = cal_info.get("event_date") or today.isoformat()
        start_time = cal_info.get("start_time") or "09:00"
        duration = int(cal_info.get("duration_minutes") or 60)

        # Determinar participantes de la invitación
        invite_emails = ["fidelm02@gmail.com"]
        attendees_labels = ["Fidel (fidelm02@gmail.com)"]

        trans_low = transcription.lower()
        attendees_text = str(cal_info.get("attendees", "")).lower()

        # Invitar a Lau
        if "lau" in trans_low or "lalis" in trans_low or target == "lau" or "laura" in attendees_text or "lau" in attendees_text:
            if "lalisgallego@hotmail.com" not in invite_emails:
                invite_emails.append("lalisgallego@hotmail.com")
                attendees_labels.append("Laura (lalisgallego@hotmail.com)")

        # Invitar a Martha
        if any(k in trans_low for k in ("martha", "marta", "elena")) or target == "martha" or any(k in attendees_text for k in ("martha", "marta")):
            if "marthaelena.gallego@mamh.gouv.qc.ca" not in invite_emails:
                invite_emails.append("marthaelena.gallego@mamh.gouv.qc.ca")
                attendees_labels.append("Martha (marthaelena.gallego@mamh.gouv.qc.ca)")

        # Generar fechas en formato ISO para URL de Google Calendar
        try:
            dt_start = datetime.strptime(f"{event_date} {start_time}", "%Y-%m-%d %H:%M")
            dt_end = dt_start + timedelta(minutes=duration)
            dates_param = f"{dt_start.strftime('%Y%m%dT%H%M%S')}/{dt_end.strftime('%Y%m%dT%H%M%S')}"
        except Exception:
            dt_start = datetime.now()
            dt_end = dt_start + timedelta(hours=1)
            dates_param = f"{event_date.replace('-', '')}/{event_date.replace('-', '')}"

        # 1. Inserción DIRECTA vía Google Calendar API
        from portal.services import google_calendar_service

        # Determinar a qué calendario dirigir el evento:
        # Laura -> Calendario "LauraG"
        # Martha -> Calendario "MarthaG"
        # Fidel -> Calendario default ("primary")
        req_from_ai = str(cal_info.get("requester") or "").lower()
        sender_lower = (sender_name or "").lower()

        if (
            any(k in sender_lower for k in ("martha", "marta", "elena", "15149986313"))
            or req_from_ai == "martha"
            or "marthag" in trans_low
            or "calendario de martha" in trans_low
        ):
            requester_person = "martha"
            cal_owner_label = "Martha (MarthaG)"
        elif (
            any(k in sender_lower for k in ("lau", "laura", "lalis", "14389955725"))
            or req_from_ai in ("lau", "laura")
            or "laurag" in trans_low
            or "calendario de laura" in trans_low
        ):
            requester_person = "lau"
            cal_owner_label = "Laura (LauraG)"
        else:
            requester_person = "fidel"
            cal_owner_label = "Fidel (Principal)"

        calendar_id, cal_name = google_calendar_service.resolve_calendar_for_requester(requester_person)

        api_success = False
        api_link = None
        if google_calendar_service.is_connected():
            api_ok, api_msg, api_link = google_calendar_service.create_calendar_event(
                title=title,
                description=desc,
                start_dt=dt_start,
                end_dt=dt_end,
                attendee_emails=invite_emails,
                calendar_id=calendar_id,
            )
            api_success = api_ok
            if not api_ok:
                logger.warning("Fallo al insertar en Google Calendar API (%s): %s", calendar_id, api_msg)

        # 2. Si no está vinculado por API o falló, enviar invitación formal iCalendar (.ics) por SMTP
        ics_ok = False
        ics_err = ""
        if not api_success:
            ics_ok, ics_err = _send_calendar_invite(
                to_emails=invite_emails,
                organizer_email="fidelm02@gmail.com",
                organizer_name=sender_name,
                title=title,
                description=desc,
                start_dt=dt_start,
                end_dt=dt_end,
            )

        # 3. Enlace web de Google Calendar
        gcal_params = {
            "action": "TEMPLATE",
            "text": title,
            "details": f"{desc}\n\nAgendado desde el grupo Chismoso por {sender_name}.",
            "dates": dates_param,
            "add": ",".join(invite_emails),
        }
        if calendar_id and calendar_id != "primary":
            gcal_params["src"] = calendar_id
        gcal_link = api_link or f"https://calendar.google.com/calendar/render?{urllib.parse.urlencode(gcal_params)}"

        if api_success:
            reply_text = (
                f"📅 *Evento agendado en Google Calendar ({cal_name})*:\n"
                f"📌 *{title}*\n"
                f"📆 *Calendario:* `{cal_name}` ({cal_owner_label})\n"
                f"🕒 *Fecha/Hora:* {event_date} a las {start_time} ({duration} min)\n"
                f"👥 *Invitados:* {', '.join(attendees_labels)}\n\n"
                f"✓ *Insertado en `{cal_name}` y Google despachó invitaciones oficiales.*\n\n"
                f"🔗 *Ver en Google Calendar:*\n{gcal_link}"
            )
        else:
            inv_notice = "✓ *Invitación formal (.ics) enviada a:* " + ", ".join(attendees_labels) if ics_ok else f"⚠️ Error enviando tarjeta .ics: {ics_err}"
            reply_text = (
                f"📅 *Evento agendado para {cal_name}*:\n"
                f"📌 *{title}*\n"
                f"📆 *Calendario:* `{cal_name}` ({cal_owner_label})\n"
                f"🕒 *Fecha/Hora:* {event_date} a las {start_time} ({duration} min)\n"
                f"👥 *Invitados:* {', '.join(attendees_labels)}\n\n"
                f"{inv_notice}\n"
                f"*(Google Calendar y Hotmail añaden el evento automáticamente al recibir el correo)*\n\n"
                f"🔗 *Abrir en Google Calendar:*\n{gcal_link}"
            )

    # =========================================================================
    # EJECUTOR 3: TAREA EXCLUSIVA PARA EL KINDLE SCRIBE
    # =========================================================================
    elif action in ("kindle_task", "task") and any(k in transcription.lower() for k in ("kindle", "scribe")):
        task_info = parsed_ai.get("kindle_task") or parsed_ai.get("task") or {}
        title = task_info.get("title") or transcription[:60]
        desc = task_info.get("description") or f"Creada desde WhatsApp por {sender_name}"
        priority = task_info.get("priority") or "normal"
        due_date = task_info.get("due_date")

        storage.create_task(
            title=title,
            description=desc,
            priority=priority,
            target_date=due_date,
            scope=target,
        )

        due_badge = f" (📅 Para: {due_date})" if due_date else ""
        prio_badge = " 🔥 Alta" if priority == "high" else ""
        reply_text = f"✓ Tarea agregada al *Kindle Scribe* para *{target_display}*{prio_badge}: \"{title}\"{due_badge}"

    # =========================================================================
    # EJECUTOR 4: RECORDATORIO / COMPROMISO (CRON DE LAS 6:00 AM)
    # =========================================================================
    elif action in ("reminder", "task"):
        rem_info = parsed_ai.get("reminder") or parsed_ai.get("task") or {}
        title = rem_info.get("title") or transcription[:80]
        due_date = rem_info.get("reminder_date") or rem_info.get("due_date")
        if not due_date:
            due_date = (today + timedelta(days=1)).isoformat()

        vault_service.add_reminder(
            requester=sender_name,
            target=target,
            reminder_date=due_date,
            text=title,
            requester_phone=sender_phone,
        )

        reply_text = (
            f"⏰ *Recordatorio programado para {target_display}*:\n"
            f"📌 \"{title}\"\n"
            f"📅 *Fecha:* {due_date}\n\n"
            f"*(Te avisaré en este grupo el día anterior y a las 6:00 AM el mero día)*"
        )

    # =========================================================================
    # EJECUTOR 5: GENERAR DOCUMENTO / BASE DE CONOCIMIENTO (OBSIDIAN VAULT)
    # =========================================================================
    elif action in ("vault_doc", "kindle_doc"):
        doc_info = parsed_ai.get("vault_doc") or parsed_ai.get("kindle_doc") or {}
        doc_title = doc_info.get("title") or "Documento de WhatsApp"
        category = doc_info.get("category") or "Documentos"
        md_body = doc_info.get("markdown_content") or f"# {doc_title}\n\n{transcription}"
        tags = doc_info.get("tags") or [category.lower(), "chismoso"]
        doc_format = str(doc_info.get("format") or "").lower()

        # Validación explícita de lectura para Kindle
        is_explicit_kindle = bool(doc_info.get("for_kindle")) or any(
            k in transcription.lower()
            for k in (
                "para el kindle",
                "lectura kindle",
                "lectura para kindle",
                "en el kindle",
                "para leer en el kindle",
                "para mi kindle",
                "para tu kindle",
            )
        )

        vault_category = "Lecturas_Kindle" if (is_explicit_kindle and category == "Documentos") else category
        saved_path = vault_service.save_vault_document(
            author=target,
            category=vault_category,
            title=doc_title,
            markdown_content=md_body,
            tags=tags,
        )

        # Caso A: Si es lectura explícita para Kindle Scribe
        if is_explicit_kindle:
            if target == "fidel":
                try:
                    k_dir = reader_service._ensure_docs_dir("fidel") / vault_category
                    k_dir.mkdir(parents=True, exist_ok=True)
                    with open(k_dir / saved_path.name, "w", encoding="utf-8") as kf:
                        kf.write(md_body)
                except Exception as k_err:
                    logger.warning("No se pudo copiar a docs/ del Kindle: %s", k_err)

            tags_str = ", ".join(f"#{t}" for t in tags)
            reply_text = (
                f"📖 *Lectura guardada para Kindle Scribe y en el Vault Obsidian*:\n"
                f"👤 *Lector:* {target_display}\n"
                f"📁 *Carpeta:* `{target_display}/{vault_category}/`\n"
                f"📄 *{doc_title}*\n"
                f"🏷️ *Tags:* {tags_str}\n\n"
                f"*(Disponible para leer en formato Markdown en tu lector Kindle Scribe)*"
            )
        else:
            # Caso B: Documento general -> Compilar en PDF (o TXT si se solicitó) y adjuntar en el chat
            is_txt = "txt" in doc_format or any(
                k in transcription.lower()
                for k in ("en txt", "formato txt", "texto plano", "archivo txt", "archivo de texto")
            )

            try:
                if is_txt:
                    desired_ext = "txt"
                    mimetype = "text/plain"
                    export_file = saved_path.with_suffix(".txt")
                    pdf_service.generate_txt(
                        title=doc_title,
                        content=md_body,
                        output_path=export_file,
                        author=target_display,
                        category=vault_category,
                        tags=tags,
                    )
                else:
                    desired_ext = "pdf"
                    mimetype = "application/pdf"
                    export_file = saved_path.with_suffix(".pdf")
                    pdf_service.generate_pdf(
                        title=doc_title,
                        markdown_content=md_body,
                        output_path=export_file,
                        author=target_display,
                        category=vault_category,
                        tags=tags,
                    )

                attachment_data = {
                    "file_path": str(export_file.resolve()),
                    "file_name": export_file.name,
                    "mimetype": mimetype,
                    "caption": f"📄 {doc_title} ({desired_ext.upper()})",
                }

                tags_str = ", ".join(f"#{t}" for t in tags)
                reply_text = (
                    f"📄 *Documento {desired_ext.upper()} generado para {target_display}*:\n"
                    f"📌 *{doc_title}*\n"
                    f"📁 *Guardado en Vault Obsidian:* `{target_display}/{vault_category}/`\n"
                    f"🏷️ *Tags:* {tags_str}\n\n"
                    f"📎 *Adjuntando archivo {desired_ext.upper()} en este chat...*"
                )
            except Exception as gen_err:
                logger.error("Error al generar archivo %s: %s", "TXT" if is_txt else "PDF", gen_err)
                tags_str = ", ".join(f"#{t}" for t in tags)
                reply_text = (
                    f"📖 *Documento guardado en la Base de Conocimiento (Vault Obsidian)*:\n"
                    f"👤 *Autor:* {target_display}\n"
                    f"📁 *Carpeta:* `{target_display}/{vault_category}/`\n"
                    f"📄 *{doc_title}*\n"
                    f"🏷️ *Tags:* {tags_str}\n\n"
                    f"⚠️ (No se pudo compilar el archivo adjunto: {gen_err})"
                )

    # =========================================================================
    # EJECUTOR 6: REGISTRO DE SALUD / PESO / HÁBITOS
    # =========================================================================
    elif action == "health_log":
        health_info = parsed_ai.get("health_log") or {}
        metric = health_info.get("metric_type", "weight")

        if metric == "weight" and health_info.get("weight_value"):
            w_val = float(health_info["weight_value"])
            notes = health_info.get("notes") or f"Registro vía WhatsApp ({sender_name})"
            health_service.log_weight_entry(profile_id=target, weight=w_val, notes=notes)
            reply_text = f"⚖️ Peso registrado para *{target_display}*: *{w_val:.1f} kg* ({notes})"
        elif metric == "habit":
            habit_id = health_info.get("habit_id", "gym")
            health_service.toggle_habit(target, habit_id, today.isoformat())
            habit_names = {"gym": "🏋️‍♂️ Gimnasio", "walk": "🚶 Caminata 1h", "water": "💧 3L de Agua"}
            h_name = habit_names.get(habit_id, habit_id.capitalize())
            reply_text = f"💪 Hábito completado para *{target_display}*: *{h_name}* ¡Gran trabajo!"
        else:
            reply_text = f"✓ Dato de salud recibido y guardado para *{target_display}*."

    # =========================================================================
    # EJECUTOR 7: RESPUESTA DE CHAT DIRECTA O CONSULTA DE CONOCIMIENTO
    # =========================================================================
    else:
        chat_info = parsed_ai.get("chat_response") or {}
        ai_reply = chat_info.get("reply_text") or summary

        # Si el usuario pregunta por información previa, consultamos el Vault Obsidian
        search_hits = vault_service.search_vault(transcription, author=target, max_results=2)
        if search_hits and any(q in transcription.lower() for q in ("qué", "que", "cuál", "cual", "dónde", "donde", "recuerdas", "teníamos", "tenemos", "paciente", "correo", "trámite", "tramite")):
            citations = "\n".join([f"• [[{h['rel_path']}|{h['title']}]]: {h['snippet'][:110]}..." for h in search_hits])
            reply_text = f"{ai_reply}\n\n📚 *Encontrado en tu Vault Obsidian:*\n{citations}"
        else:
            reply_text = ai_reply

    # Guardar en registro de actividad en memoria
    activity_entry = {
        "id": log_id,
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "sender": sender_name,
        "message_type": message_type,
        "transcription": transcription,
        "action": action,
        "target": target,
        "summary": summary,
        "reply": reply_text,
        "attachment": attachment_data,
    }
    _whatsapp_activity_log.insert(0, activity_entry)
    if len(_whatsapp_activity_log) > _MAX_HISTORY_ITEMS:
        _whatsapp_activity_log.pop()

    resp_payload = {
        "status": "success",
        "action": action,
        "target": target,
        "transcription": transcription,
        "summary": summary,
        "reply": reply_text,
    }
    if attachment_data:
        resp_payload["attachment"] = attachment_data
    return resp_payload


def get_recent_activity() -> list[dict[str, Any]]:
    """Retorna el historial reciente de mensajes de WhatsApp procesados."""
    return list(_whatsapp_activity_log)
