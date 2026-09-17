"""Router para catálogo de documentos y visor de lecturas en Kindle."""

from __future__ import annotations

import urllib.parse
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from app.core.helpers import get_section_title
from app.core.templates import templates
from app.services import email_service, reader_service

router = APIRouter(tags=["reader"])


def render_reader_catalog(
    request: Request,
    section: str,
    base_url: str,
    msg: str | None = None,
    err: str | None = None,
):
    """Render catalog of documents organized by categories.

    Args:
        request: FastAPI HTTP request instance.
        section: Section identifier string.
        base_url: Base URL prefix for links and forms.
        msg: Optional success notification message.
        err: Optional warning/error notification message.

    Returns:
        TemplateResponse: Rendered reader list template.
    """
    categories = reader_service.list_documents_by_category(section=section)
    total_docs = reader_service.count_all_documents(section=section)
    existing = reader_service.get_existing_categories(section=section)
    name = get_section_title(section)
    return templates.TemplateResponse(
        request,
        "reader_list.html",
        {
            "categories": categories,
            "total_docs": total_docs,
            "existing_categories": existing,
            "base_url": base_url,
            "page_title": f"Documentos y Lecturas ({name}) - Kindle Scribe",
            "page_heading": f"Documentos ({name})",
            "msg": msg,
            "err": err,
        },
    )


def render_reader_document(
    request: Request,
    file_path: str,
    section: str,
    base_url: str,
):
    """Render an individual Markdown document for reading.

    Args:
        request: FastAPI HTTP request instance.
        file_path: Relative path to document within section docs.
        section: Section identifier string.
        base_url: Base URL prefix for navigation.

    Returns:
        TemplateResponse: Rendered reader view template.

    Raises:
        HTTPException: If document is not found or not markdown.
    """
    doc = reader_service.get_markdown_html(file_path, section=section)
    if not doc:
        raise HTTPException(
            status_code=404, detail="Documento no encontrado."
        )
    name = get_section_title(section)
    return templates.TemplateResponse(
        request,
        "reader_view.html",
        {
            "doc": doc,
            "base_url": base_url,
            "page_title": f"{doc['title']} - {name}",
            "page_heading": f"Lectura ({name})",
        },
    )


def handle_download_document(file_path: str, section: str):
    """Deliver a document file as an attachment download.

    Args:
        file_path: Relative path to document file.
        section: Section identifier string.

    Returns:
        FileResponse: Attachment download response.

    Raises:
        HTTPException: If file is not found.
    """
    resolved_path = reader_service.resolve_document_path(
        file_path, section=section
    )
    if not resolved_path:
        raise HTTPException(
            status_code=404, detail="Archivo no encontrado."
        )
    return FileResponse(
        path=resolved_path,
        filename=resolved_path.name,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{resolved_path.name}"'
            )
        },
    )


def handle_send_to_kindle(
    file_path: str,
    section: str,
    redirect_url: str,
) -> RedirectResponse:
    """Send document via email to user Kindle recipient address.

    Args:
        file_path: Relative path to document.
        section: Section identifier string.
        redirect_url: Destination URL after sending.

    Returns:
        RedirectResponse: Redirect with status message.

    Raises:
        HTTPException: If document is not found.
    """
    resolved_path = reader_service.resolve_document_path(
        file_path, section=section
    )
    if not resolved_path:
        raise HTTPException(
            status_code=404, detail="Archivo no encontrado."
        )
    success, message = email_service.send_document_to_kindle(resolved_path)
    param = "msg" if success else "err"
    encoded = urllib.parse.quote(message)
    return RedirectResponse(
        f"{redirect_url}?{param}={encoded}", status_code=303
    )


def handle_upload_document(
    file: UploadFile,
    category: str,
    new_category: str,
    section: str,
    redirect_url: str,
) -> RedirectResponse:
    """Save an uploaded document safely and redirect back.

    Args:
        file: UploadFile payload.
        category: Selected existing category name.
        new_category: Optional new category string.
        section: Section identifier string.
        redirect_url: Destination URL.

    Returns:
        RedirectResponse: Redirect with status notification.
    """
    target_folder = (
        new_category.strip() if new_category.strip() else category.strip()
    )
    success, message = reader_service.save_uploaded_document(
        filename=file.filename or "documento",
        file_obj=file.file,
        subfolder=target_folder,
        section=section,
    )
    param = "msg" if success else "err"
    encoded = urllib.parse.quote(message)
    return RedirectResponse(
        f"{redirect_url}?{param}={encoded}", status_code=303
    )


def handle_archive_document(
    file_path: str,
    section: str,
    redirect_url: str,
) -> RedirectResponse:
    """Move document to section archive and redirect back.

    Args:
        file_path: Relative path to document.
        section: Section identifier string.
        redirect_url: Destination URL.

    Returns:
        RedirectResponse: Redirect with notification.
    """
    success, message = reader_service.archive_document(
        file_path, section=section
    )
    param = "msg" if success else "err"
    encoded = urllib.parse.quote(message)
    return RedirectResponse(
        f"{redirect_url}?{param}={encoded}", status_code=303
    )


def handle_delete_document(
    file_path: str,
    section: str,
    redirect_url: str,
) -> RedirectResponse:
    """Permanently delete a document and redirect back.

    Args:
        file_path: Relative path to document.
        section: Section identifier string.
        redirect_url: Destination URL.

    Returns:
        RedirectResponse: Redirect with notification.
    """
    success, message = reader_service.delete_document(
        file_path, section=section
    )
    param = "msg" if success else "err"
    encoded = urllib.parse.quote(message)
    return RedirectResponse(
        f"{redirect_url}?{param}={encoded}", status_code=303
    )


# ============================================================================
# Rutas de Lecturas para Fidel / Biblioteca Principal (/lecturas)
# ============================================================================


@router.get("/lecturas")
def reader_catalog(
    request: Request, msg: str | None = None, err: str | None = None
):
    """Render catalog of documents for Fidel / Default library."""
    return render_reader_catalog(
        request,
        section="fidel",
        base_url="/lecturas",
        msg=msg,
        err=err,
    )


@router.get("/lecturas/view/{file_path:path}")
def reader_document(request: Request, file_path: str):
    """Render an individual Markdown document in Fidel library."""
    return render_reader_document(
        request,
        file_path=file_path,
        section="fidel",
        base_url="/lecturas",
    )


@router.get("/lecturas/download/{file_path:path}")
def download_document(file_path: str):
    """Deliver a document download from Fidel library."""
    return handle_download_document(file_path=file_path, section="fidel")


@router.post("/lecturas/send/{file_path:path}")
def send_to_kindle(file_path: str):
    """Send document from Fidel library to Kindle via email."""
    return handle_send_to_kindle(
        file_path=file_path,
        section="fidel",
        redirect_url="/lecturas",
    )


@router.post("/lecturas/upload")
async def upload_document(
    file: UploadFile = File(...),
    category: str = Form(""),
    new_category: str = Form(""),
) -> RedirectResponse:
    """Upload a document to Fidel library from desktop or mobile."""
    return handle_upload_document(
        file=file,
        category=category,
        new_category=new_category,
        section="fidel",
        redirect_url="/lecturas",
    )


@router.post("/lecturas/archive/{file_path:path}")
def archive_document(file_path: str) -> RedirectResponse:
    """Move a document to Fidel archive directory with timestamp."""
    return handle_archive_document(
        file_path=file_path,
        section="fidel",
        redirect_url="/lecturas",
    )


@router.post("/lecturas/delete/{file_path:path}")
def delete_document(file_path: str) -> RedirectResponse:
    """Permanently delete a document from Fidel library."""
    return handle_delete_document(
        file_path=file_path,
        section="fidel",
        redirect_url="/lecturas",
    )


# ============================================================================
# Rutas Dinámicas de Lecturas por Sección (/{section}/lecturas)
# ============================================================================


@router.get("/{section}/lecturas")
def section_reader_catalog(
    section: str,
    request: Request,
    msg: str | None = None,
    err: str | None = None,
):
    """Render documents catalog for given section library."""
    return render_reader_catalog(
        request,
        section=section,
        base_url=f"/{section}/lecturas",
        msg=msg,
        err=err,
    )


@router.get("/{section}/lecturas/view/{file_path:path}")
def section_reader_document(
    section: str,
    file_path: str,
    request: Request,
):
    """Render an individual Markdown document in given section library."""
    return render_reader_document(
        request,
        file_path=file_path,
        section=section,
        base_url=f"/{section}/lecturas",
    )


@router.get("/{section}/lecturas/download/{file_path:path}")
def section_download_document(section: str, file_path: str):
    """Deliver a document download from given section library."""
    return handle_download_document(file_path=file_path, section=section)


@router.post("/{section}/lecturas/send/{file_path:path}")
def section_send_to_kindle(section: str, file_path: str):
    """Send document from given section to Kindle via email."""
    return handle_send_to_kindle(
        file_path=file_path,
        section=section,
        redirect_url=f"/{section}/lecturas",
    )


@router.post("/{section}/lecturas/upload")
async def section_upload_document(
    section: str,
    file: UploadFile = File(...),
    category: str = Form(""),
    new_category: str = Form(""),
) -> RedirectResponse:
    """Upload a document to given section library."""
    return handle_upload_document(
        file=file,
        category=category,
        new_category=new_category,
        section=section,
        redirect_url=f"/{section}/lecturas",
    )


@router.post("/{section}/lecturas/archive/{file_path:path}")
def section_archive_document(
    section: str,
    file_path: str,
) -> RedirectResponse:
    """Move document to section archive directory with timestamp."""
    return handle_archive_document(
        file_path=file_path,
        section=section,
        redirect_url=f"/{section}/lecturas",
    )


@router.post("/{section}/lecturas/delete/{file_path:path}")
def section_delete_document(
    section: str,
    file_path: str,
) -> RedirectResponse:
    """Permanently delete document from section library."""
    return handle_delete_document(
        file_path=file_path,
        section=section,
        redirect_url=f"/{section}/lecturas",
    )
