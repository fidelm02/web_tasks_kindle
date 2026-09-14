"""Utilidades comunes y validaciones de navegación."""

from __future__ import annotations

import urllib.parse
from app.services import section_service


def safe_redirect(target: str | None, default: str = "/tasks") -> str:
    """Validate and sanitize redirect URL to prevent open redirects.

    Args:
        target: Requested destination URL.
        default: Fallback URL if target is unauthorized.

    Returns:
        str: Safe redirect URL string.
    """
    if not target:
        return default
    parsed = urllib.parse.urlparse(target)
    if (
        not parsed.netloc
        and parsed.path.startswith("/")
        and not parsed.path.startswith("//")
    ):
        return target
    return default


def get_section_title(scope: str) -> str:
    """Return friendly display name for a given section scope.

    Args:
        scope: Section slug or identifier.

    Returns:
        str: Display title string.
    """
    sec = section_service.get_section(scope)
    if sec:
        return sec.get("name", scope.title())
    return scope.replace("_", " ").replace("-", " ").title()
