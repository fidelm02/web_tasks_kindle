"""Rutas para la gestión del motor de tareas recurrentes y crones."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from portal.services import recurrent_engine

logger = logging.getLogger(__name__)

router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class CreateRuleRequest(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = ""
    scope: str = "fidel"
    priority: str = "Media"
    frequency: str = "daily"  # daily, weekdays, custom_days, interval_days
    days_of_week: list[int] | None = None
    interval_days: int = 1
    story_points: float | None = None


@router.get("/recurrent", response_class=HTMLResponse)
async def recurrent_view(request: Request):
    """Renderiza el panel de control de tareas recurrentes y crones."""
    rules = recurrent_engine.get_all_rules()
    return templates.TemplateResponse(
        request,
        "recurrent.html",
        {
            "rules": rules,
            "active_tab": "recurrent",
        },
    )


@router.get("/api/recurrent/rules")
async def api_get_rules():
    """Retorna la lista completa de reglas de recurrencia en JSON."""
    return {"rules": recurrent_engine.get_all_rules()}


@router.post("/api/recurrent/rules")
async def api_create_rule(req: CreateRuleRequest):
    """Crea una nueva regla de tarea recurrente."""
    try:
        new_rule = recurrent_engine.add_rule(
            title=req.title,
            description=req.description,
            scope=req.scope,
            priority=req.priority,
            frequency=req.frequency,
            days_of_week=req.days_of_week,
            interval_days=req.interval_days,
            story_points=req.story_points,
        )
        return {"status": "ok", "rule": new_rule}
    except Exception as exc:
        logger.exception("Error al crear regla de recurrencia: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/recurrent/rules/{rule_id}/toggle")
async def api_toggle_rule(rule_id: str):
    """Pausa o activa una regla de recurrencia."""
    updated = recurrent_engine.toggle_rule(rule_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Regla no encontrada")
    return {"status": "ok", "rule_id": rule_id}


@router.post("/api/recurrent/rules/{rule_id}/delete")
async def api_delete_rule(rule_id: str):
    """Elimina una regla de recurrencia."""
    deleted = recurrent_engine.delete_rule(rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Regla no encontrada")
    return {"status": "ok", "rule_id": rule_id}


@router.post("/api/recurrent/run-now")
async def api_run_crons_now():
    """Ejecuta inmediatamente el motor de crones con deduplicación."""
    try:
        result = recurrent_engine.evaluate_and_generate()
        return {"status": "ok", "result": result}
    except Exception as exc:
        logger.exception("Error al ejecutar crones manualmente: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
