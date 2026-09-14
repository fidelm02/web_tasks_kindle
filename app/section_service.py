"""Gestión modular de secciones y proyectos para el portal del hogar."""

from __future__ import annotations

import json
import os
import re
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any
from filelock import FileLock

_BASE_DIR = Path(__file__).resolve().parent.parent
SECTIONS_FILE = str(_BASE_DIR / "data" / "sections.json")
SECTIONS_LOCK = SECTIONS_FILE + ".lock"
VALID_STATUSES = {"active", "completed", "archived"}

ICON_MAP: dict[str, str] = {
    "home": (
        '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2.5" stroke-linecap="round" '
        'stroke-linejoin="round">'
        '<path d="M3 10.5L12 3l9 7.5V21a1 1 0 0 1-1 1h-5v-6h-6v6H4'
        'a1 1 0 0 1-1-1v-10.5z"/>'
        "</svg>"
    ),
    "heart": (
        '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2.5" stroke-linecap="round" '
        'stroke-linejoin="round">'
        '<path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 '
        "2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 "
        '14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 '
        '11.54L12 21.35z"/>'
        "</svg>"
    ),
    "zap": (
        '<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor" '
        'stroke="currentColor" stroke-width="1" stroke-linecap="round" '
        'stroke-linejoin="round">'
        '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>'
        "</svg>"
    ),
    "folder": (
        '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round">'
        '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 '
        '2-2h5l2 3h9a2 2 0 0 1 2 2z"/>'
        "</svg>"
    ),
    "briefcase": (
        '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round">'
        '<rect x="2" y="7" width="20" height="14" rx="2" ry="2"/>'
        '<path d="M16 7V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v3"/>'
        "</svg>"
    ),
    "star": (
        '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round">'
        '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 '
        '12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>'
        "</svg>"
    ),
    "target": (
        '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="10"/>'
        '<circle cx="12" cy="12" r="6"/>'
        '<circle cx="12" cy="12" r="2"/>'
        "</svg>"
    ),
    "book": (
        '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round">'
        '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>'
        '<path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 '
        '0 0 1 6.5 2z"/>'
        "</svg>"
    ),
    "check": (
        '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round">'
        '<polyline points="20 6 9 17 4 12"/>'
        "</svg>"
    ),
    "tool": (
        '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round">'
        '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77'
        "-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91"
        '-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>'
        "</svg>"
    ),
    "mail": (
        '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round">'
        '<path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 '
        '0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>'
        '<polyline points="22,6 12,13 2,6"/>'
        "</svg>"
    ),
}

DEFAULT_SECTIONS: list[dict[str, Any]] = [
    {
        "id": "casa",
        "name": "Casa",
        "icon": "home",
        "has_tasks": True,
        "has_docs": False,
        "has_clickup": False,
        "tasks_label": "Pendientes del Hogar",
        "docs_label": "Documentos y Lecturas",
        "is_system": True,
        "status": "active",
        "sort_order": 0,
        "description": "Gestión del hogar y tareas domésticas compartidas.",
        "created_at": "2026-01-01T00:00:00",
    },
    {
        "id": "lau",
        "name": "Lau",
        "icon": "heart",
        "has_tasks": True,
        "has_docs": True,
        "has_clickup": False,
        "tasks_label": "Pendientes de Lau",
        "docs_label": "Documentos y Lecturas",
        "is_system": True,
        "status": "active",
        "sort_order": 1,
        "description": "Espacio personal y lecturas para Lau.",
        "created_at": "2026-01-01T00:00:00",
    },
    {
        "id": "fidel",
        "name": "Fidel",
        "icon": "zap",
        "has_tasks": True,
        "has_docs": True,
        "has_clickup": True,
        "tasks_label": "Pendientes de Fidel",
        "docs_label": "Documentos y Lecturas",
        "is_system": True,
        "status": "active",
        "sort_order": 2,
        "description": "Espacio de trabajo, ClickUp y lecturas de Fidel.",
        "created_at": "2026-01-01T00:00:00",
    },
]


def _ensure_sections_file() -> None:
    """Ensure sections JSON registry exists with default sections."""
    os.makedirs(os.path.dirname(SECTIONS_FILE), exist_ok=True)
    if not os.path.exists(SECTIONS_FILE):
        with open(SECTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {"sections": DEFAULT_SECTIONS},
                f,
                ensure_ascii=False,
                indent=2,
            )


def _write_sections_atomic(sections: list[dict[str, Any]]) -> None:
    """Atomic file replacement helper protected by FileLock."""
    directory = os.path.dirname(SECTIONS_FILE)
    fd, tmp_path = tempfile.mkstemp(
        dir=directory, prefix=".tmp_sections_", suffix=".json"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            json.dump(
                {"sections": sections},
                tmp_file,
                ensure_ascii=False,
                indent=2,
            )
        os.replace(tmp_path, SECTIONS_FILE)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def get_all_sections() -> list[dict[str, Any]]:
    """Return all registered sections sorted by display order.

    Returns:
        list[dict[str, Any]]: List of section dictionaries.
    """
    _ensure_sections_file()
    with FileLock(SECTIONS_LOCK):
        with open(SECTIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        sections = data.get("sections", [])
        return sorted(sections, key=lambda s: s.get("sort_order", 99))


def get_active_sections() -> list[dict[str, Any]]:
    """Return all active sections preserving strict initial order.

    Guarantees Casa, Lau, Fidel appear first in exact order,
    followed by active custom sections sorted by order.

    Returns:
        list[dict[str, Any]]: Filtered active sections.
    """
    all_sec = get_all_sections()
    system_order = {"casa": 0, "lau": 1, "fidel": 2}
    system_secs = [s for s in all_sec if s.get("is_system")]
    system_secs.sort(key=lambda s: system_order.get(s["id"].lower(), 99))

    custom_active = [
        s
        for s in all_sec
        if not s.get("is_system")
        and s.get("status", "active") == "active"
    ]
    custom_active.sort(key=lambda s: s.get("sort_order", 99))
    return system_secs + custom_active


def get_sections_by_status(status: str) -> list[dict[str, Any]]:
    """Return non-system sections matching specified status.

    Args:
        status: Target status ('completed' or 'archived').

    Returns:
        list[dict[str, Any]]: Filtered sections.
    """
    all_sec = get_all_sections()
    target = status.lower().strip()
    return [
        s
        for s in all_sec
        if not s.get("is_system")
        and s.get("status", "active") == target
    ]


def update_section_status(section_id: str, new_status: str) -> bool:
    """Update lifecycle status of a custom section.

    Args:
        section_id: Section slug identifier string.
        new_status: Target status ('active', 'completed', 'archived').

    Returns:
        bool: True if section was found and updated, False otherwise.
    """
    if new_status not in VALID_STATUSES:
        return False
    _ensure_sections_file()
    with FileLock(SECTIONS_LOCK):
        with open(SECTIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        sections = data.get("sections", [])
        found = False
        norm = section_id.lower().strip()
        for sec in sections:
            if sec["id"].lower() == norm:
                if sec.get("is_system"):
                    return False
                sec["status"] = new_status
                sec["updated_at"] = datetime.now().isoformat()
                found = True
                break
        if found:
            _write_sections_atomic(sections)
        return found


def get_section(section_id: str) -> dict[str, Any] | None:
    """Return a single section dictionary by its unique slug ID.

    Args:
        section_id: Section slug string.

    Returns:
        dict[str, Any] | None: Found section or None.
    """
    sections = get_all_sections()
    norm = section_id.lower().strip()
    for sec in sections:
        if sec["id"].lower() == norm:
            return sec
    return None


def get_icon_svg(icon_key: str) -> str:
    """Return SVG markup string for a given icon identifier.

    Args:
        icon_key: Registered icon name key.

    Returns:
        str: Raw SVG element markup.
    """
    return ICON_MAP.get(icon_key.lower(), ICON_MAP["folder"])


def list_available_icons() -> list[dict[str, str]]:
    """Return list of available icons for UI selection controls.

    Returns:
        list[dict[str, str]]: List of dicts with key, label, and SVG.
    """
    labels: dict[str, str] = {
        "home": "Casa",
        "heart": "Corazón",
        "zap": "Rayo",
        "folder": "Carpeta",
        "briefcase": "Trabajo",
        "star": "Estrella",
        "target": "Objetivo",
        "book": "Libro",
        "check": "Tareas",
        "tool": "Taller",
        "mail": "Correo",
    }
    return [
        {
            "key": key,
            "label": labels.get(key, key.title()),
            "svg": svg,
        }
        for key, svg in ICON_MAP.items()
    ]


def get_default_recipients() -> list[str]:
    """Return list of configured default email recipients.

    Returns:
        list[str]: Default recipient email addresses.
    """
    try:
        from app import constants as config

        if hasattr(config, "DEFAULT_EMAIL_RECIPIENTS"):
            return list(config.DEFAULT_EMAIL_RECIPIENTS)
    except Exception:
        pass
    return ["fidelm02@gmail.com", "lalisgallego@hotmail.com"]


def _slugify(text: str) -> str:
    """Convert arbitrary text string to clean ASCII URL-safe slug.

    Args:
        text: Raw name string.

    Returns:
        str: ASCII URL-safe slug.
    """
    normalized = (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    cleaned = normalized.lower().strip()
    cleaned = re.sub(r"[^\w\s-]", "", cleaned)
    cleaned = re.sub(r"[\s_]+", "-", cleaned)
    return cleaned.strip("-") or "seccion"


def create_section(
    name: str,
    icon: str = "folder",
    has_tasks: bool = True,
    has_docs: bool = True,
    description: str = "",
) -> dict[str, Any]:
    """Create and persist a new custom section in the registry.

    Args:
        name: Visible display name for the section.
        icon: Selected SVG icon key from ICON_MAP.
        has_tasks: Whether to activate task management.
        has_docs: Whether to activate document library.
        description: Optional notes or scope description.

    Returns:
        dict[str, Any]: Newly created section dictionary.
    """
    _ensure_sections_file()
    with FileLock(SECTIONS_LOCK):
        with open(SECTIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        sections: list[dict[str, Any]] = data.get("sections", [])
        base_slug = _slugify(name)
        slug = base_slug
        counter = 2
        existing_ids = {s["id"].lower() for s in sections}

        while slug.lower() in existing_ids:
            slug = f"{base_slug}-{counter}"
            counter += 1

        safe_icon = icon.lower() if icon.lower() in ICON_MAP else "folder"
        new_sec: dict[str, Any] = {
            "id": slug,
            "name": name.strip(),
            "icon": safe_icon,
            "has_tasks": bool(has_tasks),
            "has_docs": bool(has_docs),
            "has_clickup": False,
            "tasks_label": f"Pendientes de {name.strip()}",
            "docs_label": "Documentos y Lecturas",
            "is_system": False,
            "status": "active",
            "sort_order": len(sections) + 1,
            "description": description.strip(),
            "created_at": datetime.now().isoformat(),
        }

        sections.append(new_sec)
        _write_sections_atomic(sections)
        return new_sec
