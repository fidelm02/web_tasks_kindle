"""ClickUp integration service for Kindle Scribe.

Objective:
    Fetch and format assigned tasks for current sprint and product
    backlog from ClickUp API v2 for e-ink presentation.

Author:
    Fidel Moreno Miranda <fidelm02@gmail.com>
"""

from __future__ import annotations

from datetime import datetime
import json
import os
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


def _request_json(endpoint: str, api_token: str) -> dict[str, Any]:
    """Execute authenticated HTTP GET request against ClickUp API.

    Args:
        endpoint: Complete URL endpoint to request.
        api_token: Personal ClickUp API token.

    Returns:
        dict[str, Any]: Parsed JSON response payload.

    Raises:
        RuntimeError: If HTTP request fails or network is unreachable.
    """
    req = Request(
        endpoint,
        headers={
            "Authorization": api_token,
            "Content-Type": "application/json",
        },
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


def fetch_clickup_tasks(
    list_id: str,
) -> tuple[str, list[dict[str, Any]], str | None]:
    """Retrieve and format tasks for a given ClickUp list.

    Fetches tasks from the specified ClickUp list, filters them by
    the configured user identifier, and extracts relevant display
    fields for e-ink presentation.

    Args:
        list_id: Unique identifier of the ClickUp list to inspect.

    Returns:
        tuple[str, list[dict[str, Any]], str | None]: A triplet
            consisting of the list name, a list of parsed task
            dictionaries, and an error message string if any occurred.
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

        # Retrieve tasks
        query = urlencode({"archived": "false", "include_closed": "true"})
        tasks_url = f"{base_url}/list/{list_id}/task?{query}"
        tasks_payload = _request_json(tasks_url, api_token)
        raw_tasks = tasks_payload.get("tasks", [])

        parsed_tasks: list[dict[str, Any]] = []
        for t in raw_tasks:
            assignees = t.get("assignees", [])
            assignee_ids = {str(a.get("id")) for a in assignees if a.get("id")}
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

            parsed_tasks.append(
                {
                    "id": str(t.get("id", "")),
                    "name": t.get("name", "Sin título"),
                    "status": status_name,
                    "status_type": status_type,
                    "priority": priority_name,
                    "due_date": _format_date(t.get("due_date")),
                    "description": description,
                    "url": t.get("url", ""),
                }
            )

        return (list_name, parsed_tasks, None)

    except Exception as exc:
        return ("Error", [], str(exc))


def get_sprint_tasks() -> tuple[str, list[dict[str, Any]], str | None]:
    """Fetch tasks assigned to current user for the active Sprint.

    Args:
        None.

    Returns:
        tuple[str, list[dict[str, Any]], str | None]: Sprint name,
            list of tasks, and error string if any.
    """
    sprint_list_id = _get_config_value(
        "CLICKUP_LIST_ID", "901327834680"
    )
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
