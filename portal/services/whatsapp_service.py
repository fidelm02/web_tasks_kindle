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
from app.constants import GEMINI_TOKEN
from app.services import reader_service
from portal.services import health_service

logger = logging.getLogger(__name__)

# Modelos candidatos en orden de preferencia
GEMINI_MODELS = [
    "gemini-3.6-flash",
    "gemini-flash-latest",
    "gemini-3.1-flash-lite",
]

# Historial reciente de mensajes procesados para auditoría y visualización en el Portal
_MAX_HISTORY_ITEMS = 50
_whatsapp_activity_log: list[dict[str, Any]] = []


WHATSAPP_PROMPT_TEMPLATE = """Eres el Asistente Inteligente del grupo de WhatsApp "Chismoso", integrado por Fidel y su novia Lau.
Tu labor es escuchar/analizar el mensaje (audio o texto) con máxima atención, entender la intención de quien habla y clasificarla para ejecutar la acción correspondiente en el sistema Kindle Tasks Pro.

CONTEXTO TEMPORAL:
- Fecha de hoy: {today_date} ({day_name})

INTEGRANTES Y CONTACTOS:
- "fidel": Fidel Moreno (usuario principal) - Correo: fidelm02@gmail.com
- "lau": Lau / Laura / Lalis (novia de Fidel) - Correo: lalisgallego@hotmail.com

REGLAS DE INTERPRETACIÓN:
1. "email" (Redactar y Enviar Correo Electrónico):
   - Cuando se pida explícitamente enviar, mandar o redactar un correo o email (ej: "mándale un correo a Lau diciéndole...", "envía un email a Lalis con...", "manda un correo a fidel...").
   - "recipient_name": Nombre del destinatario ("Laura" o "Fidel" u otro).
   - "recipient_email": Correo destino. Si mencionan a Lau / Laura / Lalis usar "lalisgallego@hotmail.com"; si mencionan a Fidel usar "fidelm02@gmail.com"; o el correo explícito que indiquen.
   - "subject": Asunto claro y conciso del correo.
   - "body": Redacción completa del mensaje, estructurada, cordial y clara.

2. "calendar_event" (Agendar Evento / Cita en Google Calendar):
   - Cuando se mencione agendar una cita, reunión, compromiso con hora específica o bloqueo de tiempo (ej: "agenda cita con el dentista el viernes a las 4pm", "reunión mañana a las 10:00", "agenda evento e invita a Lau").
   - "target": "fidel" o "lau".
   - "title": Título del evento o cita.
   - "description": Detalles o notas del evento.
   - "event_date": Fecha en formato YYYY-MM-DD.
   - "start_time": Hora de inicio en formato HH:MM (24 horas, ej. "16:00" o "10:30"). Si no indican hora específica, usar "09:00".
   - "duration_minutes": Duración estimada en minutos (ej. 30, 60, etc., por defecto 60).
   - "invite_lau": true si se menciona invitar a Lau / Laura / Lalis o si el evento es para ambos.

3. "task" (Crear Tarea):
   - Cuando se mencione una tarea por hacer, comprar, recordar, pendiente, trámite o actividad (que no sea un evento con hora fija ni envío de correo).
   - Identificar para quién es: "target" debe ser "fidel" o "lau" (por defecto "fidel" salvo que se mencione o refiera a Lau).
   - "title": Título conciso y claro de la tarea.
   - "description": Detalles, especificaciones o notas mencionadas en el audio.
   - "priority": "high", "normal", o "low" (por defecto "normal", salvo que indiquen urgencia).
   - "due_date": Fecha calculada en formato YYYY-MM-DD si indican "mañana", "el viernes", "el sábado", "en 3 días", etc., o null si no se especifica.

4. "kindle_doc" (Documento / Lectura para Kindle):
   - Cuando indiquen "para el kindle", "lectura", "artículo", "guarda este resumen", "apunte de lectura", o compartan información extensa que quieran leer en su Kindle Scribe.
   - "target": "fidel" (se guarda en docs/) o "lau" (se guarda en docs_lau/).
   - "title": Título descriptivo del documento.
   - "markdown_content": Contenido completo en Markdown bien formateado (con títulos ##, viñetas, negritas) listo para leer en Kindle.

5. "health_log" (Salud & Fitness):
   - Cuando indiquen pesaje (ej: "pesé 92.5 kg", "mi peso hoy fue 93"), o hábitos ("ya fui al gym", "terminé mi caminata de 1 hora", "tomé mis 3 litros de agua").
   - "target": "fidel" o "lau".
   - "metric_type": "weight" o "habit".
   - Si es "weight": "weight_value" (número flotante, ej. 92.5), "notes": notas opcionales.
   - Si es "habit": "habit_id" ("gym", "walk", o "water").

6. "chat_response" (Respuesta / Consulta general):
   - Cuando hagan una pregunta, consulta de datos, cálculo rápido o saludo que requiera responderles directamente en el grupo.
   - "reply_text": Respuesta amigable, concisa y útil para el grupo.

DEBES RESPONDER EXCLUSIVAMENTE CON UN OBJETO JSON VÁLIDO CON ESTA ESTRUCTURA EXACTA (sin backticks extraños):
{{
  "action": "email" | "calendar_event" | "task" | "kindle_doc" | "health_log" | "chat_response",
  "target": "fidel" | "lau",
  "transcription": "Transcripción textual de lo que se dijo en el audio o mensaje recibido",
  "summary": "Resumen en una frase de la acción comprendida",
  "email": {{
    "recipient_name": "Laura",
    "recipient_email": "lalisgallego@hotmail.com",
    "subject": "Asunto del correo",
    "body": "Cuerpo del correo..."
  }},
  "calendar_event": {{
    "title": "Cita con el dentista",
    "description": "Limpieza dental",
    "event_date": "YYYY-MM-DD",
    "start_time": "16:00",
    "duration_minutes": 60,
    "invite_lau": true
  }},
  "task": {{
    "title": "Título de la tarea",
    "description": "Detalles o notas",
    "priority": "normal",
    "due_date": "YYYY-MM-DD"
  }},
  "kindle_doc": {{
    "title": "Título del documento",
    "category": "General",
    "markdown_content": "# Título\\n\\nContenido en Markdown..."
  }},
  "health_log": {{
    "metric_type": "weight",
    "weight_value": 92.5,
    "habit_id": "gym",
    "notes": "Pesaje matutino"
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
        name = "Fidel Moreno" if "fidel" in em else "Laura (Lalis)"
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
    if target not in ("fidel", "lau"):
        target = "fidel"

    transcription = parsed_ai.get("transcription") or (text_content or "")
    summary = parsed_ai.get("summary") or "Procesado por Asistente Chismoso"
    reply_text = ""

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
        if "lau" in recip_name_lower or "lalis" in recip_name_lower:
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
    # EJECUTOR 2: AGENDAR EN GOOGLE CALENDAR & KINDLE TASKS
    # =========================================================================
    elif action == "calendar_event":
        cal_info = parsed_ai.get("calendar_event") or {}
        title = cal_info.get("title") or transcription[:60]
        desc = cal_info.get("description") or f"Agendado desde WhatsApp por {sender_name}"
        event_date = cal_info.get("event_date") or today.isoformat()
        start_time = cal_info.get("start_time") or "09:00"
        duration = int(cal_info.get("duration_minutes") or 60)
        invite_lau = bool(cal_info.get("invite_lau"))

        # Determinar participantes de la invitación
        invite_emails = ["fidelm02@gmail.com"]
        attendees_labels = ["Fidel (fidelm02@gmail.com)"]

        # Si se pidió invitar a Lau o la transcripción la menciona
        trans_low = transcription.lower()
        if invite_lau or "lau" in trans_low or "lalis" in trans_low or target == "lau":
            invite_emails.append("lalisgallego@hotmail.com")
            attendees_labels.append("Laura (lalisgallego@hotmail.com)")

        # Generar fechas en formato ISO para URL de Google Calendar (YYYYMMDDTHHMMSS)
        try:
            dt_start = datetime.strptime(f"{event_date} {start_time}", "%Y-%m-%d %H:%M")
            dt_end = dt_start + timedelta(minutes=duration)
            dates_param = f"{dt_start.strftime('%Y%m%dT%H%M%S')}/{dt_end.strftime('%Y%m%dT%H%M%S')}"
        except Exception:
            dt_start = datetime.now()
            dt_end = dt_start + timedelta(hours=1)
            dates_param = f"{event_date.replace('-', '')}/{event_date.replace('-', '')}"

        # 1. Despachar invitación formal iCalendar (.ics) por correo vía SMTP
        ics_ok, ics_err = _send_calendar_invite(
            to_emails=invite_emails,
            organizer_email="fidelm02@gmail.com",
            organizer_name=sender_name,
            title=title,
            description=desc,
            start_dt=dt_start,
            end_dt=dt_end,
        )

        # 2. Generar enlace de respaldo 1-clic a Google Calendar con invitados precargados
        gcal_params = {
            "action": "TEMPLATE",
            "text": title,
            "details": f"{desc}\n\nAgendado desde el grupo Chismoso por {sender_name}.",
            "dates": dates_param,
            "add": ",".join(invite_emails),
        }
        gcal_link = f"https://calendar.google.com/calendar/render?{urllib.parse.urlencode(gcal_params)}"

        # 3. Guardar en base de datos de tareas con fecha para time-blocking en portal
        storage.create_task(
            title=f"📅 {title} ({start_time})",
            description=f"{desc}\n\nGoogle Calendar: {gcal_link}",
            priority="normal",
            target_date=event_date,
            scope=target,
        )

        target_display = "Fidel" if target == "fidel" else "Lau"
        inv_notice = "✓ *Invitación formal (.ics) enviada a:* " + ", ".join(attendees_labels) if ics_ok else f"⚠️ Error enviando tarjeta .ics: {ics_err}"

        reply_text = (
            f"📅 *Evento agendado para {target_display}*:\n"
            f"📌 *{title}*\n"
            f"🕒 *Fecha/Hora:* {event_date} a las {start_time} ({duration} min)\n"
            f"👥 *Invitados:* {', '.join(attendees_labels)}\n\n"
            f"{inv_notice}\n"
            f"*(Google Calendar y Hotmail detectan el correo y lo añaden al calendario)*\n\n"
            f"🔗 *Abrir directamente en Google Calendar:*\n{gcal_link}"
        )

    # =========================================================================
    # EJECUTOR 3: CREAR TAREA (KINDLE / PORTAL)
    # =========================================================================
    elif action == "task":
        task_info = parsed_ai.get("task") or {}
        title = task_info.get("title") or transcription[:60]
        desc = task_info.get("description") or f"Creada desde WhatsApp por {sender_name}"
        priority = task_info.get("priority") or "normal"
        due_date = task_info.get("due_date")

        created = storage.create_task(
            title=title,
            description=desc,
            priority=priority,
            target_date=due_date,
            scope=target,
        )

        target_display = "Fidel" if target == "fidel" else "Lau"
        due_badge = f" (📅 Para: {due_date})" if due_date else ""
        prio_badge = " 🔥 Alta" if priority == "high" else ""
        reply_text = f"✓ Tarea agregada a *{target_display}*{prio_badge}: \"{title}\"{due_badge}"

    # =========================================================================
    # EJECUTOR 2: GENERAR DOCUMENTO MARKDOWN PARA KINDLE
    # =========================================================================
    elif action == "kindle_doc":
        doc_info = parsed_ai.get("kindle_doc") or {}
        doc_title = doc_info.get("title") or "Apunte de WhatsApp"
        category = doc_info.get("category") or "General"
        md_body = doc_info.get("markdown_content") or f"# {doc_title}\n\n{transcription}"

        # Guardar en directorio docs correspondiente
        docs_target_dir = reader_service._ensure_docs_dir(target)
        cat_dir = docs_target_dir / category
        cat_dir.mkdir(parents=True, exist_ok=True)

        slug = re.sub(r"[^a-zA-Z0-9_-]", "_", doc_title.lower()).strip("_")[:40] or "nota"
        filename = f"{today.isoformat()}_{slug}.md"
        file_path = cat_dir / filename

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(md_body)

        target_display = "Fidel" if target == "fidel" else "Lau"
        reply_text = f"📖 Documento Kindle guardado para *{target_display}*:\n📄 *{doc_title}*\nCarpeta: `{category}/{filename}` (Listo para leer en Kindle)"

    # =========================================================================
    # EJECUTOR 3: REGISTRO DE SALUD / PESO / HÁBITOS
    # =========================================================================
    elif action == "health_log":
        health_info = parsed_ai.get("health_log") or {}
        metric = health_info.get("metric_type", "weight")
        target_display = "Fidel" if target == "fidel" else "Lau"

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
    # EJECUTOR 4: RESPUESTA DE CHAT DIRECTA
    # =========================================================================
    else:
        chat_info = parsed_ai.get("chat_response") or {}
        reply_text = chat_info.get("reply_text") or f"Asistente Chismoso: {summary}"

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
    }
    _whatsapp_activity_log.insert(0, activity_entry)
    if len(_whatsapp_activity_log) > _MAX_HISTORY_ITEMS:
        _whatsapp_activity_log.pop()

    return {
        "status": "success",
        "action": action,
        "target": target,
        "transcription": transcription,
        "summary": summary,
        "reply": reply_text,
    }


def get_recent_activity() -> list[dict[str, Any]]:
    """Retorna el historial reciente de mensajes de WhatsApp procesados."""
    return list(_whatsapp_activity_log)
