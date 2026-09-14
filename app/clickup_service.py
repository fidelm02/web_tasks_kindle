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
import os
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

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

_CACHED_STATUSES: list[dict[str, str]] = []
_CACHED_SPRINT_INFO: tuple[str, str] | None = None


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


def _find_highest_sprint_list(
    api_token: str, base_url: str
) -> tuple[str, str]:
    """Find the ClickUp list corresponding to the highest sprint number.

    Queries the Development folder to detect all Sprint lists,
    parses sprint numbers via regex, and identifies the most recent
    active sprint list.

    Args:
        api_token: ClickUp personal API token.
        base_url: ClickUp API root endpoint.

    Returns:
        tuple[str, str]: Target list ID and descriptive sprint name.
    """
    global _CACHED_SPRINT_INFO
    if _CACHED_SPRINT_INFO is not None:
        return _CACHED_SPRINT_INFO

    folder_id = _get_config_value("CLICKUP_FOLDER_ID", "901313945044")
    try:
        folder_data = _request_json(
            f"{base_url}/folder/{folder_id}/list", api_token
        )
        lists = folder_data.get("lists", [])
        sprints: list[tuple[int, str, str]] = []

        for item in lists:
            name = item.get("name", "")
            match = re.search(r"Sprint\s+(\d+)", name, re.IGNORECASE)
            if match:
                sprints.append(
                    (int(match.group(1)), str(item.get("id")), name)
                )

        if sprints:
            sprints.sort(key=lambda s: s[0], reverse=True)
            _CACHED_SPRINT_INFO = (sprints[0][1], sprints[0][2])
            return _CACHED_SPRINT_INFO
    except Exception:
        pass

    fallback_id = _get_config_value("CLICKUP_LIST_ID", "901329008508")
    _CACHED_SPRINT_INFO = (fallback_id, "Sprint Actual")
    return _CACHED_SPRINT_INFO


def get_available_statuses(list_id: str | None = None) -> list[dict[str, str]]:
    """Retrieve available task statuses with in-memory caching.

    Queries list details on initial run and caches valid statuses to
    prevent repeated network overhead on page reloads.

    Args:
        list_id: Optional list ID to query statuses for.

    Returns:
        list[dict[str, str]]: List of status definitions.
    """
    global _CACHED_STATUSES
    if _CACHED_STATUSES:
        return _CACHED_STATUSES

    api_token = _get_config_value("CLICKUP_API_TOKEN")
    base_url = _get_config_value(
        "CLICKUP_API_BASE_URL", "https://api.clickup.com/api/v2"
    )
    target_list_id = list_id or _get_config_value(
        "CLICKUP_LIST_ID", "901329008508"
    )

    if not api_token:
        return []

    try:
        list_info = _request_json(
            f"{base_url}/list/{target_list_id}", api_token
        )
        raw_statuses = list_info.get("statuses", [])
        _CACHED_STATUSES = [
            {
                "status": s.get("status", "").strip(),
                "type": s.get("type", "custom"),
            }
            for s in raw_statuses
            if s.get("status")
        ]
        return _CACHED_STATUSES
    except Exception:
        return [
            {"status": "to do", "type": "open"},
            {"status": "in progress", "type": "custom"},
            {"status": "review", "type": "done"},
            {"status": "done", "type": "done"},
            {"status": "complete", "type": "closed"},
        ]


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

        # Update cache of statuses
        raw_statuses = list_info.get("statuses", [])
        if raw_statuses and not _CACHED_STATUSES:
            for s in raw_statuses:
                if s.get("status"):
                    _CACHED_STATUSES.append(
                        {
                            "status": s.get("status", "").strip(),
                            "type": s.get("type", "custom"),
                        }
                    )

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
                    "url": t.get("url", ""),
                }
            )

        return (list_name, parsed_tasks, None)

    except Exception as exc:
        return ("Error", [], str(exc))


def get_sprint_tasks() -> tuple[str, list[dict[str, Any]], str | None]:
    """Fetch tasks for the highest active Sprint detected dynamically.

    Args:
        None.

    Returns:
        tuple[str, list[dict[str, Any]], str | None]: Sprint name,
            list of tasks, and error string if any.
    """
    api_token = _get_config_value("CLICKUP_API_TOKEN")
    base_url = _get_config_value(
        "CLICKUP_API_BASE_URL", "https://api.clickup.com/api/v2"
    )
    sprint_list_id, _ = _find_highest_sprint_list(api_token, base_url)
    return fetch_clickup_tasks(sprint_list_id)


def get_backlog_tasks() -> tuple[str, list[dict[str, Any]], str | None]:
    """Fetch tasks assigned to current user for the Product Backlog.

    Args:
        None.

    Returns:
        tuple[str, list[dict[str, Any]], str | None]: Backlog name,
            list of tasks, and error string if any.
    """
    backlog_list_id = _get_config_value(
        "CLICKUP_BACKLOG_LIST_ID", "901322014973"
    )
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

