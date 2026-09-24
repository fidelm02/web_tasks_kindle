"""Gestor de flujos de trabajo, etapas y tableros estilo JIRA para tareas y proyectos."""

from __future__ import annotations

from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any
import uuid
from filelock import FileLock

from app import storage

logger = logging.getLogger(__name__)

STAGES = [
    {
        "id": "backlog",
        "name": "Backlog",
        "label": "Backlog",
        "color": "#64748b",
        "bg_color": "rgba(100, 116, 139, 0.12)",
        "icon": "inbox",
    },
    {
        "id": "todo",
        "name": "Por Hacer",
        "label": "Por Hacer",
        "color": "#3b82f6",
        "bg_color": "rgba(59, 130, 246, 0.12)",
        "icon": "circle",
    },
    {
        "id": "in_progress",
        "name": "En Progreso",
        "label": "En Progreso",
        "color": "#f59e0b",
        "bg_color": "rgba(245, 158, 11, 0.12)",
        "icon": "clock",
    },
    {
        "id": "review",
        "name": "En Revisión",
        "label": "En Revisión",
        "color": "#8b5cf6",
        "bg_color": "rgba(139, 92, 246, 0.12)",
        "icon": "eye",
    },
    {
        "id": "done",
        "name": "Completado",
        "label": "Completado",
        "color": "#10b981",
        "bg_color": "rgba(16, 185, 129, 0.12)",
        "icon": "check-circle",
    },
]

STAGE_IDS = [s["id"] for s in STAGES]


def _normalize_task_stage(task: dict[str, Any]) -> str:
    """Calcula la etapa canónica garantizando compatibilidad retroactiva con Kindle."""
    stage = task.get("stage")
    status = task.get("status", "pending")

    if stage in STAGE_IDS:
        return stage

    if status == "completed":
        return "done"
    if status == "in_progress":
        return "in_progress"
    if status == "review":
        return "review"
    if status == "backlog":
        return "backlog"
    return "todo"


def get_all_sections_info() -> list[dict[str, Any]]:
    """Carga todas las secciones / scopes disponibles."""
    base_dir = Path(__file__).resolve().parent.parent.parent
    sec_file = base_dir / "data" / "sections.json"
    if sec_file.exists():
        try:
            with open(sec_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("sections", [])
        except Exception as exc:
            logger.error("Error al cargar secciones: %s", exc)
    return [
        {"id": "fidel", "name": "Fidel", "icon": "zap"},
        {"id": "casa", "name": "Casa", "icon": "home"},
        {"id": "lau", "name": "Lau", "icon": "heart"},
    ]


def get_kanban_board(
    scope: str = "fidel",
    search: str = "",
    priority: str = "",
) -> dict[str, Any]:
    """Construye los datos completos del tablero Kanban agrupados por columnas."""
    all_sections = get_all_sections_info()
    valid_scopes = [s["id"] for s in all_sections]

    if scope == "all":
        tasks_pool = []
        for s_id in valid_scopes:
            for t in storage.read_tasks(scope=s_id):
                t_copy = dict(t)
                t_copy["scope"] = s_id
                tasks_pool.append(t_copy)
    else:
        actual_scope = scope if scope in valid_scopes else "fidel"
        raw_tasks = storage.read_tasks(scope=actual_scope)
        tasks_pool = []
        for t in raw_tasks:
            t_copy = dict(t)
            t_copy["scope"] = actual_scope
            tasks_pool.append(t_copy)

    # Filtrar archivadas
    active_tasks = [t for t in tasks_pool if t.get("status") != "archived"]

    # Búsqueda por texto
    if search:
        q = search.lower().strip()
        active_tasks = [
            t
            for t in active_tasks
            if q in (t.get("title") or "").lower()
            or q in (t.get("description") or "").lower()
        ]

    # Filtro por prioridad
    if priority and priority != "all":
        active_tasks = [
            t for t in active_tasks if (t.get("priority") or "").lower() == priority.lower()
        ]

    # Agrupar por columnas
    columns: dict[str, list[dict[str, Any]]] = {s_id: [] for s_id in STAGE_IDS}
    total_sp = 0.0
    done_sp = 0.0

    for t in active_tasks:
        stage = _normalize_task_stage(t)
        t["stage"] = stage
        sp = t.get("story_points")
        try:
            sp_val = float(sp) if sp is not None else 0.0
        except (ValueError, TypeError):
            sp_val = 0.0
        t["story_points_val"] = sp_val

        total_sp += sp_val
        if stage == "done":
            done_sp += sp_val

        # Subtasks conteo
        subtasks = t.get("subtasks", [])
        if isinstance(subtasks, list):
            completed_sub = sum(1 for st in subtasks if isinstance(st, dict) and st.get("done"))
            t["subtasks_count"] = len(subtasks)
            t["subtasks_completed"] = completed_sub
        else:
            t["subtasks_count"] = 0
            t["subtasks_completed"] = 0

        columns[stage].append(t)

    # Resumen general
    stats = {
        "total_tasks": len(active_tasks),
        "total_story_points": round(total_sp, 1),
        "completed_story_points": round(done_sp, 1),
        "progress_percent": round((done_sp / total_sp * 100), 1) if total_sp > 0 else 0,
        "counts_by_stage": {s_id: len(tasks) for s_id, tasks in columns.items()},
        "sp_by_stage": {
            s_id: round(sum(t.get("story_points_val", 0) for t in tasks), 1)
            for s_id, tasks in columns.items()
        },
    }

    return {
        "scope": scope,
        "sections": all_sections,
        "stages": STAGES,
        "columns": columns,
        "stats": stats,
    }


def move_task_stage(
    task_id: str,
    target_stage: str,
    scope: str = "fidel",
) -> dict[str, Any] | None:
    """Mueve una tarea a una nueva etapa de trabajo sincronizando con el estado de Kindle."""
    if target_stage not in STAGE_IDS:
        raise ValueError(f"Etapa inválida: {target_stage}")

    db_path, lock_path = storage._get_paths(scope)
    storage._ensure_db_exists(scope)

    with FileLock(lock_path):
        tasks = storage.read_tasks(scope)
        target_task = None
        for t in tasks:
            if t["id"] == task_id:
                target_task = t
                break

        if not target_task:
            return None

        target_task["stage"] = target_stage
        target_task["updated_at"] = datetime.now().isoformat()

        if target_stage == "done":
            target_task["status"] = "completed"
            if not target_task.get("completed_at"):
                target_task["completed_at"] = datetime.now().isoformat()
        else:
            target_task["status"] = "pending"
            target_task["completed_at"] = None

        storage._write_tasks_atomic(tasks, scope)
        return target_task


def create_portal_task(
    title: str,
    description: str = "",
    priority: str = "Media",
    stage: str = "todo",
    scope: str = "fidel",
    story_points: float | None = None,
    estimated_hours: float | None = None,
    target_date: str | None = None,
    subtasks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Crea una tarea extendida con soporte para Story Points, etapas y subtareas."""
    db_path, lock_path = storage._get_paths(scope)
    storage._ensure_db_exists(scope)

    if stage not in STAGE_IDS:
        stage = "todo"

    now_iso = datetime.now().isoformat()
    status = "completed" if stage == "done" else "pending"

    new_task = {
        "id": str(uuid.uuid4()),
        "title": title.strip(),
        "description": (description or "").strip(),
        "priority": priority,
        "stage": stage,
        "status": status,
        "scope": scope,
        "story_points": float(story_points) if story_points is not None and story_points != "" else None,
        "estimated_hours": float(estimated_hours) if estimated_hours is not None and estimated_hours != "" else None,
        "target_date": target_date or None,
        "subtasks": subtasks or [],
        "created_at": now_iso,
        "updated_at": now_iso,
        "completed_at": now_iso if stage == "done" else None,
    }

    with FileLock(lock_path):
        tasks = storage.read_tasks(scope)
        tasks.append(new_task)
        storage._write_tasks_atomic(tasks, scope)

    return new_task


def update_portal_task(
    task_id: str,
    scope: str = "fidel",
    **fields: Any,
) -> dict[str, Any] | None:
    """Actualiza propiedades extendidas de una tarea existente."""
    db_path, lock_path = storage._get_paths(scope)
    storage._ensure_db_exists(scope)

    with FileLock(lock_path):
        tasks = storage.read_tasks(scope)
        target = None
        for t in tasks:
            if t["id"] == task_id:
                target = t
                break

        if not target:
            return None

        # Actualizar campos permitidos
        for key in ["title", "description", "priority", "target_date", "story_points", "estimated_hours", "subtasks"]:
            if key in fields:
                val = fields[key]
                if key in ("story_points", "estimated_hours"):
                    try:
                        target[key] = float(val) if val is not None and val != "" else None
                    except (ValueError, TypeError):
                        pass
                elif key == "title":
                    target[key] = str(val).strip()
                else:
                    target[key] = val

        if "stage" in fields and fields["stage"] in STAGE_IDS:
            new_stage = fields["stage"]
            target["stage"] = new_stage
            if new_stage == "done":
                target["status"] = "completed"
                if not target.get("completed_at"):
                    target["completed_at"] = datetime.now().isoformat()
            else:
                target["status"] = "pending"
                target["completed_at"] = None

        target["updated_at"] = datetime.now().isoformat()
        storage._write_tasks_atomic(tasks, scope)
        return target
