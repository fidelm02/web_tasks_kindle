"""Router para generación y envío de reportes PDF por correo."""

from __future__ import annotations

from datetime import datetime
import urllib.parse
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from app import storage
from app.core.templates import templates
from app.services import (
    email_service,
    pdf_service,
    reader_service,
    section_service,
)

router = APIRouter(tags=["reports"])


@router.get("/sections/{section}/email")
def section_email_view(
    section: str,
    request: Request,
    msg: str | None = None,
    err: str | None = None,
):
    """Render form to email project task and document reports.

    Args:
        section: Section identifier string.
        request: FastAPI HTTP request instance.
        msg: Optional success query string.
        err: Optional error query string.

    Returns:
        TemplateResponse: Rendered email form.

    Raises:
        HTTPException: If section is not found.
    """
    sec = section_service.get_section(section)
    if not sec:
        raise HTTPException(
            status_code=404, detail="Sección no encontrada."
        )

    recipients = section_service.get_default_recipients()
    has_tasks = bool(sec.get("has_tasks"))
    has_docs = bool(sec.get("has_docs"))
    tasks_count = (
        len(storage.read_tasks(scope=section)) if has_tasks else 0
    )
    docs_count = (
        reader_service.count_all_documents(section=section)
        if has_docs
        else 0
    )

    return templates.TemplateResponse(
        request,
        "section_email.html",
        {
            "section": sec,
            "default_recipients": recipients,
            "tasks_count": tasks_count,
            "docs_count": docs_count,
            "page_title": f"Enviar Reporte - {sec['name']}",
            "page_heading": f"Reporte de {sec['name']}",
            "msg": msg,
            "err": err,
        },
    )


@router.post("/sections/{section}/email/send")
def section_send_email_action(
    section: str,
    selected_recipients: list[str] = Form([]),
    custom_recipient: str = Form(""),
    include_tasks: str | None = Form(None),
    include_docs: str | None = Form(None),
    subject: str = Form(""),
    notes: str = Form(""),
):
    """Generate requested PDF reports and email to selected recipients.

    Args:
        section: Section slug identifier string.
        selected_recipients: List of preconfigured recipient addresses.
        custom_recipient: Optional custom recipient string.
        include_tasks: Flag to attach tasks PDF.
        include_docs: Flag to attach documents PDF.
        subject: Optional email subject line.
        notes: Optional additional notes body text.

    Returns:
        RedirectResponse: Redirect to Home with feedback.

    Raises:
        HTTPException: If section is not found.
    """
    sec = section_service.get_section(section)
    if not sec:
        raise HTTPException(
            status_code=404, detail="Sección no encontrada."
        )

    targets: list[str] = list(selected_recipients)
    if custom_recipient.strip():
        for r in custom_recipient.replace(";", ",").split(","):
            cleaned = r.strip()
            if cleaned and "@" in cleaned:
                targets.append(cleaned)

    if not targets:
        encoded = urllib.parse.quote(
            "Debes seleccionar o ingresar al menos un correo de destino."
        )
        return RedirectResponse(
            f"/sections/{section}/email?err={encoded}", status_code=303
        )

    attachments: list[tuple[str, bytes]] = []

    if include_tasks and sec.get("has_tasks"):
        tasks = storage.read_tasks(scope=section)
        pdf_bytes = pdf_service.generate_tasks_pdf(sec["name"], tasks)
        attachments.append((f"Tareas_{sec['id']}.pdf", pdf_bytes))

    if include_docs and sec.get("has_docs"):
        categories = reader_service.list_documents_by_category(
            section=section
        )
        pdf_docs = pdf_service.generate_documents_pdf(
            sec["name"], categories
        )
        attachments.append((f"Documentos_{sec['id']}.pdf", pdf_docs))

    if not attachments:
        encoded = urllib.parse.quote(
            "Debes seleccionar al menos un reporte PDF para adjuntar."
        )
        return RedirectResponse(
            f"/sections/{section}/email?err={encoded}", status_code=303
        )

    email_subject = (
        subject.strip() or f"Reporte del Proyecto: {sec['name']}"
    )
    now_dt = datetime.now().strftime("%d/%m/%Y, %H:%M")
    body_lines = [
        f"Reporte del proyecto '{sec['name']}' generado desde Kindle Portal.",
        f"Fecha: {now_dt}",
        "",
    ]
    if notes.strip():
        body_lines.extend(["Notas:", notes.strip(), ""])
    body_lines.append(
        f"Se adjuntan {len(attachments)} archivo(s) PDF en este mensaje."
    )
    body_text = "\n".join(body_lines)

    success, message = email_service.send_project_report(
        recipients=targets,
        subject=email_subject,
        body=body_text,
        pdf_attachments=attachments,
    )

    encoded = urllib.parse.quote(message)
    param = "msg" if success else "err"
    return RedirectResponse(f"/?{param}={encoded}", status_code=303)
