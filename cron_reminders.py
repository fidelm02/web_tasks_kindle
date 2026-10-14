#!/usr/bin/env python3
"""Script de Cron Diario (6:00 AM) para Notificación de Recordatorios en WhatsApp.

Revisa los recordatorios registrados en el Vault (reminders.json):
1. Si un recordatorio es para MAÑANA y no se ha notificado: Envía aviso anticipado.
2. Si un recordatorio es para HOY y no se ha notificado: Envía aviso del día.

Despacha los mensajes a través del microservidor push de WhatsApp Bridge (puerto 8095).

Uso manual o programado:
    python3 cron_reminders.py
    # Crontab diario a las 6:00 AM:
    # 0 6 * * * cd /home/fmoreno/Dev/web_tasks_kindle && .venv/bin/python cron_reminders.py >> reminders.log 2>&1
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
import logging
from pathlib import Path
import sys
import urllib.parse
import urllib.request
import urllib.error

# Asegurar path del repositorio
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from portal.services import vault_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("cron_reminders")

BRIDGE_PUSH_URL = "http://127.0.0.1:8095/api/send"


def send_whatsapp_message(text: str) -> bool:
    """Envía un mensaje al grupo Chismoso vía el microservidor push de WhatsApp Bridge."""
    payload = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        BRIDGE_PUSH_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            logger.info("Mensaje despachado a WhatsApp exitosamente: %s", data.get("id"))
            return True
    except urllib.error.URLError as exc:
        logger.error("No se pudo contactar con WhatsApp Bridge (puerto 8095): %s", exc)
        return False
    except Exception as exc:
        logger.error("Error al despachar mensaje a WhatsApp: %s", exc)
        return False


def run_reminders_check() -> int:
    """Ejecuta la revisión de recordatorios para mañana y para hoy."""
    today = date.today()
    tomorrow = today + timedelta(days=1)

    today_str = today.isoformat()
    tomorrow_str = tomorrow.isoformat()

    logger.info("Iniciando revisión de recordatorios... (Hoy: %s, Mañana: %s)", today_str, tomorrow_str)

    reminders = vault_service.get_all_reminders()
    notifications_sent = 0

    for rem in reminders:
        rem_id = rem.get("id")
        rem_date = rem.get("reminder_date")
        target = rem.get("target") or "Fidel"
        requester = rem.get("requester") or target
        text = rem.get("text", "")
        notified_day_before = bool(rem.get("notified_day_before"))
        notified_day_of = bool(rem.get("notified_day_of"))
        status = rem.get("status", "pending")

        if status == "completed" and notified_day_of:
            continue

        target_display = target.capitalize()
        req_notice = f" (Pedido por {requester.capitalize()})" if requester.lower() != target.lower() else ""

        # CASO 1: AVISO EL DÍA ANTERIOR (Mañana es la fecha)
        if rem_date == tomorrow_str and not notified_day_before:
            msg = (
                f"🔔 *Recordatorio para mañana ({tomorrow_str})*\n\n"
                f"Hola *{target_display}*, me pediste que te recordara que mañana tienes que:\n"
                f"👉 *{text}*{req_notice}\n\n"
                f"_(Te volveré a avisar mañana a las 6:00 AM)_"
            )
            logger.info("Enviando aviso de día anterior para %s: %s", target_display, text)
            if send_whatsapp_message(msg):
                vault_service.mark_reminder_notified(rem_id, notified_day_before=True)
                notifications_sent += 1

        # CASO 2: AVISO EL DÍA DE HOY (Hoy es la fecha)
        elif rem_date == today_str and not notified_day_of:
            time_tag = f" (a las {rem.get('time')})" if rem.get("time") else ""
            msg = (
                f"⏰ *Recordatorio de hoy ({today_str})*\n\n"
                f"Buenos días *{target_display}*, hoy tienes programado{time_tag}:\n"
                f"👉 *{text}*{req_notice}\n\n"
                f"¡Que tengas un excelente día!"
            )
            logger.info("Enviando aviso del mero día para %s: %s", target_display, text)
            if send_whatsapp_message(msg):
                vault_service.mark_reminder_notified(rem_id, notified_day_of=True)
                notifications_sent += 1

    logger.info("Revisión finalizada. Total de recordatorios despachados: %d", notifications_sent)
    return notifications_sent


if __name__ == "__main__":
    count = run_reminders_check()
    print(f"Total notificaciones enviadas: {count}")
