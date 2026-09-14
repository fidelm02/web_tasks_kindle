"""Configuración centralizada del motor de plantillas Jinja2."""

from __future__ import annotations

from datetime import date, datetime
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")


def format_datetime_filter(val: str | None) -> str:
    """Format ISO timestamps for clean e-ink display.

    Args:
        val: ISO-formatted timestamp string or None.

    Returns:
        str: Human-readable timestamp string.
    """
    if not val:
        return ""
    try:
        dt = datetime.fromisoformat(val)
        today = date.today()
        if dt.date() == today:
            return f"Hoy, {dt.strftime('%H:%M')}"
        return dt.strftime("%d/%m/%Y, %H:%M")
    except Exception:
        return str(val)[:16].replace("T", " ")


def format_target_date_filter(val: str | None) -> str:
    """Format deadline date with friendly relative labels.

    Args:
        val: Date string in ISO format or None.

    Returns:
        str: Relative or formatted date string.
    """
    if not val:
        return ""
    try:
        d = date.fromisoformat(val)
        today = date.today()
        diff = (d - today).days
        if diff == 0:
            return "Hoy"
        if diff == 1:
            return "Mañana"
        if diff < 0:
            return f"Venció el {d.strftime('%d/%m/%Y')}"
        return d.strftime("%d/%m/%Y")
    except Exception:
        return str(val)


templates.env.filters["format_datetime"] = format_datetime_filter
templates.env.filters["format_target_date"] = format_target_date_filter
