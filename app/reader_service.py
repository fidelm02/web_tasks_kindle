"""Markdown reader service for Kindle Scribe.

Objective:
    Scan, parse, and convert markdown documents into clean, readable
    HTML optimized for electronic ink screens and serif typography.

Author:
    Fidel Moreno Miranda <fidelm02@gmail.com>
"""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import re
from typing import Any
import markdown

BASE_DIR: Path = Path(__file__).resolve().parent.parent
DOCS_DIR: Path = BASE_DIR / "docs"


def _ensure_docs_dir() -> Path:
    """Ensure the documents directory exists.

    Args:
        None.

    Returns:
        Path: Resolved directory path for markdown files.
    """
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    return DOCS_DIR


def list_documents() -> list[dict[str, Any]]:
    """Scan and list all available markdown documents.

    Inspects the docs directory, extracts metadata (title, summary,
    and modification date) from each file for catalog display.

    Args:
        None.

    Returns:
        list[dict[str, Any]]: List of document summaries.
    """
    directory: Path = _ensure_docs_dir()
    docs: list[dict[str, Any]] = []

    for file_path in sorted(directory.glob("*.md")):
        if not file_path.is_file():
            continue
        try:
            content: str = file_path.read_text(encoding="utf-8")
            lines: list[str] = content.splitlines()

            title: str = file_path.stem.replace("_", " ").title()
            description: str = ""

            for line in lines:
                stripped: str = line.strip()
                if stripped.startswith("# ") and not title:
                    title = stripped[2:].strip()
                elif (
                    stripped
                    and not stripped.startswith("#")
                    and not description
                ):
                    description = stripped

            if not description and len(lines) > 1:
                description = "Documento técnico en formato Markdown."

            mtime_dt = datetime.fromtimestamp(file_path.stat().st_mtime)
            formatted_date: str = mtime_dt.strftime("%d/%m/%Y")

            docs.append(
                {
                    "slug": file_path.stem,
                    "filename": file_path.name,
                    "title": title,
                    "description": description[:140],
                    "date": formatted_date,
                    "size_kb": max(1, round(file_path.stat().st_size / 1024)),
                }
            )
        except OSError:
            continue

    return docs


def get_document(slug: str) -> dict[str, Any] | None:
    """Retrieve and render a markdown document to HTML.

    Performs safe path resolution to guard against traversal,
    extracts the document heading, and converts markdown syntax into
    semantic HTML.

    Args:
        slug: File slug identifier (without extension).

    Returns:
        dict[str, Any] | None: Dictionary containing document title,
            rendered HTML body, and metadata, or None if not found.
    """
    directory: Path = _ensure_docs_dir()
    safe_name: str = re.sub(r"[^a-zA-Z0-9_\-]", "", slug)
    target_path: Path = directory / f"{safe_name}.md"

    if not target_path.is_file():
        return None

    try:
        raw_text: str = target_path.read_text(encoding="utf-8")
        title: str = safe_name.replace("_", " ").title()

        for line in raw_text.splitlines():
            stripped: str = line.strip()
            if stripped.startswith("# "):
                title = stripped[2:].strip()
                break

        html_body: str = markdown.markdown(
            raw_text,
            extensions=[
                "fenced_code",
                "tables",
                "nl2br",
                "sane_lists",
            ],
        )

        mtime_dt = datetime.fromtimestamp(target_path.stat().st_mtime)
        return {
            "slug": safe_name,
            "title": title,
            "html_content": html_body,
            "date": mtime_dt.strftime("%d/%m/%Y"),
        }
    except OSError:
        return None
