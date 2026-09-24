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
        t["code"] = format_task_code(t, t.get("scope", "fidel"))
        t["google_cal_url"] = generate_google_calendar_url(t)
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


def format_task_code(task: dict[str, Any], scope: str) -> str:
    """Genera o recupera un identificador humano único y corto (ej. FID-4A1B)."""
    if task.get("code"):
        return task["code"]
    scope_clean = (scope or "FID").upper()
    prefix = "REF" if ("PROYECTO" in scope_clean or "REFORMA" in scope_clean) else scope_clean[:3]
    short_hash = "".join(c for c in str(task.get("id", "")) if c.isalnum())[:4].upper()
    code = f"{prefix}-{short_hash or '01'}"
    task["code"] = code
    return code


def generate_google_calendar_url(task: dict[str, Any]) -> str:
    """Genera URL directa para bloquear tiempo en Google Calendar con un solo clic."""
    import urllib.parse

    code = task.get("code") or format_task_code(task, task.get("scope", "fidel"))
    title = f"[{code}] {task.get('title', 'Tarea')}"
    target_date = task.get("target_date")
    start_time = task.get("start_time") or "09:00"
    end_time = task.get("end_time") or "10:30"

    if target_date:
        d_clean = target_date.replace("-", "")
        st_clean = start_time.replace(":", "") + "00"
        et_clean = end_time.replace(":", "") + "00"
        dates_param = f"{d_clean}T{st_clean}/{d_clean}T{et_clean}"
    else:
        now = datetime.now()
        d_clean = now.strftime("%Y%m%d")
        dates_param = f"{d_clean}T090000/{d_clean}T103000"

    subtasks_text = ""
    for st in task.get("subtasks", []):
        st_title = st.get("title") if isinstance(st, dict) else str(st)
        subtasks_text += f"\n- [ ] {st_title}"

    details = (
        f"Código: {code}\n"
        f"Proyecto / Scope: {task.get('scope')}\n"
        f"Prioridad: {task.get('priority')}\n"
        f"Story Points: {task.get('story_points') or 'N/A'}\n"
        f"Horas Estimadas: {task.get('estimated_hours') or 'N/A'}h\n\n"
        f"Descripción:\n{task.get('description', '')}\n"
        f"{f'Subtareas:{subtasks_text}' if subtasks_text else ''}"
    )

    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": dates_param,
        "details": details,
    }
    return f"https://calendar.google.com/calendar/render?{urllib.parse.urlencode(params)}"


def create_portal_task(
    title: str,
    description: str = "",
    priority: str = "Media",
    stage: str = "todo",
    scope: str = "fidel",
    story_points: float | None = None,
    estimated_hours: float | None = None,
    target_date: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    subtasks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Crea una tarea extendida con soporte para Story Points, etapas, bloqueo de tiempo y subtareas."""
    db_path, lock_path = storage._get_paths(scope)
    storage._ensure_db_exists(scope)

    if stage not in STAGE_IDS:
        stage = "todo"

    now_iso = datetime.now().isoformat()
    status = "completed" if stage == "done" else "pending"
    task_id = str(uuid.uuid4())

    new_task = {
        "id": task_id,
        "code": None,  # Se asigna abajo
        "title": title.strip(),
        "description": (description or "").strip(),
        "priority": priority,
        "stage": stage,
        "status": status,
        "scope": scope,
        "story_points": float(story_points) if story_points is not None and story_points != "" else None,
        "estimated_hours": float(estimated_hours) if estimated_hours is not None and estimated_hours != "" else None,
        "target_date": target_date or None,
        "start_time": start_time or None,
        "end_time": end_time or None,
        "subtasks": subtasks or [],
        "created_at": now_iso,
        "updated_at": now_iso,
        "completed_at": now_iso if stage == "done" else None,
    }
    new_task["code"] = format_task_code(new_task, scope)

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
        for key in [
            "title",
            "description",
            "priority",
            "target_date",
            "start_time",
            "end_time",
            "story_points",
            "estimated_hours",
            "subtasks",
        ]:
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

        if not target.get("code"):
            target["code"] = format_task_code(target, scope)

        target["updated_at"] = datetime.now().isoformat()
        storage._write_tasks_atomic(tasks, scope)
        return target


def get_table_data(
    scope: str = "fidel",
    search: str = "",
    priority: str = "",
    stage: str = "",
    sort_by: str = "created_at",
    order: str = "desc",
) -> dict[str, Any]:
    """Prepara la lista tabular estructurada de tareas para la vista de Tabla/Lista."""
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
        tasks_pool = []
        for t in storage.read_tasks(scope=actual_scope):
            t_copy = dict(t)
            t_copy["scope"] = actual_scope
            tasks_pool.append(t_copy)

    # Filtrar archivadas
    active = [t for t in tasks_pool if t.get("status") != "archived"]

    # Procesar campos derivados
    for t in active:
        t["stage"] = _normalize_task_stage(t)
        t["code"] = format_task_code(t, t.get("scope", "fidel"))
        t["google_cal_url"] = generate_google_calendar_url(t)

        subtasks = t.get("subtasks", [])
        if isinstance(subtasks, list):
            completed_count = sum(1 for st in subtasks if isinstance(st, dict) and st.get("done"))
            t["subtasks_count"] = len(subtasks)
            t["subtasks_completed"] = completed_count
        else:
            t["subtasks_count"] = 0
            t["subtasks_completed"] = 0

    # Filtros
    if search:
        q = search.lower().strip()
        active = [
            t
            for t in active
            if q in (t.get("title") or "").lower()
            or q in (t.get("description") or "").lower()
            or q in (t.get("code") or "").lower()
        ]

    if priority and priority != "all":
        active = [t for t in active if (t.get("priority") or "").lower() == priority.lower()]

    if stage and stage != "all":
        allowed_stages = {s.strip().lower() for s in stage.split(",") if s.strip()}
        active = [t for t in active if t.get("stage") in allowed_stages]

    # Ordenamiento por cualquier columna
    reverse = order.lower() == "desc"
    stage_rank = {"backlog": 1, "todo": 2, "in_progress": 3, "review": 4, "done": 5}
    prio_order = {"urgente": 4, "alta": 3, "media": 2, "baja": 1}

    if sort_by == "priority":
        active.sort(key=lambda t: prio_order.get((t.get("priority") or "").lower(), 0), reverse=reverse)
    elif sort_by in ("story_points", "sp"):
        active.sort(key=lambda t: float(t.get("story_points") or 0), reverse=reverse)
    elif sort_by in ("estimated_hours", "hours"):
        active.sort(key=lambda t: float(t.get("estimated_hours") or 0), reverse=reverse)
    elif sort_by == "stage":
        active.sort(key=lambda t: stage_rank.get(t.get("stage", "todo"), 2), reverse=reverse)
    elif sort_by == "code":
        active.sort(key=lambda t: (t.get("code") or "").lower(), reverse=reverse)
    elif sort_by == "scope":
        active.sort(key=lambda t: (t.get("scope") or "").lower(), reverse=reverse)
    elif sort_by in ("target_date", "date"):
        def date_sort_key(t):
            d = t.get("target_date")
            tm = t.get("start_time") or ""
            if not d:
                return (0, "") if reverse else (1, "9999-99-99")
            return (1, f"{d} {tm}") if reverse else (0, f"{d} {tm}")
        active.sort(key=date_sort_key, reverse=reverse)
    elif sort_by == "subtasks":
        active.sort(key=lambda t: (t.get("subtasks_count") or 0, t.get("subtasks_completed") or 0), reverse=reverse)
    elif sort_by == "title":
        active.sort(key=lambda t: (t.get("title") or "").lower(), reverse=reverse)
    else:
        active.sort(key=lambda t: t.get("created_at") or "", reverse=reverse)

    return {
        "scope": scope,
        "sections": all_sections,
        "stages": STAGES,
        "tasks": active,
        "total_count": len(active),
        "total_sp": round(sum(float(t.get("story_points") or 0) for t in active), 1),
    }


def get_calendar_data(
    scope: str = "fidel",
    year: int | None = None,
    month: int | None = None,
) -> dict[str, Any]:
    """Construye la estructura de eventos y time blocking para la vista de Calendario y Gantt."""
    import calendar as pycalendar

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
        tasks_pool = []
        for t in storage.read_tasks(scope=actual_scope):
            t_copy = dict(t)
            t_copy["scope"] = actual_scope
            tasks_pool.append(t_copy)

    now = datetime.now()
    cur_year = year or now.year
    cur_month = month or now.month

    # Asegurar códigos y urls
    scheduled_tasks: list[dict[str, Any]] = []
    unscheduled_tasks: list[dict[str, Any]] = []

    for t in tasks_pool:
        if t.get("status") == "archived":
            continue
        t["stage"] = _normalize_task_stage(t)
        t["code"] = format_task_code(t, t.get("scope", "fidel"))
        t["google_cal_url"] = generate_google_calendar_url(t)

        t_date = t.get("target_date")
        if t_date:
            scheduled_tasks.append(t)
        else:
            unscheduled_tasks.append(t)

    # Matriz del mes
    cal = pycalendar.Calendar(firstweekday=0)  # Lunes primero
    month_days = cal.monthdays2calendar(cur_year, cur_month)  # semanas con (dia, weekday)

    # Agrupar tareas por fecha ISO "YYYY-MM-DD"
    events_by_date: dict[str, list[dict[str, Any]]] = {}
    for t in scheduled_tasks:
        d_str = str(t.get("target_date") or "").split("T")[0]
        events_by_date.setdefault(d_str, []).append(t)

    # Construir semanas con eventos
    weeks = []
    for week in month_days:
        week_days = []
        for day, wday in week:
            if day == 0:
                week_days.append({"day": 0, "date_str": None, "is_current_month": False, "tasks": []})
            else:
                date_str = f"{cur_year:04d}-{cur_month:02d}-{day:02d}"
                week_days.append(
                    {
                        "day": day,
                        "date_str": date_str,
                        "is_current_month": True,
                        "is_today": (date_str == now.strftime("%Y-%m-%d")),
                        "tasks": events_by_date.get(date_str, []),
                    }
                )
        weeks.append(week_days)

    month_name = pycalendar.month_name[cur_month]
    meses_es = [
        "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
    ]

    return {
        "scope": scope,
        "sections": all_sections,
        "stages": STAGES,
        "year": cur_year,
        "month": cur_month,
        "month_label": f"{meses_es[cur_month]} {cur_year}",
        "weeks": weeks,
        "scheduled_count": len(scheduled_tasks),
        "unscheduled_tasks": unscheduled_tasks,
    }


def generate_ics_calendar(scope: str = "fidel") -> str:
    """Genera un archivo de suscripción estándar iCalendar (.ics) para sincronizar con Google Calendar."""
    board = get_kanban_board(scope=scope)
    tasks = []
    for stage_tasks in board["columns"].values():
        tasks.extend(stage_tasks)

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Kindle Tasks Pro//ES",
        f"X-WR-CALNAME:Kindle Tasks ({scope.upper()})",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for t in tasks:
        t_date = t.get("target_date")
        if not t_date:
            continue
        d_clean = t_date.replace("-", "")
        st_clean = (t.get("start_time") or "09:00").replace(":", "") + "00"
        et_clean = (t.get("end_time") or "10:30").replace(":", "") + "00"
        code = t.get("code") or format_task_code(t, t.get("scope", "fidel"))

        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{t.get('id')}@kindletasks.local",
            f"DTSTAMP:{datetime.now().strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART:{d_clean}T{st_clean}",
            f"DTEND:{d_clean}T{et_clean}",
            f"SUMMARY:[{code}] {t.get('title', 'Tarea')}",
            f"DESCRIPTION:Prioridad: {t.get('priority')} | SP: {t.get('story_points')} | Etapa: {t.get('stage')}\\n{t.get('description', '')}",
            f"STATUS:{'COMPLETED' if t.get('stage') == 'done' else 'CONFIRMED'}",
            "END:VEVENT",
        ])

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)

