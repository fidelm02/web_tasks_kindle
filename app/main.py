"""FastAPI application for Kindle Tasks and Home Portal.

Objective:
    Provide SSR endpoints for the home portal, local task management,
    ClickUp sprint/backlog viewer, and multi-format document reader
    with Kindle delivery and direct download support.

Author:
    Fidel Moreno Miranda <fidelm02@gmail.com>
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
import urllib.parse
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import clickup_service, email_service, reader_service, storage

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
    allowed_paths = {
        "/",
        "/tasks",
        "/tasks/completed",
        "/completed",
        "/clickup",
        "/lecturas",
    }
    if parsed.path in allowed_paths and not parsed.netloc:
        return target
    return default



@app.get("/")
def home_portal(request: Request):
    """Render the central home portal with sections Casa, Lau, Fidel.

    Args:
        request: FastAPI HTTP request instance.

    Returns:
        TemplateResponse: Rendered home portal template.
    """
    pending = storage.get_pending_tasks()
    docs_count = reader_service.count_all_documents()
    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "pending_count": len(pending),
            "docs_count": docs_count,
        },
    )


@app.get("/tasks")
def tasks_dashboard(request: Request, msg: str | None = None):
    """Render the active pending tasks dashboard.

    Args:
        request: FastAPI HTTP request instance.
        msg: Optional feedback message query parameter.

    Returns:
        TemplateResponse: Rendered tasks template.
    """
    pending = _sort_pending(storage.get_pending_tasks())
    completed = storage.get_completed_tasks()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "pending_tasks": pending,
            "pending_count": len(pending),
            "completed_count": len(completed),
            "active_tab": "pending",
            "msg": msg,
        },
    )



@app.get("/tasks/completed")
@app.get("/completed")
def completed_dashboard(request: Request):
    """Render the completed tasks history view.

    Args:
        request: FastAPI HTTP request instance.

    Returns:
        TemplateResponse: Rendered completed tasks template.
    """
    pending = storage.get_pending_tasks()
    completed = storage.get_completed_tasks()
    return templates.TemplateResponse(
        request,
        "completed.html",
        {
            "completed_tasks": completed,
            "pending_count": len(pending),
            "completed_count": len(completed),
            "active_tab": "completed",
        },
    )


@app.post("/tasks/create")
def create_task(
    title: str = Form(...),
    description: str = Form(""),
    priority: str = Form("Media"),
    target_date: str = Form(""),
    redirect_to: str = Form("/tasks"),
):
    """Create a new local task in JSON storage.

    Args:
        title: Task name string.
        description: Optional notes or context.
        priority: Alta, Media, or Baja.
        target_date: Optional due date string.
        redirect_to: Return URL after creation.

    Returns:
        RedirectResponse: HTTP 303 redirect to destination.
    """
    storage.create_task(title, description, priority, target_date or None)
    return RedirectResponse(
        _safe_redirect(redirect_to, "/tasks"), status_code=303
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
    """Update an existing task in local storage.

    Args:
        task_id: Unique UUID string of the task.
        title: Updated task title string.
        description: Optional updated notes.
        priority: Alta, Media, or Baja.
        target_date: Optional updated due date.
        redirect_to: Return URL after saving.

    Returns:
        RedirectResponse: HTTP 303 redirect with feedback.
    """
    storage.update_task(
        task_id,
        title,
        description,
        priority,
        target_date or None,
    )
    sep = "&" if "?" in redirect_to else "?"
    encoded_msg = urllib.parse.quote("Tarea actualizada correctamente.")
    dest_url = f"{redirect_to}{sep}msg={encoded_msg}"
    return RedirectResponse(
        _safe_redirect(dest_url, "/tasks"), status_code=303
    )



@app.post("/tasks/{task_id}/toggle")
def toggle_task(task_id: str, redirect_to: str = Form("/tasks")):
    """Toggle pending or completed status for a given task.

    Args:
        task_id: Unique UUID string of the task.
        redirect_to: Return URL.

    Returns:
        RedirectResponse: HTTP 303 redirect.
    """
    storage.toggle_task(task_id)
    return RedirectResponse(
        _safe_redirect(redirect_to, "/tasks"), status_code=303
    )


@app.post("/tasks/{task_id}/delete")
def delete_task(task_id: str, redirect_to: str = Form("/tasks")):
    """Permanently remove a task from local storage.

    Args:
        task_id: Unique UUID string of the task.
        redirect_to: Return URL.

    Returns:
        RedirectResponse: HTTP 303 redirect.
    """
    storage.delete_task(task_id)
    return RedirectResponse(
        _safe_redirect(redirect_to, "/tasks"), status_code=303
    )


@app.post("/tasks/{task_id}/archive")
def archive_task(task_id: str, redirect_to: str = Form("/tasks")):
    """Archive a specific task.

    Args:
        task_id: Unique UUID string of the task.
        redirect_to: Return URL.

    Returns:
        RedirectResponse: HTTP 303 redirect.
    """
    storage.archive_task(task_id)
    return RedirectResponse(
        _safe_redirect(redirect_to, "/tasks"), status_code=303
    )


@app.post("/tasks/archive-completed")
def archive_completed_tasks():
    """Archive all completed tasks in local storage.

    Args:
        None.

    Returns:
        RedirectResponse: HTTP 303 redirect to completed view.
    """
    storage.archive_completed()
    return RedirectResponse("/tasks/completed", status_code=303)


@app.get("/clickup")
def clickup_dashboard(
    request: Request,
    view: str = "sprint",
    msg: str | None = None,
    err: str | None = None,
):
    """Render ClickUp sprint or backlog tasks for user Fidel.

    Args:
        request: FastAPI HTTP request instance.
        view: Active view mode ('sprint' or 'backlog').
        msg: Optional success feedback string.
        err: Optional error feedback string.

    Returns:
        TemplateResponse: Rendered ClickUp template.
    """
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
    """Update status of a ClickUp task and redirect back with feedback.

    Args:
        task_id: Unique ClickUp task identifier.
        status: Target status name.
        redirect_to: Return URL.

    Returns:
        RedirectResponse: Redirect with message or error query param.
    """
    success, message = clickup_service.update_task_status(task_id, status)
    sep = "&" if "?" in redirect_to else "?"
    param = "msg" if success else "err"
    encoded_msg = urllib.parse.quote(message)
    dest_url = f"{redirect_to}{sep}{param}={encoded_msg}"
    return RedirectResponse(dest_url, status_code=303)


@app.get("/lecturas")
def reader_catalog(
    request: Request, msg: str | None = None, err: str | None = None
):
    """Render catalog of documents organized by folder categories.

    Args:
        request: FastAPI HTTP request instance.
        msg: Optional success flash message query parameter.
        err: Optional error flash message query parameter.

    Returns:
        TemplateResponse: Rendered reader list template.
    """
    categories = reader_service.list_documents_by_category()
    total_docs = reader_service.count_all_documents()
    return templates.TemplateResponse(
        request,
        "reader_list.html",
        {
            "categories": categories,
            "total_docs": total_docs,
            "msg": msg,
            "err": err,
        },
    )


@app.get("/lecturas/view/{file_path:path}")
def reader_document(request: Request, file_path: str):
    """Render an individual Markdown document for reading on Kindle.

    Args:
        request: FastAPI HTTP request instance.
        file_path: Relative path to document within docs directory.

    Returns:
        TemplateResponse: Rendered reader article template.

    Raises:
        HTTPException: If document is not found or not markdown.
    """
    doc = reader_service.get_markdown_html(file_path)
    if not doc:
        raise HTTPException(
            status_code=404, detail="Documento no encontrado."
        )
    return templates.TemplateResponse(
        request,
        "reader_view.html",
        {"doc": doc},
    )


@app.get("/lecturas/download/{file_path:path}")
def download_document(file_path: str):
    """Deliver a document as a direct file download for Kindle.

    Args:
        file_path: Relative path to document within docs directory.

    Returns:
        FileResponse: Attachment download response.

    Raises:
        HTTPException: If document is not found.
    """
    resolved_path = reader_service.resolve_document_path(file_path)
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


@app.post("/lecturas/send/{file_path:path}")
def send_to_kindle(file_path: str):
    """Send document via email to user Kindle recipient address.

    Args:
        file_path: Relative path to document within docs directory.

    Returns:
        RedirectResponse: Redirect to /lecturas with status message.

    Raises:
        HTTPException: If document is not found.
    """
    resolved_path = reader_service.resolve_document_path(file_path)
    if not resolved_path:
        raise HTTPException(
            status_code=404, detail="Archivo no encontrado."
        )

    success, message = email_service.send_document_to_kindle(resolved_path)
    param = "msg" if success else "err"
    encoded_msg = urllib.parse.quote(message)
    dest_url = f"/lecturas?{param}={encoded_msg}"
    return RedirectResponse(dest_url, status_code=303)
