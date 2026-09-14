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
    msg: str | None = None,
    err: str | None = None,
):
    """Render ClickUp sprint or backlog tasks for user Fidel.

    Args:
        request: FastAPI HTTP request instance.
        view: Active view identifier ('sprint' or 'backlog').
        msg: Optional success message.
        err: Optional error message.

    Returns:
        TemplateResponse: Rendered ClickUp view.
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
