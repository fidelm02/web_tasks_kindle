"""Router para integración con ClickUp (Sprint y Backlog)."""

from __future__ import annotations

import urllib.parse
from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.core.templates import templates
from app.services import clickup_service

router = APIRouter(tags=["clickup"])


@router.get("/clickup")
def clickup_dashboard(
    request: Request,
    view: str = "sprint",
    refresh: bool = False,
    msg: str | None = None,
    err: str | None = None,
):
    """Render ClickUp sprint or backlog tasks for user Fidel.

    Args:
        request: FastAPI HTTP request instance.
        view: Active view identifier ('sprint' or 'backlog').
        refresh: Whether to force fresh sprint detection and tasks query.
        msg: Optional success message.
        err: Optional error message.

    Returns:
        TemplateResponse: Rendered ClickUp view.
    """
    force_refresh = bool(refresh)
    if view == "backlog":
        list_name, tasks, error = clickup_service.get_backlog_tasks()
        active_list_id = clickup_service.get_backlog_list_id()
    else:
        view = "sprint"
        list_name, tasks, error = clickup_service.get_sprint_tasks(
            force_refresh=force_refresh
        )
        active_list_id = clickup_service.get_current_sprint_id()

    if force_refresh and not error and not msg:
        msg = f"Sincronización actualizada con ClickUp: {list_name}"

    raw_req_tasks = [t for t in tasks if t.get("is_req")]
    raw_dev_tasks = [t for t in tasks if not t.get("is_req")]

    req_tasks = clickup_service.sort_tasks_by_priority(raw_req_tasks)
    status_groups = clickup_service.group_tasks_by_status(raw_dev_tasks)
    available_statuses = clickup_service.get_available_statuses(active_list_id)
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


@router.post("/clickup/tasks/{task_id}/status")
def update_clickup_status(
    task_id: str,
    status: str = Form(...),
    redirect_to: str = Form("/clickup"),
):
    """Update status of a ClickUp task and redirect back.

    Args:
        task_id: Unique task identifier string.
        status: Target ClickUp status string.
        redirect_to: Return URL string.

    Returns:
        RedirectResponse: HTTP 303 redirect.
    """
    success, message = clickup_service.update_task_status(task_id, status)
    sep = "&" if "?" in redirect_to else "?"
    param = "msg" if success else "err"
    encoded_msg = urllib.parse.quote(message)
    dest_url = f"{redirect_to}{sep}{param}={encoded_msg}"
    return RedirectResponse(dest_url, status_code=303)


@router.get("/clickup/tasks/new")
def new_clickup_task_form(
    request: Request,
    view: str = "sprint",
    err: str | None = None,
):
    """Render standalone form to create a new ClickUp task.

    Args:
        request: FastAPI HTTP request instance.
        view: Active view identifier ('sprint' or 'backlog').
        err: Optional error message to display.

    Returns:
        TemplateResponse: Rendered task creation form.
    """
    sprint_id, sprint_name = clickup_service.get_current_sprint_info()
    backlog_id = clickup_service.get_backlog_list_id()

    return templates.TemplateResponse(
        request,
        "clickup_new_task.html",
        {
            "view": view,
            "sprint_id": sprint_id,
            "sprint_name": sprint_name,
            "backlog_id": backlog_id,
            "err": err,
        },
    )


@router.post("/clickup/tasks/create")
def create_clickup_task_action(
    name: str = Form(...),
    description: str = Form(""),
    story_points: str = Form(""),
    target_list: str = Form("sprint"),
    redirect_view: str = Form("sprint"),
):
    """Create a new ClickUp task with default status and assignee.

    Args:
        name: Task title from user input.
        description: Optional notes/description.
        story_points: Optional numeric story points.
        target_list: Target list identifier ('sprint' or 'backlog').
        redirect_view: View to redirect to after creation.

    Returns:
        RedirectResponse: HTTP 303 redirect.
    """
    if target_list == "backlog":
        list_id = clickup_service.get_backlog_list_id()
    else:
        list_id = clickup_service.get_current_sprint_id()

    sp_value: float | None = None
    sp_clean = story_points.strip()
    if sp_clean:
        try:
            sp_value = float(sp_clean)
        except ValueError:
            pass

    success, message, _ = clickup_service.create_clickup_task(
        list_id=list_id,
        name=name,
        description=description,
        story_points=sp_value,
        status="to do",
    )

    dest_view = redirect_view if redirect_view in ("sprint", "backlog") else "sprint"
    if success:
        encoded_msg = urllib.parse.quote(message)
        return RedirectResponse(
            f"/clickup?view={dest_view}&refresh=1&msg={encoded_msg}",
            status_code=303,
        )
    else:
        encoded_err = urllib.parse.quote(message)
        return RedirectResponse(
            f"/clickup/tasks/new?view={dest_view}&err={encoded_err}",
            status_code=303,
        )
