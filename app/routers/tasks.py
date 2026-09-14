"""Router para gestión de tareas (locales en Casa y dinámicas por sección)."""

from __future__ import annotations

from typing import Any
import urllib.parse
from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app import storage
from app.core.helpers import get_section_title, safe_redirect
from app.core.templates import templates

router = APIRouter(tags=["tasks"])

PRIORITY_ORDER: dict[str, int] = {"Alta": 0, "Media": 1, "Baja": 2}


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
            PRIORITY_ORDER.get(t.get("priority", "Media"), 1),
            t.get("target_date") or "9999-99-99",
            t.get("created_at", ""),
        ),
    )


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
    name = get_section_title(scope)
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
    name = get_section_title(scope)
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
        safe_redirect(redirect_to, default_url), status_code=303
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
    dest_url = safe_redirect(redirect_to, default_url)
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
        safe_redirect(redirect_to, default_url), status_code=303
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
        safe_redirect(redirect_to, default_url), status_code=303
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
        safe_redirect(redirect_to, default_url), status_code=303
    )


# ============================================================================
# Rutas de Tareas para Casa (/tasks)
# ============================================================================


@router.get("/tasks")
def tasks_dashboard(request: Request, msg: str | None = None):
    """Render the active pending tasks dashboard for Casa."""
    return render_tasks_dashboard(
        request, scope="casa", base_url="/tasks", msg=msg
    )


@router.get("/tasks/completed")
@router.get("/completed")
def completed_dashboard(request: Request):
    """Render completed tasks history for Casa."""
    return render_completed_dashboard(
        request, scope="casa", base_url="/tasks"
    )


@router.post("/tasks/create")
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


@router.post("/tasks/{task_id}/edit")
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


@router.post("/tasks/{task_id}/toggle")
def toggle_task(task_id: str, redirect_to: str = Form("/tasks")):
    """Toggle status of a Casa task."""
    return handle_toggle_task(
        scope="casa",
        task_id=task_id,
        redirect_to=redirect_to,
        default_url="/tasks",
    )


@router.post("/tasks/{task_id}/delete")
def delete_task(task_id: str, redirect_to: str = Form("/tasks")):
    """Delete a task permanently in Casa storage."""
    return handle_delete_task(
        scope="casa",
        task_id=task_id,
        redirect_to=redirect_to,
        default_url="/tasks",
    )


@router.post("/tasks/archive-completed")
def archive_completed(redirect_to: str = Form("/tasks/completed")):
    """Archive completed tasks in Casa storage."""
    return handle_archive_completed(
        scope="casa",
        redirect_to=redirect_to,
        default_url="/tasks/completed",
    )


# ============================================================================
# Rutas Dinámicas de Tareas por Sección (/{section}/tasks)
# ============================================================================


@router.get("/{section}/tasks")
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


@router.get("/{section}/tasks/completed")
def section_completed_dashboard(section: str, request: Request):
    """Render completed tasks history view for given section."""
    return render_completed_dashboard(
        request,
        scope=section,
        base_url=f"/{section}/tasks",
    )


@router.post("/{section}/tasks/create")
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


@router.post("/{section}/tasks/{task_id}/edit")
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


@router.post("/{section}/tasks/{task_id}/toggle")
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


@router.post("/{section}/tasks/{task_id}/delete")
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


@router.post("/{section}/tasks/archive-completed")
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
