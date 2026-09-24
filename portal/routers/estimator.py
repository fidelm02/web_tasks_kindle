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


@router.post("/api/estimator/create-task")
async def api_create_from_estimation(req: CreateFromEstimationRequest):
    """Convierte la estimación en una tarea real en el tablero Kanban."""
    try:
        # Formatear subtareas en objetos de lista de verificación
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
