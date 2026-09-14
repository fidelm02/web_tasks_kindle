"""Router para el portal de inicio y administración de proyectos."""

from __future__ import annotations

from typing import Any
import urllib.parse
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from app import storage
from app.core.helpers import safe_redirect
from app.core.templates import templates
from app.services import reader_service, section_service

router = APIRouter(tags=["home"])


@router.get("/")
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


@router.get("/sections/status/{status}")
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


@router.post("/sections/{section_id}/status")
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
        dest = safe_redirect(redirect_to, "/")
        sep = "&" if "?" in dest else "?"
        return RedirectResponse(f"{dest}{sep}msg={encoded}", status_code=303)

    encoded = urllib.parse.quote(
        "No se pudo cambiar el estado de la sección."
    )
    dest = safe_redirect(redirect_to, "/")
    sep = "&" if "?" in dest else "?"
    return RedirectResponse(f"{dest}{sep}err={encoded}", status_code=303)


@router.get("/sections/new")
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


@router.post("/sections/create")
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
