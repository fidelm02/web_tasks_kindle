"""Rutas para el portal de Salud, Fitness, Hábitos y Programas Trimestrales."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from portal.services import health_service

logger = logging.getLogger(__name__)

router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class LogWeightRequest(BaseModel):
    profile_id: str = "fidel"
    weight: float = Field(..., gt=20, lt=300)
    date_str: str | None = None
    notes: str = ""


class ToggleHabitRequest(BaseModel):
    profile_id: str = "fidel"
    habit_type: str = "gym"  # "gym", "walk", "water"
    date_str: str | None = None


class UpdateProfileRequest(BaseModel):
    profile_id: str = "fidel"
    height_cm: float | None = None
    initial_weight: float | None = None
    target_weight: float | None = None
    weekly_gym_goal: int | None = None
    daily_walking_hours: float | None = None
    water_goal_liters: float | None = None


class GenerateAiProgramRequest(BaseModel):
    profile_id: str = "fidel"
    target_loss_kg: float = 8.0
    weeks: int = 12
    gym_days_available: int = 4
    diet_preferences: str = "Equilibrada con alta proteína"


class SyncRecurrentRequest(BaseModel):
    profile_id: str = "fidel"


@router.get("/health", response_class=HTMLResponse)
@router.get("/fitness", response_class=HTMLResponse)
async def health_dashboard_view(
    request: Request,
    profile: str = "fidel",
):
    """Renderiza el centro de mando de Salud, Fitness y Programas Trimestrales."""
    data = health_service.get_profile_data(profile_id=profile)
    return templates.TemplateResponse(
        request,
        "health.html",
        {
            "data": data,
            "current_profile": profile,
            "active_tab": "health",
        },
    )


@router.post("/api/health/weight")
async def api_log_weight(req: LogWeightRequest):
    """Registra una medición de peso."""
    try:
        new_entry = health_service.log_weight_entry(
            profile_id=req.profile_id,
            weight=req.weight,
            date_str=req.date_str,
            notes=req.notes,
        )
        profile_data = health_service.get_profile_data(profile_id=req.profile_id)
        return {
            "status": "ok",
            "entry": new_entry,
            "weight_stats": profile_data["weight_stats"],
        }
    except Exception as exc:
        logger.exception("Error al registrar peso: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/health/habit")
async def api_toggle_habit(req: ToggleHabitRequest):
    """Registra o desmarca el cumplimiento de un hábito diario (gym, caminata, agua)."""
    try:
        is_completed = health_service.toggle_habit(
            profile_id=req.profile_id,
            habit_type=req.habit_type,
            date_str=req.date_str,
        )
        profile_data = health_service.get_profile_data(profile_id=req.profile_id)
        return {
            "status": "ok",
            "is_completed": is_completed,
            "gym_stats": profile_data["gym_stats"],
        }
    except Exception as exc:
        logger.exception("Error al alternar hábito: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/health/profile/update")
async def api_update_profile(req: UpdateProfileRequest):
    """Actualiza metas y parámetros antropométricos del perfil."""
    try:
        data = health_service.get_health_data()
        profiles = data.setdefault("profiles", {})
        if req.profile_id not in profiles:
            raise HTTPException(status_code=404, detail="Perfil no encontrado")

        prof = profiles[req.profile_id]
        if req.height_cm is not None:
            prof["height_cm"] = req.height_cm
        if req.initial_weight is not None:
            prof["initial_weight"] = req.initial_weight
        if req.target_weight is not None:
            prof["target_weight"] = req.target_weight
        if req.weekly_gym_goal is not None:
            prof["weekly_gym_goal"] = req.weekly_gym_goal
        if req.daily_walking_hours is not None:
            prof["daily_walking_hours"] = req.daily_walking_hours
        if req.water_goal_liters is not None:
            prof["water_goal_liters"] = req.water_goal_liters

        health_service.save_health_data(data)
        return {"status": "ok", "profile": prof}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/health/program/ai-generate")
async def api_generate_program_ai(req: GenerateAiProgramRequest):
    """Genera un programa de 12 semanas (3 meses) usando Gemini 3.6 Flash."""
    try:
        prog = health_service.generate_ai_health_program(
            profile_id=req.profile_id,
            target_loss_kg=req.target_loss_kg,
            weeks=req.weeks,
            gym_days_available=req.gym_days_available,
            diet_preferences=req.diet_preferences,
        )
        return {"status": "ok", "program": prog}
    except Exception as exc:
        logger.exception("Error al generar programa con IA: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/health/program/sync-recurrent")
async def api_sync_recurrent_program(req: SyncRecurrentRequest):
    """Vincula los hábitos del programa a tareas recurrentes en el motor de crones."""
    try:
        res = health_service.sync_program_with_recurrent_rules(profile_id=req.profile_id)
        return res
    except Exception as exc:
        logger.exception("Error al sincronizar con crones: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
