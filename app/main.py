"""FastAPI application for Kindle Tasks and Home Portal.

Objective:
    Provide SSR endpoints for the home portal, dynamic sections,
    local task management, ClickUp sprint/backlog viewer, and
    multi-format document reader for Kindle Scribe.

Author:
    Fidel Moreno Miranda <fidelm02@gmail.com>
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
import urllib.parse
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import (
    clickup_service,
    email_service,
    pdf_service,
    reader_service,
    section_service,
    storage,
)

app = FastAPI(title="Kindle Tasks & Home Portal")
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

PRIORITY_ORDER: dict[str, int] = {"Alta": 0, "Media": 1, "Baja": 2}


def format_datetime_filter(val: str | None) -> str:
    """Format ISO timestamps for clean e-ink display.

    Args:
        val: ISO-formatted timestamp string or None.

    Returns:
        str: Human-readable timestamp string.
    """
    if not val:
        return ""
    try:
        dt = datetime.fromisoformat(val)
        today = date.today()
        if dt.date() == today:
            return f"Hoy, {dt.strftime('%H:%M')}"
        return dt.strftime("%d/%m/%Y, %H:%M")
    except Exception:
        return str(val)[:16].replace("T", " ")


def format_target_date_filter(val: str | None) -> str:
    """Format deadline date with friendly relative labels.

    Args:
        val: Date string in ISO format or None.

    Returns:
        str: Relative or formatted date string.
    """
    if not val:
        return ""
    try:
        d = date.fromisoformat(val)
        today = date.today()
        diff = (d - today).days
        if diff == 0:
            return "Hoy"
        if diff == 1:
            return "Mañana"
        if diff < 0:
            return f"Venció el {d.strftime('%d/%m/%Y')}"
        return d.strftime("%d/%m/%Y")
    except Exception:
        return str(val)


templates.env.filters["format_datetime"] = format_datetime_filter
templates.env.filters["format_target_date"] = format_target_date_filter


def _sort_pending(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort pending tasks by priority order and target date.

    Args:
        tasks: List of raw task dictionaries.

    Returns:
        list[dict[str, Any]]: Sorted task list.
    """
    return sorted(
        tasks,
        key=lambda t: (
            PRIORITY_ORDER.get(t.get("priority", "Media"), 3),
            t.get("target_date") or "9999-99-99",
        ),
    )


def _safe_redirect(target: str | None, default: str = "/tasks") -> str:
    """Validate and sanitize redirect URL to prevent open redirects.

    Args:
        target: Requested destination URL.
        default: Fallback URL if target is unauthorized.

    Returns:
        str: Safe redirect URL string.
    """
    if not target:
        return default
    parsed = urllib.parse.urlparse(target)
    if (
        not parsed.netloc
        and parsed.path.startswith("/")
        and not parsed.path.startswith("//")
    ):
        return target
    return default


def _get_section_title(scope: str) -> str:
    """Return friendly display name for a given section scope.

    Args:
        scope: Section slug or identifier.

    Returns:
        str: Display title string.
    """
    sec = section_service.get_section(scope)
    if sec:
        return sec.get("name", scope.title())
    return scope.replace("_", " ").replace("-", " ").title()


# ============================================================================
# Controladores Genéricos de Tareas
# ============================================================================


def render_tasks_dashboard(
    request: Request,
    scope: str,
    base_url: str,
    msg: str | None = None,
):
    """Render the active pending tasks dashboard for given scope.

    Args:
        request: FastAPI HTTP request instance.
        scope: Task scope identifier string.
        base_url: Base URL prefix for actions.
        msg: Optional feedback notification message.

    Returns:
        TemplateResponse: Rendered tasks template.
    """
    pending = _sort_pending(storage.get_pending_tasks(scope=scope))
    completed = storage.get_completed_tasks(scope=scope)
    name = _get_section_title(scope)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "pending_tasks": pending,
            "pending_count": len(pending),
            "completed_count": len(completed),
            "active_tab": "pending",
            "base_url": base_url,
            "page_title": f"Pendientes - {name}",
            "page_heading": f"Pendientes - {name}",
            "msg": msg,
        },
    )


def render_completed_dashboard(
    request: Request,
    scope: str,
    base_url: str,
):
    """Render the completed tasks history view for given scope.

    Args:
        request: FastAPI HTTP request instance.
        scope: Task scope identifier string.
        base_url: Base URL prefix for actions.

    Returns:
        TemplateResponse: Rendered completed tasks template.
    """
    pending = storage.get_pending_tasks(scope=scope)
    completed = storage.get_completed_tasks(scope=scope)
    name = _get_section_title(scope)
    return templates.TemplateResponse(
        request,
        "completed.html",
        {
            "completed_tasks": completed,
            "pending_count": len(pending),
            "completed_count": len(completed),
            "active_tab": "completed",
            "base_url": base_url,
            "page_title": f"Completadas - {name}",
            "page_heading": f"Completadas - {name}",
        },
    )


def handle_create_task(
    scope: str,
    title: str,
    description: str,
    priority: str,
    target_date: str,
    redirect_to: str,
    default_url: str,
) -> RedirectResponse:
    """Create a new task and redirect back safely.

    Args:
        scope: Task scope identifier string.
        title: Task name string.
        description: Optional notes or context.
        priority: Alta, Media, or Baja.
        target_date: Optional due date string.
        redirect_to: Requested return URL.
        default_url: Fallback URL if redirect is invalid.

    Returns:
        RedirectResponse: HTTP 303 redirect.
    """
    storage.create_task(
        title=title,
        description=description,
        priority=priority,
        target_date=target_date or None,
        scope=scope,
    )
    return RedirectResponse(
        _safe_redirect(redirect_to, default_url), status_code=303
    )


def handle_edit_task(
    scope: str,
    task_id: str,
    title: str,
    description: str,
    priority: str,
    target_date: str,
    redirect_to: str,
    default_url: str,
) -> RedirectResponse:
    """Update an existing task and redirect back with feedback.

    Args:
        scope: Task scope identifier string.
        task_id: Unique UUID string of the task.
        title: Updated title string.
        description: Updated notes or context.
        priority: Updated priority string.
        target_date: Updated due date string.
        redirect_to: Requested return URL.
        default_url: Fallback URL.

    Returns:
        RedirectResponse: HTTP 303 redirect.
    """
    updated = storage.update_task(
        task_id=task_id,
        title=title,
        description=description,
        priority=priority,
        target_date=target_date or None,
        scope=scope,
    )
    dest_url = _safe_redirect(redirect_to, default_url)
    if updated:
        sep = "&" if "?" in dest_url else "?"
        encoded = urllib.parse.quote("Tarea actualizada correctamente.")
        dest_url = f"{dest_url}{sep}msg={encoded}"
    return RedirectResponse(dest_url, status_code=303)


def handle_toggle_task(
    scope: str,
    task_id: str,
    redirect_to: str,
    default_url: str,
) -> RedirectResponse:
    """Toggle status of a task and redirect back.

    Args:
        scope: Task scope identifier string.
        task_id: Unique UUID string.
        redirect_to: Requested return URL.
        default_url: Fallback URL.

    Returns:
        RedirectResponse: HTTP 303 redirect.
    """
    storage.toggle_task(task_id, scope=scope)
    return RedirectResponse(
        _safe_redirect(redirect_to, default_url), status_code=303
    )


def handle_delete_task(
    scope: str,
    task_id: str,
    redirect_to: str,
    default_url: str,
) -> RedirectResponse:
    """Delete a task and redirect back.

    Args:
        scope: Task scope identifier string.
        task_id: Unique UUID string.
        redirect_to: Requested return URL.
        default_url: Fallback URL.

    Returns:
        RedirectResponse: HTTP 303 redirect.
    """
    storage.delete_task(task_id, scope=scope)
    return RedirectResponse(
        _safe_redirect(redirect_to, default_url), status_code=303
    )


def handle_archive_completed(
    scope: str,
    redirect_to: str,
    default_url: str,
) -> RedirectResponse:
    """Archive all completed tasks in given scope.

    Args:
        scope: Task scope identifier string.
        redirect_to: Requested return URL.
        default_url: Fallback URL.

    Returns:
        RedirectResponse: HTTP 303 redirect.
    """
    storage.archive_completed(scope=scope)
    return RedirectResponse(
        _safe_redirect(redirect_to, default_url), status_code=303
    )


# ============================================================================
# Controladores Genéricos de Lecturas y Documentos
# ============================================================================


def render_reader_catalog(
    request: Request,
    section: str,
    base_url: str,
    msg: str | None = None,
    err: str | None = None,
):
    """Render catalog of documents organized by categories.

    Args:
        request: FastAPI HTTP request instance.
        section: Section identifier string.
        base_url: Base URL prefix for links and forms.
        msg: Optional success notification message.
        err: Optional warning/error notification message.

    Returns:
        TemplateResponse: Rendered reader list template.
    """
    categories = reader_service.list_documents_by_category(section=section)
    total_docs = reader_service.count_all_documents(section=section)
    existing = reader_service.get_existing_categories(section=section)
    name = _get_section_title(section)
    return templates.TemplateResponse(
        request,
        "reader_list.html",
        {
            "categories": categories,
            "total_docs": total_docs,
            "existing_categories": existing,
            "base_url": base_url,
            "page_title": f"Documentos y Lecturas ({name}) - Kindle Scribe",
            "page_heading": f"Documentos ({name})",
            "msg": msg,
            "err": err,
        },
    )


def render_reader_document(
    request: Request,
    file_path: str,
    section: str,
    base_url: str,
):
    """Render an individual Markdown document for reading.

    Args:
        request: FastAPI HTTP request instance.
        file_path: Relative path to document within section docs.
        section: Section identifier string.
        base_url: Base URL prefix for navigation.

    Returns:
        TemplateResponse: Rendered reader view template.

    Raises:
        HTTPException: If document is not found or not markdown.
    """
    doc = reader_service.get_markdown_html(file_path, section=section)
    if not doc:
        raise HTTPException(
            status_code=404, detail="Documento no encontrado."
        )
    name = _get_section_title(section)
    return templates.TemplateResponse(
        request,
        "reader_view.html",
        {
            "doc": doc,
            "base_url": base_url,
            "page_title": f"{doc['title']} - {name}",
            "page_heading": f"Lectura ({name})",
        },
    )


def handle_download_document(file_path: str, section: str):
    """Deliver a document file as an attachment download.

    Args:
        file_path: Relative path to document file.
        section: Section identifier string.

    Returns:
        FileResponse: Attachment download response.

    Raises:
        HTTPException: If file is not found.
    """
    resolved_path = reader_service.resolve_document_path(
        file_path, section=section
    )
    if not resolved_path:
        raise HTTPException(
            status_code=404, detail="Archivo no encontrado."
        )
    return FileResponse(
        path=resolved_path,
        filename=resolved_path.name,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{resolved_path.name}"'
            )
        },
    )


def handle_send_to_kindle(
    file_path: str,
    section: str,
    redirect_url: str,
) -> RedirectResponse:
    """Send document via email to user Kindle recipient address.

    Args:
        file_path: Relative path to document.
        section: Section identifier string.
        redirect_url: Destination URL after sending.

    Returns:
        RedirectResponse: Redirect with status message.

    Raises:
        HTTPException: If document is not found.
    """
    resolved_path = reader_service.resolve_document_path(
        file_path, section=section
    )
    if not resolved_path:
        raise HTTPException(
            status_code=404, detail="Archivo no encontrado."
        )
    success, message = email_service.send_document_to_kindle(resolved_path)
    param = "msg" if success else "err"
    encoded = urllib.parse.quote(message)
    return RedirectResponse(
        f"{redirect_url}?{param}={encoded}", status_code=303
    )


def handle_upload_document(
    file: UploadFile,
    category: str,
    new_category: str,
    section: str,
    redirect_url: str,
) -> RedirectResponse:
    """Save an uploaded document safely and redirect back.

    Args:
        file: UploadFile payload.
        category: Selected existing category name.
        new_category: Optional new category string.
        section: Section identifier string.
        redirect_url: Destination URL.

    Returns:
        RedirectResponse: Redirect with status notification.
    """
    target_folder = (
        new_category.strip() if new_category.strip() else category.strip()
    )
    success, message = reader_service.save_uploaded_document(
        filename=file.filename or "documento",
        file_obj=file.file,
        subfolder=target_folder,
        section=section,
    )
    param = "msg" if success else "err"
    encoded = urllib.parse.quote(message)
    return RedirectResponse(
        f"{redirect_url}?{param}={encoded}", status_code=303
    )


def handle_archive_document(
    file_path: str,
    section: str,
    redirect_url: str,
) -> RedirectResponse:
    """Move document to section archive and redirect back.

    Args:
        file_path: Relative path to document.
        section: Section identifier string.
        redirect_url: Destination URL.

    Returns:
        RedirectResponse: Redirect with notification.
    """
    success, message = reader_service.archive_document(
        file_path, section=section
    )
    param = "msg" if success else "err"
    encoded = urllib.parse.quote(message)
    return RedirectResponse(
        f"{redirect_url}?{param}={encoded}", status_code=303
    )


# ============================================================================
# Portal de Inicio (Home) y Registro de Secciones
# ============================================================================


@app.get("/")
def home_portal(
    request: Request,
    msg: str | None = None,
    err: str | None = None,
):
    """Render the central home portal with all active sections.

    Args:
        request: FastAPI HTTP request instance.
        msg: Optional success notification query parameter.
        err: Optional error notification query parameter.

    Returns:
        TemplateResponse: Rendered home portal template.
    """
    sections = section_service.get_active_sections()
    archived_count = len(
        section_service.get_sections_by_status("archived")
    )
    completed_count = len(
        section_service.get_sections_by_status("completed")
    )
    sections_view: list[dict[str, Any]] = []

    for sec in sections:
        item = dict(sec)
        sec_id = sec["id"]
        item["icon_svg"] = section_service.get_icon_svg(
            sec.get("icon", "folder")
        )

        if sec.get("has_tasks"):
            pending = storage.get_pending_tasks(scope=sec_id)
            item["pending_count"] = len(pending)
            if sec_id == "casa":
                item["tasks_url"] = "/tasks"
            else:
                item["tasks_url"] = f"/{sec_id}/tasks"

        if sec.get("has_docs"):
            item["docs_count"] = reader_service.count_all_documents(
                section=sec_id
            )
            if sec_id in ("fidel", "default"):
                item["docs_url"] = "/lecturas"
            else:
                item["docs_url"] = f"/{sec_id}/lecturas"

        sections_view.append(item)

    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "sections": sections_view,
            "archived_count": archived_count,
            "completed_count": completed_count,
            "msg": msg,
            "err": err,
        },
    )


@app.get("/sections/status/{status}")
def sections_by_status_view(
    status: str,
    request: Request,
    msg: str | None = None,
    err: str | None = None,
):
    """Render listing of sections filtered by completed or archived status.

    Args:
        request: FastAPI HTTP request instance.
        status: Target status ('completed' or 'archived').
        msg: Optional success feedback string.
        err: Optional error feedback string.

    Returns:
        TemplateResponse: Rendered status view.

    Raises:
        HTTPException: If status parameter is invalid.
    """
    norm_status = status.lower().strip()
    if norm_status not in ("completed", "archived"):
        raise HTTPException(
            status_code=404, detail="Estado de sección no válido."
        )

    sections = section_service.get_sections_by_status(norm_status)
    sections_view: list[dict[str, Any]] = []
    for sec in sections:
        item = dict(sec)
        sec_id = sec["id"]
        item["icon_svg"] = section_service.get_icon_svg(
            sec.get("icon", "folder")
        )
        if sec.get("has_tasks"):
            pending = storage.get_pending_tasks(scope=sec_id)
            item["pending_count"] = len(pending)
            item["tasks_url"] = f"/{sec_id}/tasks"
        if sec.get("has_docs"):
            item["docs_count"] = reader_service.count_all_documents(
                section=sec_id
            )
            item["docs_url"] = f"/{sec_id}/lecturas"
        sections_view.append(item)

    is_archived = norm_status == "archived"
    heading = (
        "Proyectos Archivados" if is_archived else "Proyectos Completados"
    )
    return templates.TemplateResponse(
        request,
        "sections_status.html",
        {
            "status": norm_status,
            "sections": sections_view,
            "page_title": f"{heading} - Kindle Scribe",
            "page_heading": heading,
            "msg": msg,
            "err": err,
        },
    )


@app.post("/sections/{section_id}/status")
def update_section_status_action(
    section_id: str,
    new_status: str = Form(...),
    redirect_to: str = Form("/"),
):
    """Update section lifecycle status and redirect back safely.

    Args:
        section_id: Unique section slug string.
        new_status: Target status ('active', 'completed', 'archived').
        redirect_to: Return URL string.

    Returns:
        RedirectResponse: HTTP 303 redirect.
    """
    success = section_service.update_section_status(section_id, new_status)
    status_labels = {
        "active": "reactivado",
        "completed": "marcado como completado",
        "archived": "archivado",
    }
    if success:
        label = status_labels.get(new_status, new_status)
        encoded = urllib.parse.quote(
            f"Proyecto {label} correctamente."
        )
        dest = _safe_redirect(redirect_to, "/")
        sep = "&" if "?" in dest else "?"
        return RedirectResponse(f"{dest}{sep}msg={encoded}", status_code=303)

    encoded = urllib.parse.quote(
        "No se pudo cambiar el estado de la sección."
    )
    dest = _safe_redirect(redirect_to, "/")
    sep = "&" if "?" in dest else "?"
    return RedirectResponse(f"{dest}{sep}err={encoded}", status_code=303)


@app.get("/sections/{section}/email")
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


@app.post("/sections/{section}/email/send")
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


@app.get("/sections/new")
def new_section_view(
    request: Request,
    err: str | None = None,
):
    """Render form to create a new section or project.

    Args:
        request: FastAPI HTTP request instance.
        err: Optional error message parameter.

    Returns:
        TemplateResponse: Rendered section creation form.
    """
    icons = section_service.list_available_icons()
    return templates.TemplateResponse(
        request,
        "section_new.html",
        {
            "available_icons": icons,
            "err": err,
            "page_title": "Nueva Sección - Kindle Scribe",
            "page_heading": "Nueva Sección",
        },
    )


@app.post("/sections/create")
def create_section_action(
    name: str = Form(...),
    icon: str = Form("folder"),
    has_tasks: str | None = Form(None),
    has_docs: str | None = Form(None),
    description: str = Form(""),
):
    """Process creation of a new custom section or project.

    Args:
        name: Name of the new section.
        icon: Selected SVG icon key.
        has_tasks: Checkbox value for tasks module.
        has_docs: Checkbox value for documents module.
        description: Optional notes or scope description.

    Returns:
        RedirectResponse: Redirect to home portal with message.
    """
    clean_name = name.strip()
    if not clean_name:
        encoded = urllib.parse.quote("El nombre no puede estar vacío.")
        return RedirectResponse(
            f"/sections/new?err={encoded}", status_code=303
        )

    tasks_enabled = has_tasks in ("on", "true", "1", True)
    docs_enabled = has_docs in ("on", "true", "1", True)

    new_sec = section_service.create_section(
        name=clean_name,
        icon=icon,
        has_tasks=tasks_enabled,
        has_docs=docs_enabled,
        description=description,
    )

    slug = new_sec["id"]
    if tasks_enabled:
        storage._ensure_db_exists(slug)
    if docs_enabled:
        reader_service._ensure_docs_dir(slug)

    encoded = urllib.parse.quote(
        f"Sección '{clean_name}' creada exitosamente."
    )
    return RedirectResponse(f"/?msg={encoded}", status_code=303)


# ============================================================================
# Rutas Retrocompatibles de Tareas (Casa)
# ============================================================================


@app.get("/tasks")
def tasks_dashboard(request: Request, msg: str | None = None):
    """Render the active pending tasks dashboard for Casa."""
    return render_tasks_dashboard(
        request, scope="casa", base_url="/tasks", msg=msg
    )


@app.get("/tasks/completed")
@app.get("/completed")
def completed_dashboard(request: Request):
    """Render completed tasks history for Casa."""
    return render_completed_dashboard(
        request, scope="casa", base_url="/tasks"
    )


@app.post("/tasks/create")
def create_task(
    title: str = Form(...),
    description: str = Form(""),
    priority: str = Form("Media"),
    target_date: str = Form(""),
    redirect_to: str = Form("/tasks"),
):
    """Create a new local task in Casa storage."""
    return handle_create_task(
        scope="casa",
        title=title,
        description=description,
        priority=priority,
        target_date=target_date,
        redirect_to=redirect_to,
        default_url="/tasks",
    )


@app.post("/tasks/{task_id}/edit")
def edit_task(
    task_id: str,
    title: str = Form(...),
    description: str = Form(""),
    priority: str = Form("Media"),
    target_date: str = Form(""),
    redirect_to: str = Form("/tasks"),
):
    """Update an existing task in Casa storage."""
    return handle_edit_task(
        scope="casa",
        task_id=task_id,
        title=title,
        description=description,
        priority=priority,
        target_date=target_date,
        redirect_to=redirect_to,
        default_url="/tasks",
    )


@app.post("/tasks/{task_id}/toggle")
def toggle_task(task_id: str, redirect_to: str = Form("/tasks")):
    """Toggle status of a Casa task."""
    return handle_toggle_task(
        scope="casa",
        task_id=task_id,
        redirect_to=redirect_to,
        default_url="/tasks",
    )


@app.post("/tasks/{task_id}/delete")
def delete_task(task_id: str, redirect_to: str = Form("/tasks")):
    """Delete a task permanently in Casa storage."""
    return handle_delete_task(
        scope="casa",
        task_id=task_id,
        redirect_to=redirect_to,
        default_url="/tasks",
    )


@app.post("/tasks/archive-completed")
def archive_completed(redirect_to: str = Form("/tasks/completed")):
    """Archive completed tasks in Casa storage."""
    return handle_archive_completed(
        scope="casa",
        redirect_to=redirect_to,
        default_url="/tasks/completed",
    )


# ============================================================================
# Rutas de ClickUp (Fidel)
# ============================================================================


@app.get("/clickup")
def clickup_dashboard(
    request: Request,
    view: str = "sprint",
    msg: str | None = None,
    err: str | None = None,
):
    """Render ClickUp sprint or backlog tasks for user Fidel."""
    if view == "backlog":
        list_name, tasks, error = clickup_service.get_backlog_tasks()
    else:
        view = "sprint"
        list_name, tasks, error = clickup_service.get_sprint_tasks()

    raw_req_tasks = [t for t in tasks if t.get("is_req")]
    raw_dev_tasks = [t for t in tasks if not t.get("is_req")]

    req_tasks = clickup_service.sort_tasks_by_priority(raw_req_tasks)
    status_groups = clickup_service.group_tasks_by_status(raw_dev_tasks)
    available_statuses = clickup_service.get_available_statuses()
    current_url = f"/clickup?view={view}"

    return templates.TemplateResponse(
        request,
        "clickup.html",
        {
            "list_name": list_name,
            "tasks": tasks,
            "req_tasks": req_tasks,
            "status_groups": status_groups,
            "available_statuses": available_statuses,
            "error": err or error,
            "msg": msg,
            "active_view": view,
            "current_url": current_url,
        },
    )


@app.post("/clickup/tasks/{task_id}/status")
def update_clickup_status(
    task_id: str,
    status: str = Form(...),
    redirect_to: str = Form("/clickup"),
):
    """Update status of a ClickUp task and redirect back."""
    success, message = clickup_service.update_task_status(task_id, status)
    sep = "&" if "?" in redirect_to else "?"
    param = "msg" if success else "err"
    encoded_msg = urllib.parse.quote(message)
    dest_url = f"{redirect_to}{sep}{param}={encoded_msg}"
    return RedirectResponse(dest_url, status_code=303)


# ============================================================================
# Rutas Retrocompatibles de Lecturas (Fidel / Default)
# ============================================================================


@app.get("/lecturas")
def reader_catalog(
    request: Request, msg: str | None = None, err: str | None = None
):
    """Render catalog of documents for Fidel / Default library."""
    return render_reader_catalog(
        request,
        section="fidel",
        base_url="/lecturas",
        msg=msg,
        err=err,
    )


@app.get("/lecturas/view/{file_path:path}")
def reader_document(request: Request, file_path: str):
    """Render an individual Markdown document in Fidel library."""
    return render_reader_document(
        request,
        file_path=file_path,
        section="fidel",
        base_url="/lecturas",
    )


@app.get("/lecturas/download/{file_path:path}")
def download_document(file_path: str):
    """Deliver a document download from Fidel library."""
    return handle_download_document(file_path=file_path, section="fidel")


@app.post("/lecturas/send/{file_path:path}")
def send_to_kindle(file_path: str):
    """Send document from Fidel library to Kindle via email."""
    return handle_send_to_kindle(
        file_path=file_path,
        section="fidel",
        redirect_url="/lecturas",
    )


@app.post("/lecturas/upload")
async def upload_document(
    file: UploadFile = File(...),
    category: str = Form(""),
    new_category: str = Form(""),
) -> RedirectResponse:
    """Upload a document to Fidel library from desktop or mobile."""
    return handle_upload_document(
        file=file,
        category=category,
        new_category=new_category,
        section="fidel",
        redirect_url="/lecturas",
    )


@app.post("/lecturas/archive/{file_path:path}")
def archive_document(file_path: str) -> RedirectResponse:
    """Move a document to Fidel archive directory with timestamp."""
    return handle_archive_document(
        file_path=file_path,
        section="fidel",
        redirect_url="/lecturas",
    )


# ============================================================================
# Rutas Genéricas de Tareas para Cualquier Sección (Lau, Fidel, Proyectos)
# ============================================================================


@app.get("/{section}/tasks")
def section_tasks_dashboard(
    section: str,
    request: Request,
    msg: str | None = None,
):
    """Render active pending tasks dashboard for given section."""
    return render_tasks_dashboard(
        request,
        scope=section,
        base_url=f"/{section}/tasks",
        msg=msg,
    )


@app.get("/{section}/tasks/completed")
def section_completed_dashboard(section: str, request: Request):
    """Render completed tasks history view for given section."""
    return render_completed_dashboard(
        request,
        scope=section,
        base_url=f"/{section}/tasks",
    )


@app.post("/{section}/tasks/create")
def section_create_task(
    section: str,
    title: str = Form(...),
    description: str = Form(""),
    priority: str = Form("Media"),
    target_date: str = Form(""),
    redirect_to: str | None = None,
):
    """Create a new task in given section storage."""
    base_url = f"/{section}/tasks"
    return handle_create_task(
        scope=section,
        title=title,
        description=description,
        priority=priority,
        target_date=target_date,
        redirect_to=redirect_to or base_url,
        default_url=base_url,
    )


@app.post("/{section}/tasks/{task_id}/edit")
def section_edit_task(
    section: str,
    task_id: str,
    title: str = Form(...),
    description: str = Form(""),
    priority: str = Form("Media"),
    target_date: str = Form(""),
    redirect_to: str | None = None,
):
    """Update an existing task in given section storage."""
    base_url = f"/{section}/tasks"
    return handle_edit_task(
        scope=section,
        task_id=task_id,
        title=title,
        description=description,
        priority=priority,
        target_date=target_date,
        redirect_to=redirect_to or base_url,
        default_url=base_url,
    )


@app.post("/{section}/tasks/{task_id}/toggle")
def section_toggle_task(
    section: str,
    task_id: str,
    redirect_to: str | None = None,
):
    """Toggle status of a task in given section storage."""
    base_url = f"/{section}/tasks"
    return handle_toggle_task(
        scope=section,
        task_id=task_id,
        redirect_to=redirect_to or base_url,
        default_url=base_url,
    )


@app.post("/{section}/tasks/{task_id}/delete")
def section_delete_task(
    section: str,
    task_id: str,
    redirect_to: str | None = None,
):
    """Delete a task permanently in given section storage."""
    base_url = f"/{section}/tasks"
    return handle_delete_task(
        scope=section,
        task_id=task_id,
        redirect_to=redirect_to or base_url,
        default_url=base_url,
    )


@app.post("/{section}/tasks/archive-completed")
def section_archive_completed(
    section: str,
    redirect_to: str | None = None,
):
    """Archive completed tasks in given section storage."""
    base_url = f"/{section}/tasks/completed"
    return handle_archive_completed(
        scope=section,
        redirect_to=redirect_to or base_url,
        default_url=base_url,
    )


# ============================================================================
# Rutas Genéricas de Lecturas para Cualquier Sección (Lau, Fidel, Proyectos)
# ============================================================================


@app.get("/{section}/lecturas")
def section_reader_catalog(
    section: str,
    request: Request,
    msg: str | None = None,
    err: str | None = None,
):
    """Render documents catalog for given section library."""
    return render_reader_catalog(
        request,
        section=section,
        base_url=f"/{section}/lecturas",
        msg=msg,
        err=err,
    )


@app.get("/{section}/lecturas/view/{file_path:path}")
def section_reader_document(
    section: str,
    file_path: str,
    request: Request,
):
    """Render an individual Markdown document in given section library."""
    return render_reader_document(
        request,
        file_path=file_path,
        section=section,
        base_url=f"/{section}/lecturas",
    )


@app.get("/{section}/lecturas/download/{file_path:path}")
def section_download_document(section: str, file_path: str):
    """Deliver a document download from given section library."""
    return handle_download_document(file_path=file_path, section=section)


@app.post("/{section}/lecturas/send/{file_path:path}")
def section_send_to_kindle(section: str, file_path: str):
    """Send document from given section to Kindle via email."""
    return handle_send_to_kindle(
        file_path=file_path,
        section=section,
        redirect_url=f"/{section}/lecturas",
    )


@app.post("/{section}/lecturas/upload")
async def section_upload_document(
    section: str,
    file: UploadFile = File(...),
    category: str = Form(""),
    new_category: str = Form(""),
) -> RedirectResponse:
    """Upload a document to given section library."""
    return handle_upload_document(
        file=file,
        category=category,
        new_category=new_category,
        section=section,
        redirect_url=f"/{section}/lecturas",
    )


@app.post("/{section}/lecturas/archive/{file_path:path}")
def section_archive_document(
    section: str,
    file_path: str,
) -> RedirectResponse:
    """Move document to section archive directory with timestamp."""
    return handle_archive_document(
        file_path=file_path,
        section=section,
        redirect_url=f"/{section}/lecturas",
    )
