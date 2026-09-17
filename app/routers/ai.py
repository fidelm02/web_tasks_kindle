"""Router para generación de lecturas con Google Gemini AI."""

from __future__ import annotations

import urllib.parse
from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.core.contexts import get_all_contexts, get_context
from app.core.templates import templates
from app.services import ai_service, email_service, reader_service, section_service

router = APIRouter(prefix="/ia", tags=["ai"])


@router.get("")
@router.get("/")
def ai_generator_page(
    request: Request,
    msg: str | None = None,
    err: str | None = None,
):
    """Renderiza una página completa dedicada a la generación de lecturas con IA."""
    contexts = get_all_contexts()
    sections = [
        s for s in section_service.get_active_sections() if s.get("has_docs")
    ]
    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "contexts": contexts,
            "sections": sections,
            "msg": msg,
            "err": err,
        },
    )


@router.post("/generate")
async def generate_reading_endpoint(
    prompt: str = Form(...),
    context_id: str = Form("didactico"),
    section: str = Form("fidel"),
    category_hint: str = Form(""),
    send_email: str | None = Form(None),
    redirect_to: str = Form("/"),
) -> RedirectResponse:
    """Genera un documento Markdown con Gemini, lo guarda y opcionalmente lo envía al Kindle.

    Args:
        prompt: Tema o pregunta del usuario.
        context_id: Identificador del contexto o estilo pedagógico.
        section: Sección destino donde se archivará la lectura (fidel, lau, etc.).
        category_hint: Categoría o subcarpeta sugerida (opcional).
        send_email: Checkbox si se debe despachar copia a Amazon Kindle por email.
        redirect_to: URL de retorno en caso de error.

    Returns:
        RedirectResponse: Redirige al visor de lectura o al home con aviso.
    """
    clean_prompt = prompt.strip()
    if not clean_prompt:
        encoded = urllib.parse.quote("Debes ingresar un tema para generar la lectura.")
        return RedirectResponse(f"{redirect_to}?err={encoded}", status_code=303)

    # 1. Llamada al servicio de IA con Gemini
    success, msg, result = ai_service.generate_reading_markdown(
        user_prompt=clean_prompt,
        context_id=context_id,
        category_hint=category_hint,
    )

    if not success or not result:
        encoded_err = urllib.parse.quote(msg or "Error al generar la lectura con IA.")
        return RedirectResponse(f"{redirect_to}?err={encoded_err}", status_code=303)

    # 2. Guardar en el directorio de documentos de la sección elegida
    target_section = section.strip() or "fidel"
    save_ok, save_msg, saved_path = reader_service.save_generated_document(
        filename=result["filename"],
        content=result["markdown"],
        subfolder=result["category"],
        section=target_section,
    )

    if not save_ok or not saved_path:
        encoded_err = urllib.parse.quote(f"Error al guardar archivo: {save_msg}")
        return RedirectResponse(f"{redirect_to}?err={encoded_err}", status_code=303)

    email_notice = ""
    # 3. Envío opcional por correo al Kindle
    is_email_requested = send_email in ("on", "true", "1", "yes")
    if is_email_requested:
        email_ok, email_msg = email_service.send_document_to_kindle(saved_path)
        if email_ok:
            email_notice = " y se envió a tu correo Kindle"
        else:
            email_notice = f" (aviso de correo: {email_msg})"

    # 4. Construir URL de redirección directa al visor de lectura
    rel_path = (
        f"{result['category']}/{result['filename']}"
        if result["category"] and result["category"].lower() != "general"
        else result["filename"]
    )

    if target_section in ("fidel", "default"):
        view_url = f"/lecturas/view/{urllib.parse.quote(rel_path)}"
    else:
        view_url = f"/{target_section}/lecturas/view/{urllib.parse.quote(rel_path)}"

    final_msg = urllib.parse.quote(
        f"✓ Lectura generada con éxito{email_notice}."
    )
    return RedirectResponse(f"{view_url}?msg={final_msg}", status_code=303)
