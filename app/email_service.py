"""Email delivery service for sending documents to Kindle.

Objective:
    Deliver documents (PDF, EPUB, MD) directly to the user Kindle
    email address (fidelm02@kindle.com) via Gmail SMTP or REST API.

Author:
    Fidel Moreno Miranda <fidelm02@gmail.com>
"""

from __future__ import annotations

from email.message import EmailMessage
import mimetypes
import os
from pathlib import Path
import smtplib

# Attempt to load credentials from constants or parent workspace
try:
    from app import constants as config  # type: ignore
except ImportError:
    try:
        import sys

        parent_dir = str(Path(__file__).resolve().parent.parent.parent)
        if parent_dir not in sys.path:
            sys.path.append(parent_dir)
        from Clickup import constants as config  # type: ignore
    except ImportError:
        config = None  # type: ignore


def _get_cfg(key: str, default: str = "") -> str:
    """Retrieve configuration parameter from constants or environment.

    Args:
        key: Setting variable name.
        default: Fallback string value.

    Returns:
        str: Resolved setting value.
    """
    if config is not None and hasattr(config, key):
        val = getattr(config, key)
        if val:
            return str(val)
    return os.getenv(key, default)


def send_document_to_kindle(file_path: Path) -> tuple[bool, str]:
    """Send a document file attached to the Kindle recipient email.

    Connects to Gmail SMTP over SSL using application password
    credentials and sends the file to the Amazon Kindle address.

    Args:
        file_path: Absolute or resolved path to the document file.

    Returns:
        tuple[bool, str]: Success boolean and descriptive status
            message.
    """
    if not file_path.is_file():
        return False, f"Archivo no encontrado: {file_path.name}"

    sender = _get_cfg("GMAIL_SENDER_EMAIL", "fidelm02@gmail.com")
    recipient = _get_cfg("EMAIL_RECIPIENT", "fidelm02@kindle.com")
    app_pwd = _get_cfg("GMAIL_APP_PASSWORD", "")

    if not sender or not recipient:
        return (
            False,
            "GMAIL_SENDER_EMAIL o EMAIL_RECIPIENT no están configurados.",
        )

    if not app_pwd:
        return (
            False,
            "GMAIL_APP_PASSWORD no está configurado en app/constants.py.",
        )

    msg = EmailMessage()
    msg["Subject"] = file_path.stem
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(
        f"Documento enviado desde Kindle Home Portal: {file_path.name}"
    )

    mime_type, _ = mimetypes.guess_type(str(file_path))
    maintype, subtype = (
        mime_type.split("/", 1)
        if mime_type
        else ("application", "octet-stream")
    )

    try:
        data = file_path.read_bytes()
        msg.add_attachment(
            data,
            maintype=maintype,
            subtype=subtype,
            filename=file_path.name,
        )

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as s:
            s.login(sender, app_pwd)
            s.send_message(msg)

        return (
            True,
            f"Archivo enviado correctamente a {recipient}. "
            "Amazon lo procesará en breve.",
        )
    except smtplib.SMTPAuthenticationError:
        return (
            False,
            "Error de autenticación en Gmail. Asegúrate de usar una "
            "'Contraseña de aplicación' de 16 caracteres de Google.",
        )
    except Exception as exc:
        return False, f"Error al enviar correo: {exc}"
