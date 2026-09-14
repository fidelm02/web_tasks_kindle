"""Markdown and multi-format document reader for Kindle Scribe.

Objective:
    Scan docs directory recursively, organize files by subfolder,
    and parse Markdown, PDF, and EPUB files for e-ink screens.

Author:
    Fidel Moreno Miranda <fidelm02@gmail.com>
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import markdown

BASE_DIR: Path = Path(__file__).resolve().parent.parent
DOCS_DIR: Path = BASE_DIR / "docs"
SUPPORTED_EXTENSIONS = {".md", ".pdf", ".epub", ".txt"}


def _ensure_docs_dir() -> Path:
    """Ensure the base documents directory exists.

    Args:
        None.

    Returns:
        Path: Resolved directory path for documents.
    """
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    return DOCS_DIR


def list_documents_by_category() -> dict[str, list[dict[str, Any]]]:
    """Scan documents directory recursively grouped by subfolder.

    Discovers all supported document formats (.md, .pdf, .epub, .txt)
    and organizes them into categorized sections based on subfolders.

    Args:
        None.

    Returns:
        dict[str, list[dict[str, Any]]]: Mapping from folder category
            names to lists of document metadata dictionaries.
    """
    directory: Path = _ensure_docs_dir()
    categories: dict[str, list[dict[str, Any]]] = {}

    all_files = sorted(
        [
            f
            for f in directory.rglob("*")
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
        ],
        key=lambda p: (str(p.parent), p.name.lower()),
    )

    for file_path in all_files:
        try:
            rel_parent = file_path.relative_to(directory).parent
            category_name = (
                "General"
                if str(rel_parent) == "."
                else str(rel_parent).replace("_", " ").title()
            )

            ext = file_path.suffix.lower()[1:]
            title = file_path.stem.replace("_", " ").title()
            description = ""

            if ext == "md" or ext == "txt":
                content = file_path.read_text(encoding="utf-8")
                lines = content.splitlines()
                for line in lines:
                    stripped = line.strip()
                    if stripped.startswith("# ") and ext == "md":
                        title = stripped[2:].strip()
                        break
                for line in lines:
                    stripped = line.strip()
                    if (
                        stripped
                        and not stripped.startswith("#")
                        and not description
                    ):
                        description = stripped[:140]
                        break
            elif ext == "pdf":
                description = "Documento PDF listo para lectura o descarga."
            elif ext == "epub":
                description = "Libro electrónico en formato EPUB estándar."

            mtime_dt = datetime.fromtimestamp(file_path.stat().st_mtime)
            rel_path = str(file_path.relative_to(directory))

            doc_info: dict[str, Any] = {
                "name": file_path.name,
                "rel_path": rel_path,
                "ext": ext.upper(),
                "title": title,
                "description": description,
                "date": mtime_dt.strftime("%d/%m/%Y"),
                "size_kb": max(1, round(file_path.stat().st_size / 1024)),
                "is_markdown": ext == "md",
                "is_pdf": ext == "pdf",
                "is_epub": ext == "epub",
            }

            if category_name not in categories:
                categories[category_name] = []
            categories[category_name].append(doc_info)

        except (OSError, ValueError):
            continue

    return categories


def count_all_documents() -> int:
    """Return total count of all supported documents across folders.

    Args:
        None.

    Returns:
        int: Total number of documents.
    """
    directory: Path = _ensure_docs_dir()
    return sum(
        1
        for f in directory.rglob("*")
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def resolve_document_path(rel_path: str) -> Path | None:
    """Safely resolve a document path within docs directory.

    Guards against path traversal attacks by ensuring the target
    resides strictly within DOCS_DIR.

    Args:
        rel_path: Relative file path string.

    Returns:
        Path | None: Resolved existing path, or None if invalid.
    """
    directory: Path = _ensure_docs_dir().resolve()
    target_path = (directory / rel_path).resolve()

    if not target_path.is_file():
        return None

    try:
        target_path.relative_to(directory)
        return target_path
    except ValueError:
        return None


def get_markdown_html(rel_path: str) -> dict[str, Any] | None:
    """Render a specific Markdown document to HTML.

    Args:
        rel_path: Relative file path to the markdown file.

    Returns:
        dict[str, Any] | None: Dictionary with title, rendered HTML
            and metadata, or None if not found.
    """
    file_path = resolve_document_path(rel_path)
    if not file_path or file_path.suffix.lower() != ".md":
        return None

    try:
        raw_text: str = file_path.read_text(encoding="utf-8")
        title: str = file_path.stem.replace("_", " ").title()

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

        mtime_dt = datetime.fromtimestamp(file_path.stat().st_mtime)
        return {
            "rel_path": rel_path,
            "filename": file_path.name,
            "title": title,
            "html_content": html_body,
            "date": mtime_dt.strftime("%d/%m/%Y"),
            "size_kb": max(1, round(file_path.stat().st_size / 1024)),
        }
    except OSError:
        return None
