"""Motor de tareas recurrentes y crones automáticos con deduplicación atómica."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
import logging
import os
from pathlib import Path
import re
from typing import Any
import uuid
from filelock import FileLock

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_DATA_DIR = _BASE_DIR / "data"
_RULES_FILE = _DATA_DIR / "recurrent_tasks.json"
_LOCK_FILE = _DATA_DIR / "recurrent_tasks.json.lock"


def _ensure_files():
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not _RULES_FILE.exists():
        initial_rules = [
            {
                "id": str(uuid.uuid4()),
                "title": "Arena Cece",
                "description": "Limpieza y mantenimiento de la arena sanitaria de Cece.",
                "scope": "fidel",
                "priority": "Media",
                "frequency": "daily",
                "days_of_week": [0, 1, 2, 3, 4, 5, 6],
                "interval_days": 1,
                "story_points": 1.0,
                "enabled": True,
                "last_generated_at": None,
                "created_at": datetime.now().isoformat(),
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Jugar con Cece",
                "description": "Tiempo diario de juego y enriquecimiento con Cece.",
                "scope": "fidel",
                "priority": "Alta",
                "frequency": "daily",
                "days_of_week": [0, 1, 2, 3, 4, 5, 6],
                "interval_days": 1,
                "story_points": 1.0,
                "enabled": True,
                "last_generated_at": None,
                "created_at": datetime.now().isoformat(),
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Ir al gym",
                "description": "Sesión de entrenamiento y salud física.",
                "scope": "fidel",
                "priority": "Media",
                "frequency": "weekdays",
                "days_of_week": [0, 1, 2, 3, 4],
                "interval_days": 1,
                "story_points": 2.0,
                "enabled": True,
                "last_generated_at": None,
                "created_at": datetime.now().isoformat(),
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Lavar ropa",
                "description": "Ciclo de lavado y secado semanal del hogar.",
                "scope": "fidel",
                "priority": "Media",
                "frequency": "custom_days",
                "days_of_week": [2, 6],  # Miércoles y Domingo
                "interval_days": 1,
                "story_points": 2.0,
                "enabled": True,
                "last_generated_at": None,
                "created_at": datetime.now().isoformat(),
            },
        ]
        with open(_RULES_FILE, "w", encoding="utf-8") as f:
            json.dump({"rules": initial_rules}, f, ensure_ascii=False, indent=2)


def get_all_rules() -> list[dict[str, Any]]:
    """Carga todas las reglas de recurrencia registradas."""
    _ensure_files()
    with FileLock(str(_LOCK_FILE), timeout=5):
        try:
            with open(_RULES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("rules", [])
        except Exception as exc:
            logger.error("Error al leer reglas de recurrencia: %s", exc)
            return []


def save_all_rules(rules: list[dict[str, Any]]) -> None:
    """Guarda atómicamente la lista de reglas de recurrencia."""
    _ensure_files()
    with FileLock(str(_LOCK_FILE), timeout=5):
        with open(_RULES_FILE, "w", encoding="utf-8") as f:
            json.dump({"rules": rules}, f, ensure_ascii=False, indent=2)


def add_rule(
    title: str,
    description: str = "",
    scope: str = "fidel",
    priority: str = "Media",
    frequency: str = "daily",
    days_of_week: list[int] | None = None,
    interval_days: int = 1,
    story_points: float | None = None,
) -> dict[str, Any]:
    """Crea una nueva regla de recurrencia."""
    rules = get_all_rules()
    new_rule = {
        "id": str(uuid.uuid4()),
        "title": title.strip(),
        "description": description.strip(),
        "scope": (scope or "fidel").lower().strip(),
        "priority": priority,
        "frequency": frequency,
        "days_of_week": days_of_week if days_of_week is not None else [0, 1, 2, 3, 4, 5, 6],
        "interval_days": max(1, int(interval_days or 1)),
        "story_points": float(story_points) if story_points is not None and story_points != "" else None,
        "enabled": True,
        "last_generated_at": None,
        "created_at": datetime.now().isoformat(),
    }
    rules.append(new_rule)
    save_all_rules(rules)
    return new_rule


def toggle_rule(rule_id: str) -> bool:
    """Activa o pausa una regla de recurrencia."""
    rules = get_all_rules()
    updated = False
    for r in rules:
        if r.get("id") == rule_id:
            r["enabled"] = not r.get("enabled", True)
            updated = True
            break
    if updated:
        save_all_rules(rules)
    return updated


def delete_rule(rule_id: str) -> bool:
    """Elimina una regla de recurrencia."""
    rules = get_all_rules()
    initial_len = len(rules)
    rules = [r for r in rules if r.get("id") != rule_id]
    if len(rules) < initial_len:
        save_all_rules(rules)
        return True
    return False


def update_rule(
    rule_id: str,
    title: str | None = None,
    description: str | None = None,
    scope: str | None = None,
    priority: str | None = None,
    frequency: str | None = None,
    days_of_week: list[int] | None = None,
    interval_days: int | None = None,
    story_points: float | None = None,
) -> dict[str, Any] | None:
    """Actualiza la configuración de una regla recurrente existente."""
    rules = get_all_rules()
    target_rule = None
    for r in rules:
        if r.get("id") == rule_id:
            target_rule = r
            break

    if not target_rule:
        return None

    if title is not None:
        target_rule["title"] = title.strip()
    if description is not None:
        target_rule["description"] = description.strip()
    if scope is not None:
        target_rule["scope"] = (scope or "fidel").lower().strip()
    if priority is not None:
        target_rule["priority"] = priority
    if frequency is not None:
        target_rule["frequency"] = frequency
    if days_of_week is not None:
        target_rule["days_of_week"] = days_of_week
    if interval_days is not None:
        target_rule["interval_days"] = max(1, int(interval_days))
    if story_points is not None:
        target_rule["story_points"] = (
            float(story_points) if story_points != "" else None
        )

    target_rule["updated_at"] = datetime.now().isoformat()
    save_all_rules(rules)
    return target_rule



def _normalize_text(text: str) -> str:
    """Normaliza texto para comparaciones de deduplicación."""
    cleaned = (text or "").lower().strip()
    return re.sub(r"\s+", " ", cleaned)


def is_rule_due(rule: dict[str, Any], check_date: date) -> bool:
    """Determina si una regla debe ejecutarse en la fecha objetivo."""
    if not rule.get("enabled", True):
        return False

    frequency = rule.get("frequency", "daily")
    weekday = check_date.weekday()  # 0=Lunes, 6=Domingo

    if frequency == "daily":
        return True

    if frequency == "weekdays":
        return weekday in (0, 1, 2, 3, 4)

    if frequency == "custom_days":
        allowed_days = rule.get("days_of_week", [])
        return weekday in allowed_days

    if frequency == "interval_days":
        interval = max(1, int(rule.get("interval_days", 1)))
        last_gen_str = rule.get("last_generated_at")
        if not last_gen_str:
            return True
        try:
            last_date = datetime.fromisoformat(last_gen_str).date()
            return (check_date - last_date).days >= interval
        except Exception:
            return True

    return True


def evaluate_and_generate(target_date: date | None = None) -> dict[str, Any]:
    """Evalúa las reglas activas y genera tareas evitando duplicaciones.

    Comprueba si ya existe una tarea con el mismo título en el scope objetivo
    que esté pendiente o que tenga la misma fecha objetivo. Si existe, no se crea.

    Args:
        target_date: Fecha a evaluar (por defecto la fecha actual).

    Returns:
        dict[str, Any]: Resumen de tareas generadas, omitidas y evaluadas.
    """
    check_date = target_date or date.today()
    check_date_str = check_date.isoformat()

    rules = get_all_rules()
    generated_tasks: list[dict[str, Any]] = []
    skipped_tasks: list[dict[str, Any]] = []

    # Importar storage del núcleo del sistema
    try:
        from app import storage
    except ImportError:
        import sys
        sys.path.append(str(_BASE_DIR))
        from app import storage

    rules_updated = False

    for rule in rules:
        if not is_rule_due(rule, check_date):
            continue

        scope = rule.get("scope", "fidel")
        norm_title = _normalize_text(rule.get("title", ""))

        # Leer tareas existentes en el scope
        existing_tasks = storage.read_tasks(scope=scope)

        # Regla de no duplicación:
        # 1. Ya existe una tarea con ese nombre que esté pendiente/en progreso
        # 2. O ya existe una tarea con ese nombre programada para la misma fecha (aunque esté completada hoy)
        duplicate = None
        for t in existing_tasks:
            t_norm = _normalize_text(t.get("title", ""))
            if t_norm == norm_title:
                is_pending = t.get("status") in ("pending", "to do", "in_progress")
                is_same_date = str(t.get("target_date") or "").startswith(check_date_str)
                if is_pending or is_same_date:
                    duplicate = t
                    break

        if duplicate:
            skipped_tasks.append(
                {
                    "rule_id": rule.get("id"),
                    "title": rule.get("title"),
                    "scope": scope,
                    "reason": f"Ya existe una tarea activa o registrada para hoy ({duplicate.get('status')})",
                }
            )
            continue

        # Crear la tarea con soporte para Story Points y etapa Por Hacer
        try:
            from portal.services.project_workflow import create_portal_task

            created = create_portal_task(
                title=rule.get("title", "Tarea Recurrente"),
                description=rule.get("description", ""),
                priority=rule.get("priority", "Media"),
                stage="todo",
                scope=scope,
                story_points=rule.get("story_points"),
                target_date=check_date_str,
            )

            rule["last_generated_at"] = datetime.now().isoformat()
            rules_updated = True

            generated_tasks.append(
                {
                    "id": created.get("id"),
                    "title": created.get("title"),
                    "scope": scope,
                    "target_date": check_date_str,
                    "priority": created.get("priority"),
                    "story_points": rule.get("story_points"),
                }
            )
        except Exception as exc:
            logger.error("Error al crear tarea recurrente '%s': %s", rule.get("title"), exc)

    if rules_updated:
        save_all_rules(rules)

    return {
        "date": check_date_str,
        "evaluated_rules": len(rules),
        "generated_count": len(generated_tasks),
        "skipped_count": len(skipped_tasks),
        "generated": generated_tasks,
        "skipped": skipped_tasks,
    }
