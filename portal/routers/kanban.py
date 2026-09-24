"""Rutas para el tablero Kanban estilo Jira."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app import storage
from portal.services import project_workflow

logger = logging.getLogger(__name__)

router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class MoveStageRequest(BaseModel):
    task_id: str
    target_stage: str
    scope: str = "fidel"


class CreateTaskRequest(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = ""
    priority: str = "Media"
    stage: str = "todo"
    scope: str = "fidel"
    story_points: float | None = None
    estimated_hours: float | None = None
    target_date: str | None = None
    subtasks: list[dict[str, Any]] | None = None


class UpdateTaskRequest(BaseModel):
    task_id: str
    scope: str = "fidel"
    title: str | None = None
    description: str | None = None
    priority: str | None = None
    stage: str | None = None
    story_points: float | None = None
    estimated_hours: float | None = None
    target_date: str | None = None
    subtasks: list[dict[str, Any]] | None = None


class DeleteTaskRequest(BaseModel):
    task_id: str
    scope: str = "fidel"


class ToggleSubtaskRequest(BaseModel):
    task_id: str
    scope: str = "fidel"
    subtask_index: int


@router.get("/", response_class=HTMLResponse)
@router.get("/kanban", response_class=HTMLResponse)
async def kanban_view(
    request: Request,
    scope: str = "fidel",
    search: str = "",
    priority: str = "",
):
    """Renderiza el tablero Kanban interactivo."""
    board_data = project_workflow.get_kanban_board(
        scope=scope,
        search=search,
        priority=priority,
    )
    return templates.TemplateResponse(
        request,
        "kanban.html",
        {
            "board": board_data,
            "current_scope": scope,
            "search_query": search,
            "current_priority": priority,
            "active_tab": "kanban",
        },
    )


@router.post("/api/tasks/move")
async def api_move_stage(req: MoveStageRequest):
    """Mueve una tarea de etapa."""
    try:
        updated = project_workflow.move_task_stage(
            task_id=req.task_id,
            target_stage=req.target_stage,
            scope=req.scope,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Tarea no encontrada")
        return {"status": "ok", "task": updated}
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as exc:
        logger.exception("Error al mover etapa de tarea: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/tasks/create")
async def api_create_task(req: CreateTaskRequest):
    """Crea una nueva tarea con soporte de etapas y estimaciones."""
    try:
        created = project_workflow.create_portal_task(
            title=req.title,
            description=req.description,
            priority=req.priority,
            stage=req.stage,
            scope=req.scope,
            story_points=req.story_points,
            estimated_hours=req.estimated_hours,
            target_date=req.target_date,
            subtasks=req.subtasks,
        )
        return {"status": "ok", "task": created}
    except Exception as exc:
        logger.exception("Error al crear tarea en portal: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/tasks/update")
async def api_update_task(req: UpdateTaskRequest):
    """Actualiza una tarea existente."""
    fields = req.model_dump(exclude_unset=True, exclude={"task_id", "scope"})
    updated = project_workflow.update_portal_task(
        task_id=req.task_id,
        scope=req.scope,
        **fields,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return {"status": "ok", "task": updated}


@router.post("/api/tasks/delete")
async def api_delete_task(req: DeleteTaskRequest):
    """Elimina permanentemente una tarea."""
    try:
        storage.delete_task(req.task_id, scope=req.scope)
        return {"status": "ok", "deleted_id": req.task_id}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/tasks/toggle-subtask")
async def api_toggle_subtask(req: ToggleSubtaskRequest):
    """Marca o desmarca una subtarea como completada."""
    tasks = storage.read_tasks(scope=req.scope)
    target = None
    for t in tasks:
        if t["id"] == req.task_id:
            target = t
            break

    if not target:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")

    subtasks = target.get("subtasks", [])
    if 0 <= req.subtask_index < len(subtasks):
        item = subtasks[req.subtask_index]
        if isinstance(item, dict):
            item["done"] = not item.get("done", False)
        elif isinstance(item, str):
            subtasks[req.subtask_index] = {"title": item, "done": True}
        project_workflow.update_portal_task(
            task_id=req.task_id,
            scope=req.scope,
            subtasks=subtasks,
        )
        return {"status": "ok", "subtasks": subtasks}
    raise HTTPException(status_code=400, detail="Índice de subtarea fuera de rango")
