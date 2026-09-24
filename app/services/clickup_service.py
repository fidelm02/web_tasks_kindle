"""ClickUp integration service for Kindle Scribe.

Objective:
    Fetch, format, and update assigned tasks for active sprint and
    backlog from ClickUp API v2, with caching and status management.

Author:
    Fidel Moreno Miranda <fidelm02@gmail.com>
"""

from __future__ import annotations

from datetime import datetime
import json
import logging
import os
import re
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# Attempt to load local credentials module
try:
    from app import constants as config  # type: ignore
except ImportError:
    try:
        import sys
        from pathlib import Path

        parent_dir = str(Path(__file__).resolve().parent.parent.parent)
        if parent_dir not in sys.path:
            sys.path.append(parent_dir)
        from Clickup import constants as config  # type: ignore
    except ImportError:
        config = None  # type: ignore

_SPRINT_CACHE_TTL: float = 300.0  # 5 minutos de caché para sprint actual
_CACHED_SPRINT_INFO: tuple[str, str] | None = None
_CACHED_SPRINT_TIMESTAMP: float = 0.0

_STATUS_CACHE_TTL: float = 3600.0  # 1 hora para estados por lista
_CACHED_STATUSES: dict[str, tuple[list[dict[str, str]], float]] = {}

_DEFAULT_FALLBACK_STATUSES: list[dict[str, str]] = [
    {"status": "to do", "type": "open"},
    {"status": "in progress", "type": "custom"},
    {"status": "review", "type": "done"},
    {"status": "done", "type": "done"},
    {"status": "complete", "type": "closed"},
]


def _get_config_value(key: str, default: str = "") -> str:
    """Retrieve configuration variable from constants or environment.

    Args:
        key: The configuration setting name.
        default: Default fallback value if not configured.

    Returns:
        str: The resolved configuration setting.
    """
    if config is not None and hasattr(config, key):
        val = getattr(config, key)
        if val:
            return str(val)
    return os.getenv(key, default)


def _format_date(timestamp_raw: str | int | None) -> str | None:
    """Format millisecond timestamp into day/month/year string.

    Args:
        timestamp_raw: Millisecond Unix timestamp or None.

    Returns:
        str | None: Formatted date string (DD/MM/YYYY) or None.
    """
    if not timestamp_raw:
        return None
    try:
        ts = int(timestamp_raw) / 1000.0
        return datetime.fromtimestamp(ts).strftime("%d/%m/%Y")
    except (ValueError, TypeError, OSError):
        return None


def _request_json(
    endpoint: str,
    api_token: str,
    method: str = "GET",
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute authenticated HTTP request against ClickUp API.

    Args:
        endpoint: Complete URL endpoint to request.
        api_token: Personal ClickUp API token.
        method: HTTP method verb ('GET', 'PUT', etc.).
        data: Optional dictionary payload to send as JSON.

    Returns:
        dict[str, Any]: Parsed JSON response payload.

    Raises:
        RuntimeError: If HTTP request fails or network is unreachable.
    """
    payload_bytes = json.dumps(data).encode("utf-8") if data else None
    req = Request(
        endpoint,
        data=payload_bytes,
        headers={
            "Authorization": api_token,
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(
            f"Error de ClickUp (Código {exc.code})"
        ) from exc
    except URLError as exc:
        raise RuntimeError(
            f"No se pudo conectar con ClickUp: {exc.reason}"
        ) from exc


def get_current_sprint_info(
    force_refresh: bool = False,
) -> tuple[str, str]:
    """Dynamically determine the active Sprint list ID and name from ClickUp.

    Evaluates lists in the Development folder (or configured folder),
    matches Sprint lists, and checks their start_date and due_date timestamps
    against the current time. If an active sprint is found, its list ID is
    returned. If dates are not set or between sprints, it selects the most
    recently started or highest numbered sprint.

    Results are cached in memory with a 5-minute TTL to avoid redundant API
    calls while remaining responsive when sprints change.

    Args:
        force_refresh: If True, bypass in-memory TTL cache and query ClickUp.

    Returns:
        tuple[str, str]: Target list ID and descriptive sprint name.
    """
    global _CACHED_SPRINT_INFO, _CACHED_SPRINT_TIMESTAMP

    now = time.time()
    if (
        not force_refresh
        and _CACHED_SPRINT_INFO is not None
        and (now - _CACHED_SPRINT_TIMESTAMP) < _SPRINT_CACHE_TTL
    ):
        return _CACHED_SPRINT_INFO

    api_token = _get_config_value("CLICKUP_API_TOKEN")
    base_url = _get_config_value(
        "CLICKUP_API_BASE_URL", "https://api.clickup.com/api/v2"
    )

    if not api_token:
        return ("0", "Sin Configuración")

    # 1. Override manual explícito (si el usuario lo definió)
    override_id = _get_config_value("CLICKUP_SPRINT_OVERRIDE_ID").strip()
    if override_id:
        try:
            list_info = _request_json(f"{base_url}/list/{override_id}", api_token)
            name = list_info.get("name", f"Sprint {override_id}")
            _CACHED_SPRINT_INFO = (override_id, name)
            _CACHED_SPRINT_TIMESTAMP = now
            return _CACHED_SPRINT_INFO
        except Exception:
            _CACHED_SPRINT_INFO = (override_id, "Sprint Actual")
            _CACHED_SPRINT_TIMESTAMP = now
            return _CACHED_SPRINT_INFO

    # 2. Detección dinámica en el folder de desarrollo
    folder_id = _get_config_value("CLICKUP_FOLDER_ID", "901313945044")
    try:
        folder_data = _request_json(
            f"{base_url}/folder/{folder_id}/list", api_token
        )
        lists = folder_data.get("lists", [])
        now_ms = int(now * 1000)

        sprint_candidates: list[dict[str, Any]] = []
        for item in lists:
            if item.get("archived"):
                continue
            name = str(item.get("name", ""))
            match = re.search(r"Sprint\s+(\d+)", name, re.IGNORECASE)
            if not match:
                continue

            sprint_num = int(match.group(1))
            list_id = str(item.get("id", ""))
            start_raw = item.get("start_date")
            due_raw = item.get("due_date")
            start_ms = int(start_raw) if start_raw else None
            due_ms = int(due_raw) if due_raw else None

            is_active_now = False
            if start_ms is not None and due_ms is not None:
                if start_ms <= now_ms <= due_ms:
                    is_active_now = True

            sprint_candidates.append(
                {
                    "number": sprint_num,
                    "id": list_id,
                    "name": name,
                    "start_ms": start_ms,
                    "due_ms": due_ms,
                    "is_active_now": is_active_now,
                }
            )

        if sprint_candidates:
            # Criterio A: Activo por fecha hoy (start <= hoy <= due)
            active_by_date = [s for s in sprint_candidates if s["is_active_now"]]
            if active_by_date:
                active_by_date.sort(key=lambda s: s["number"], reverse=True)
                selected = active_by_date[0]
            else:
                # Criterio B: Ya ha iniciado en el pasado más reciente
                started = [
                    s
                    for s in sprint_candidates
                    if s["start_ms"] is not None and s["start_ms"] <= now_ms
                ]
                if started:
                    started.sort(key=lambda s: s["number"], reverse=True)
                    selected = started[0]
                else:
                    # Criterio C: Mayor número de sprint
                    sprint_candidates.sort(
                        key=lambda s: s["number"], reverse=True
                    )
                    selected = sprint_candidates[0]

            _CACHED_SPRINT_INFO = (selected["id"], selected["name"])
            _CACHED_SPRINT_TIMESTAMP = now
            return _CACHED_SPRINT_INFO

    except Exception as exc:
        logger.warning(
            "Fallo al detectar sprint actual dinámicamente: %s", exc
        )
        if _CACHED_SPRINT_INFO is not None:
            return _CACHED_SPRINT_INFO

    # 3. Fallback de rescate si no se pudo conectar y no hay caché
    return ("0", "Sprint Actual")


def get_current_sprint_id(force_refresh: bool = False) -> str:
    """Retrieve the ID of the current active ClickUp sprint.

    Args:
        force_refresh: Whether to force cache invalidation.

    Returns:
        str: ClickUp list ID string for the active sprint.
    """
    sprint_id, _ = get_current_sprint_info(force_refresh=force_refresh)
    return sprint_id


def _find_highest_sprint_list(
    api_token: str = "", base_url: str = ""
) -> tuple[str, str]:
    """Compatibility wrapper for dynamic sprint detection.

    Args:
        api_token: Unused, kept for backwards compatibility.
        base_url: Unused, kept for backwards compatibility.

    Returns:
        tuple[str, str]: Target list ID and descriptive sprint name.
    """
    return get_current_sprint_info()


def clear_clickup_cache() -> None:
    """Clear all in-memory sprint and status caches to force fresh fetch."""
    global _CACHED_SPRINT_INFO, _CACHED_SPRINT_TIMESTAMP, _CACHED_STATUSES
    _CACHED_SPRINT_INFO = None
    _CACHED_SPRINT_TIMESTAMP = 0.0
    _CACHED_STATUSES.clear()


def get_available_statuses(list_id: str | None = None) -> list[dict[str, str]]:
    """Retrieve available task statuses with in-memory per-list caching.

    Args:
        list_id: Optional list ID to query statuses for. Defaults to current sprint list.

    Returns:
        list[dict[str, str]]: List of status definitions.
    """
    global _CACHED_STATUSES
    target_list_id = list_id or get_current_sprint_id()

    now = time.time()
    if target_list_id and target_list_id in _CACHED_STATUSES:
        cached_statuses, cached_time = _CACHED_STATUSES[target_list_id]
        if (now - cached_time) < _STATUS_CACHE_TTL:
            return cached_statuses

    api_token = _get_config_value("CLICKUP_API_TOKEN")
    base_url = _get_config_value(
        "CLICKUP_API_BASE_URL", "https://api.clickup.com/api/v2"
    )

    if not api_token or not target_list_id or target_list_id == "0":
        return _DEFAULT_FALLBACK_STATUSES

    try:
        list_info = _request_json(
            f"{base_url}/list/{target_list_id}", api_token
        )
        raw_statuses = list_info.get("statuses", [])
        parsed_statuses = [
            {
                "status": s.get("status", "").strip(),
                "type": s.get("type", "custom"),
            }
            for s in raw_statuses
            if s.get("status")
        ]
        if parsed_statuses:
            _CACHED_STATUSES[target_list_id] = (parsed_statuses, now)
            return parsed_statuses
    except Exception:
        pass

    return _DEFAULT_FALLBACK_STATUSES


def update_task_status(
    task_id: str, new_status: str
) -> tuple[bool, str]:
    """Update the status of a specific ClickUp task.

    Args:
        task_id: Unique task identifier.
        new_status: Desired status string (e.g. 'in progress').

    Returns:
        tuple[bool, str]: Success boolean and status message.
    """
    api_token = _get_config_value("CLICKUP_API_TOKEN")
    base_url = _get_config_value(
        "CLICKUP_API_BASE_URL", "https://api.clickup.com/api/v2"
    )

    if not api_token:
        return False, "Token de ClickUp no configurado."

    try:
        _request_json(
            f"{base_url}/task/{task_id}",
            api_token,
            method="PUT",
            data={"status": new_status.lower().strip()},
        )
        return True, f"Estado actualizado a '{new_status.upper()}'."
    except Exception as exc:
        return False, f"Error al actualizar estado: {exc}"


_STORY_POINTS_FIELD_ID_CACHE: dict[str, str] = {}
DEFAULT_STORY_POINTS_FIELD_ID: str = "7b1508db-eb0b-4879-8a3e-7d6aee84f52e"


def _get_story_points_field_id(
    list_id: str, api_token: str, base_url: str
) -> str:
    """Retrieve the custom field ID for Story Points in the given list.

    Args:
        list_id: ClickUp list ID.
        api_token: ClickUp API authorization token.
        base_url: ClickUp API root endpoint.

    Returns:
        str: Custom field UUID for Story Points.
    """
    if list_id in _STORY_POINTS_FIELD_ID_CACHE:
        return _STORY_POINTS_FIELD_ID_CACHE[list_id]

    try:
        data = _request_json(f"{base_url}/list/{list_id}/field", api_token)
        fields = data.get("fields", [])
        for f in fields:
            name = str(f.get("name", "")).strip().lower()
            if name in ("story points", "story point", "points", "puntos"):
                fid = str(f.get("id"))
                _STORY_POINTS_FIELD_ID_CACHE[list_id] = fid
                return fid
    except Exception:
        pass

    _STORY_POINTS_FIELD_ID_CACHE[list_id] = DEFAULT_STORY_POINTS_FIELD_ID
    return DEFAULT_STORY_POINTS_FIELD_ID


def create_clickup_task(
    list_id: str,
    name: str,
    description: str = "",
    story_points: float | int | None = None,
    status: str = "to do",
    assignee_id: str | int | None = None,
) -> tuple[bool, str, dict[str, Any] | None]:
    """Create a new task in ClickUp with default status and assignee.

    By default assigns the configured user and sets status to 'to do'.
    Story points are saved via the 'Story Points' custom field.

    Args:
        list_id: Target ClickUp list ID.
        name: Title of the task.
        description: Optional task description or technical notes.
        story_points: Optional numeric story points estimate.
        status: Initial task status (defaults to 'to do').
        assignee_id: Optional user identifier (defaults to CLICKUP_USER_ID).

    Returns:
        tuple[bool, str, dict[str, Any] | None]: Success status, message,
            and task payload dict if created.
    """
    api_token = _get_config_value("CLICKUP_API_TOKEN")
    base_url = _get_config_value(
        "CLICKUP_API_BASE_URL", "https://api.clickup.com/api/v2"
    )

    if not api_token:
        return False, "Token de ClickUp no configurado en app/constants.py.", None

    if not list_id or list_id == "0":
        return False, "No se ha determinado una lista válida de ClickUp.", None

    target_name = name.strip()
    if not target_name:
        return False, "El título de la tarea no puede estar vacío.", None

    target_assignee = assignee_id or _get_config_value(
        "CLICKUP_USER_ID", "106028598"
    )
    assignees: list[int] = []
    if target_assignee:
        try:
            assignees.append(int(target_assignee))
        except (ValueError, TypeError):
            pass

    payload: dict[str, Any] = {
        "name": target_name,
        "description": description.strip(),
        "status": status.lower().strip(),
    }
    if assignees:
        payload["assignees"] = assignees

    # Configuración de Story Points en custom_fields
    if story_points is not None:
        try:
            sp_num = float(story_points)
            if sp_num.is_integer():
                sp_num = int(sp_num)

            field_id = _get_story_points_field_id(list_id, api_token, base_url)
            if field_id:
                payload["custom_fields"] = [
                    {"id": field_id, "value": sp_num}
                ]
        except (ValueError, TypeError):
            pass

    try:
        created_task = _request_json(
            f"{base_url}/list/{list_id}/task",
            api_token,
            method="POST",
            data=payload,
        )
        task_title = created_task.get("name", target_name)
        return (
            True,
            f"Tarea '{task_title}' creada exitosamente en ClickUp.",
            created_task,
        )
    except Exception as exc:
        logger.error("Error al crear tarea en ClickUp: %s", exc)
        return False, f"Error al crear tarea en ClickUp: {exc}", None


def fetch_clickup_tasks(
    list_id: str,
) -> tuple[str, list[dict[str, Any]], str | None]:
    """Retrieve and format tasks for a given ClickUp list.

    Fetches tasks from the specified ClickUp list, filters them by
    the configured user identifier, identifies tags, flags REQ tasks,
    and extracts relevant display fields for e-ink presentation.

    Args:
        list_id: Unique identifier of the ClickUp list to inspect.

    Returns:
        tuple[str, list[dict[str, Any]], str | None]: List name,
            parsed task dictionaries, and error message if any.
    """
    api_token = _get_config_value("CLICKUP_API_TOKEN")
    base_url = _get_config_value(
        "CLICKUP_API_BASE_URL", "https://api.clickup.com/api/v2"
    )
    target_user_id = _get_config_value("CLICKUP_USER_ID")

    if not api_token:
        return (
            "Sin Configuración",
            [],
            "CLICKUP_API_TOKEN no está configurado en app/constants.py",
        )

    if not list_id:
        return ("Sin Lista", [], "ID de lista ClickUp no proporcionado.")

    try:
        # Retrieve list metadata
        list_info = _request_json(f"{base_url}/list/{list_id}", api_token)
        list_name = list_info.get("name", f"Lista {list_id}")

        # Update cache of statuses for this list
        raw_statuses = list_info.get("statuses", [])
        if raw_statuses:
            list_statuses = [
                {
                    "status": s.get("status", "").strip(),
                    "type": s.get("type", "custom"),
                }
                for s in raw_statuses
                if s.get("status")
            ]
            if list_statuses:
                _CACHED_STATUSES[str(list_id)] = (list_statuses, time.time())

        # Retrieve tasks
        query = urlencode({"archived": "false", "include_closed": "true"})
        tasks_url = f"{base_url}/list/{list_id}/task?{query}"
        tasks_payload = _request_json(tasks_url, api_token)
        raw_tasks = tasks_payload.get("tasks", [])

        parsed_tasks: list[dict[str, Any]] = []
        for t in raw_tasks:
            assignees = t.get("assignees", [])
            assignee_ids = {
                str(a.get("id")) for a in assignees if a.get("id")
            }
            if target_user_id and str(target_user_id) not in assignee_ids:
                continue

            status_obj = t.get("status") or {}
            status_name = status_obj.get("status", "Sin estado").upper()
            status_type = status_obj.get("type", "custom")

            priority_obj = t.get("priority") or {}
            priority_name = priority_obj.get("priority", "Normal").capitalize()

            description = (
                t.get("text_content") or t.get("description") or ""
            ).strip()

            raw_tags = t.get("tags") or []
            tags: list[str] = [
                str(tag.get("name", "")).strip()
                for tag in raw_tags
                if tag.get("name")
            ]

            task_name = t.get("name", "Sin título")
            is_req = (
                task_name.strip().upper().startswith("REQ")
                or any(tg.upper() in ("REQ", "REQUEST") for tg in tags)
            )

            # Story points (custom field o nativo)
            story_points = t.get("points")
            if story_points is None:
                for cf in t.get("custom_fields", []):
                    if (
                        str(cf.get("name", "")).strip().lower() == "story points"
                        and cf.get("value") is not None
                    ):
                        story_points = cf.get("value")
                        break

            parsed_tasks.append(
                {
                    "id": str(t.get("id", "")),
                    "name": task_name,
                    "status": status_name,
                    "status_type": status_type,
                    "priority": priority_name,
                    "due_date": _format_date(t.get("due_date")),
                    "description": description,
                    "tags": tags,
                    "is_req": is_req,
                    "story_points": story_points,
                    "url": t.get("url", ""),
                }
            )

        return (list_name, parsed_tasks, None)

    except Exception as exc:
        return ("Error", [], str(exc))


def get_sprint_tasks(
    force_refresh: bool = False,
) -> tuple[str, list[dict[str, Any]], str | None]:
    """Fetch tasks for the active Sprint detected dynamically.

    Args:
        force_refresh: Whether to force cache invalidation.

    Returns:
        tuple[str, list[dict[str, Any]], str | None]: Sprint name,
            list of tasks, and error string if any.
    """
    sprint_list_id, _ = get_current_sprint_info(force_refresh=force_refresh)
    return fetch_clickup_tasks(sprint_list_id)


def get_backlog_list_id() -> str:
    """Retrieve the configured or default Product Backlog list ID.

    Returns:
        str: ClickUp list ID string for backlog.
    """
    return _get_config_value("CLICKUP_BACKLOG_LIST_ID", "901322014973")


def get_backlog_tasks() -> tuple[str, list[dict[str, Any]], str | None]:
    """Fetch tasks assigned to current user for the Product Backlog.

    Args:
        None.

    Returns:
        tuple[str, list[dict[str, Any]], str | None]: Backlog name,
            list of tasks, and error string if any.
    """
    backlog_list_id = get_backlog_list_id()
    return fetch_clickup_tasks(backlog_list_id)


_PRIORITY_WEIGHTS: dict[str, int] = {
    "URGENT": 0,
    "ALTA": 0,
    "HIGH": 1,
    "NORMAL": 2,
    "MEDIA": 2,
    "LOW": 3,
    "BAJA": 3,
}

_STATUS_ORDER_WEIGHTS: dict[str, int] = {
    "IN PROGRESS": 10,
    "EN PROGRESO": 10,
    "READY FOR SPRINT": 20,
    "LISTO": 20,
    "TO DO": 30,
    "TODO": 30,
    "OPEN": 30,
    "POR HACER": 30,
    "REVIEW": 40,
    "IN REVIEW": 40,
    "EN REVISION": 40,
    "BLOCKED": 50,
    "BLOQUEADO": 50,
    "ON HOLD": 60,
    "PAUSADO": 60,
    "DONE": 90,
    "LISTO / COMPLETADO": 90,
    "COMPLETE": 95,
    "COMPLETED": 95,
    "CLOSED": 99,
    "CERRADO": 99,
}


def sort_tasks_by_priority(
    tasks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Sort task dictionary list by priority rank, then by name.

    Args:
        tasks: List of task dictionaries.

    Returns:
        list[dict[str, Any]]: Sorted list of tasks.
    """
    return sorted(
        tasks,
        key=lambda t: (
            _PRIORITY_WEIGHTS.get(
                str(t.get("priority", "")).upper(), 99
            ),
            str(t.get("name", "")).lower(),
        ),
    )


def group_tasks_by_status(
    tasks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Group non-REQ tasks by status, sorted by priority within group.

    Args:
        tasks: List of task dictionaries.

    Returns:
        list[dict[str, Any]]: List of grouped status dictionaries,
            ordered by workflow lifecycle.
    """
    groups_dict: dict[str, list[dict[str, Any]]] = {}
    types_dict: dict[str, str] = {}

    for t in tasks:
        st = str(t.get("status", "SIN ESTADO")).upper()
        if st not in groups_dict:
            groups_dict[st] = []
            types_dict[st] = str(t.get("status_type", "custom"))
        groups_dict[st].append(t)

    result: list[dict[str, Any]] = []
    for st, group_tasks in groups_dict.items():
        sorted_group = sort_tasks_by_priority(group_tasks)
        st_type = types_dict.get(st, "custom")
        is_done = st in (
            "DONE",
            "COMPLETE",
            "COMPLETED",
            "CLOSED",
        ) or st_type in ("done", "closed")
        result.append(
            {
                "status": st,
                "status_type": st_type,
                "is_done": is_done,
                "tasks": sorted_group,
                "count": len(sorted_group),
            }
        )

    result.sort(
        key=lambda g: (
            _STATUS_ORDER_WEIGHTS.get(g["status"], 70),
            g["status"],
        )
    )
    return result

