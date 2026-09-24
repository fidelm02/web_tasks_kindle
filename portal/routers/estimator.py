"""Rutas para el estimador de esfuerzo y análisis de tareas con IA."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from portal.services import effort_estimator, project_workflow

logger = logging.getLogger(__name__)

router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class AnalyzeEffortRequest(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = ""
    scope: str = "fidel"
    context: str = ""


class CreateFromEstimationRequest(BaseModel):
    title: str
    description: str = ""
    scope: str = "fidel"
    stage: str = "todo"
    priority: str = "Media"
    story_points: float | None = None
    estimated_hours: float | None = None
    subtasks: list[str] | list[dict[str, Any]] = []


@router.get("/estimator", response_class=HTMLResponse)
async def estimator_view(request: Request):
    """Renderiza la página del analizador y estimador de esfuerzo con IA."""
    sections = project_workflow.get_all_sections_info()
    return templates.TemplateResponse(
        request,
        "estimator.html",
        {
            "sections": sections,
            "active_tab": "estimator",
        },
    )


@router.post("/api/estimator/analyze")
async def api_analyze_effort(req: AnalyzeEffortRequest):
    """Analiza la tarea usando Gemini y devuelve complejidad, SP y desglose."""
    try:
        result = effort_estimator.estimate_task_effort(
            title=req.title,
            description=req.description,
            scope=req.scope,
            context=req.context,
        )
        return {"status": "ok", "estimation": result}
    except Exception as exc:
        logger.exception("Error al estimar esfuerzo: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


class AnalyzeExistingTaskRequest(BaseModel):
    task_id: str
    scope: str = "fidel"


class ApplyToTaskRequest(BaseModel):
    task_id: str
    scope: str = "fidel"
    story_points: float | None = None
    estimated_hours: float | None = None
    subtasks: list[str] | list[dict[str, Any]] = []
    summary: str = ""


class ConvertToRecurrentRequest(BaseModel):
    task_id: str
    scope: str = "fidel"
    frequency: str = "daily"
    days_of_week: list[int] | None = None
    interval_days: int = 1
    story_points: float | None = None


@router.post("/api/estimator/create-task")
async def api_create_from_estimation(req: CreateFromEstimationRequest):
    """Convierte la estimación en una tarea real en el tablero Kanban."""
    try:
        formatted_subtasks = []
        for item in req.subtasks:
            if isinstance(item, str):
                formatted_subtasks.append({"title": item, "done": False})
            elif isinstance(item, dict):
                formatted_subtasks.append(item)

        created = project_workflow.create_portal_task(
            title=req.title,
            description=req.description,
            priority=req.priority,
            stage=req.stage,
            scope=req.scope,
            story_points=req.story_points,
            estimated_hours=req.estimated_hours,
            subtasks=formatted_subtasks,
        )
        return {"status": "ok", "task": created}
    except Exception as exc:
        logger.exception("Error al crear tarea desde estimación: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/estimator/analyze-existing")
async def api_analyze_existing(req: AnalyzeExistingTaskRequest):
    """Analiza una tarea existente usando Gemini y evalúa viabilidad recurrente."""
    from app import storage

    tasks = storage.read_tasks(scope=req.scope)
    target = None
    for t in tasks:
        if t["id"] == req.task_id:
            target = t
            break

    if not target:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")

    estimation = effort_estimator.estimate_task_effort(
        title=target.get("title", ""),
        description=target.get("description", ""),
        scope=req.scope,
        context=f"Prioridad actual: {target.get('priority')}. Etapa: {target.get('stage', 'todo')}",
    )
    estimation["task_id"] = req.task_id
    estimation["current_stage"] = target.get("stage", "todo")
    estimation["current_priority"] = target.get("priority", "Media")
    return {"status": "ok", "estimation": estimation, "task": target}


@router.post("/api/estimator/apply-to-task")
async def api_apply_to_task(req: ApplyToTaskRequest):
    """Aplica los resultados del análisis IA a una tarea existente."""
    formatted_subtasks = []
    for item in req.subtasks:
        if isinstance(item, str):
            formatted_subtasks.append({"title": item, "done": False})
        elif isinstance(item, dict):
            formatted_subtasks.append(item)

    updated = project_workflow.update_portal_task(
        task_id=req.task_id,
        scope=req.scope,
        story_points=req.story_points,
        estimated_hours=req.estimated_hours,
        subtasks=formatted_subtasks,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return {"status": "ok", "task": updated}


@router.post("/api/estimator/convert-to-recurrent")
async def api_convert_to_recurrent(req: ConvertToRecurrentRequest):
    """Convierte una tarea existente en una regla de crones recurrentes."""
    from app import storage
    from portal.services import recurrent_engine

    tasks = storage.read_tasks(scope=req.scope)
    target = None
    for t in tasks:
        if t["id"] == req.task_id:
            target = t
            break

    if not target:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")

    rule = recurrent_engine.add_rule(
        title=target.get("title", "Tarea"),
        description=target.get("description", ""),
        scope=req.scope,
        priority=target.get("priority", "Media"),
        frequency=req.frequency,
        days_of_week=req.days_of_week or [0, 1, 2, 3, 4, 5, 6],
        interval_days=req.interval_days,
        story_points=req.story_points or target.get("story_points"),
    )
    return {"status": "ok", "rule": rule}

