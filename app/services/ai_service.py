"""Servicio de generación de artículos y lecturas con Google Gemini AI.

Utiliza el SDK oficial google-genai para interactuar con modelos Gemini
y generar documentos Markdown educativos listos para leer en Kindle.
"""

from __future__ import annotations

from datetime import datetime
import os
import re
from typing import Any
from google import genai
from google.genai import types

from app.core.contexts import get_context

# Cargar configuración y credenciales sin exponerlas en logs
try:
    from app import constants as config
except ImportError:
    config = None  # type: ignore

CANDIDATE_MODELS = ["gemini-3.6-flash", "gemini-3.7-flash", "gemini-2.5-flash"]
MODEL_NAME = CANDIDATE_MODELS[0]


def _get_api_token() -> str:
    """Obtiene el token de autenticación de Gemini desde constants o entorno."""
    if config is not None:
        token = getattr(config, "GEMINI_TOKEN", None)
        if token and str(token).strip():
            return str(token).strip()
    return os.getenv("GEMINI_ACCESS_TOKEN", os.getenv("GEMINI_API_KEY", "")).strip()


def _sanitize_name_part(text: str) -> str:
    """Limpia caracteres no válidos para nombres de archivo en el sistema."""
    # Eliminar acentos para nombres de archivo seguros en Kindle/Linux
    cleaned = re.sub(r'[\\/*?:"<>|]', "", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "Documento"


def _extract_title_and_category(
    prompt: str,
    raw_markdown: str,
    category_hint: str = "",
) -> tuple[str, str, str]:
    """Extrae el título principal, categoría general y nombre de archivo jerárquico.

    Returns:
        tuple[str, str, str]: (titulo, categoria, nombre_archivo_md)
    """
    lines = raw_markdown.splitlines()
    title = ""
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped[2:].strip()
            break

    if not title:
        title = prompt.strip().capitalize()
        if len(title) > 60:
            title = title[:57] + "..."

    # Determinar categoría
    category = category_hint.strip()
    if not category or category.lower() == "general":
        # Clasificación heurística simple basada en palabras clave
        low_prompt = (prompt + " " + title).lower()
        if any(w in low_prompt for w in ("fisica", "quimica", "biologia", "astronomia", "cuantica", "ciencia")):
            category = "Ciencia"
        elif any(w in low_prompt for w in ("python", "linux", "codigo", "programacion", "software", "api", "docker", "fastapi")):
            category = "Tecnologia"
        elif any(w in low_prompt for w in ("historia", "guerra", "imperio", "roma", "siglo", "revolucion")):
            category = "Historia"
        elif any(w in low_prompt for w in ("filosofia", "etica", "sociedad", "psicologia", "mente")):
            category = "Filosofia"
        elif any(w in low_prompt for w in ("salud", "medicina", "nutricion", "ejercicio", "dormir")):
            category = "Salud"
        elif any(w in low_prompt for w in ("casa", "hogar", "cocina", "receta", "reparacion", "plantas")):
            category = "Hogar"
        elif any(w in low_prompt for w in ("habito", "productividad", "trabajo", "tiempo", "finanzas", "dinero")):
            category = "Productividad"
        else:
            category = "General"

    clean_category = _sanitize_name_part(category).title()
    clean_title = _sanitize_name_part(title)

    # Nombre taxonómico: De lo general a lo particular (ej. Fisica - Teoria Cuantica.md)
    if clean_category.lower() != "general" and not clean_title.lower().startswith(clean_category.lower()):
        filename = f"{clean_category} - {clean_title}.md"
    else:
        filename = f"{clean_title}.md"

    # Acotar largo del nombre si excede límites de SO
    if len(filename) > 120:
        stem = filename[:-3][:110]
        filename = f"{stem}.md"

    return title, clean_category, filename


def generate_reading_markdown(
    user_prompt: str,
    context_id: str = "didactico",
    category_hint: str = "",
) -> tuple[bool, str, dict[str, Any] | None]:
    """Genera una lectura en Markdown utilizando la API de Google Gemini.

    Args:
        user_prompt: Tema o pregunta proporcionada por el usuario.
        context_id: ID del contexto pedagógico (didactico, resumen, tutorial, profundo).
        category_hint: Categoría o subcarpeta sugerida (opcional).

    Returns:
        tuple[bool, str, dict | None]:
            - bool: Éxito de la operación.
            - str: Mensaje descriptivo o mensaje de error legible.
            - dict: Datos estructurados del documento (title, category, filename, markdown, metadata).
    """
    token = _get_api_token()
    if not token:
        return (
            False,
            "No se encontró GEMINI_TOKEN configurado en app/constants.py ni variable de entorno.",
            None,
        )

    clean_prompt = user_prompt.strip()
    if not clean_prompt:
        return False, "El tema o prompt no puede estar vacío.", None

    context_info = get_context(context_id)
    system_instruction = context_info["system_instruction"]

    try:
        client = genai.Client(api_key=token)

        generation_config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.7,
        )

        prompt_payload = (
            f"Tema solicitado: {clean_prompt}\n"
            f"Categoría o ámbito preferido: {category_hint or 'General'}\n"
            "Por favor genera la lectura completa siguiendo estrictamente el formato Markdown."
        )

        response = None
        last_exc = None
        used_model = MODEL_NAME

        for model_cand in CANDIDATE_MODELS:
            try:
                response = client.models.generate_content(
                    model=model_cand,
                    contents=prompt_payload,
                    config=generation_config,
                )
                used_model = model_cand
                break
            except Exception as e:
                last_exc = e
                continue

        if response is None:
            raise last_exc or RuntimeError("No fue posible generar respuesta con los modelos disponibles.")

        raw_text = (response.text or "").strip()
        if not raw_text:
            return False, "La respuesta recibida de Gemini estuvo vacía.", None

        # Limpiar bloques envolventes de markdown si el modelo incluyó ```markdown ... ```
        cleaned_text = raw_text
        if cleaned_text.startswith("```markdown"):
            cleaned_text = cleaned_text[len("```markdown") :].strip()
        elif cleaned_text.startswith("```"):
            cleaned_text = cleaned_text[len("```") :].strip()
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3].strip()

        title, category, filename = _extract_title_and_category(
            clean_prompt, cleaned_text, category_hint=category_hint
        )

        # Preparar encabezado legible con metadatos para Kindle
        fecha_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        metadata_header = (
            f"> **Categoría:** {category} | **Estilo:** {context_info['name']}  \n"
            f"> **Fecha:** {fecha_str} | **Generador:** Gemini AI ({used_model})\n\n---\n\n"
        )

        # Si el texto ya comienza con el título #, insertar la metadata justo después
        first_line_end = cleaned_text.find("\n")
        if cleaned_text.startswith("# ") and first_line_end != -1:
            first_line = cleaned_text[:first_line_end].strip()
            rest = cleaned_text[first_line_end:].strip()
            final_markdown = f"{first_line}\n\n{metadata_header}{rest}\n"
        else:
            final_markdown = f"# {title}\n\n{metadata_header}{cleaned_text}\n"

        result = {
            "title": title,
            "category": category,
            "filename": filename,
            "markdown": final_markdown,
            "context_id": context_id,
            "context_name": context_info["name"],
            "model": used_model,
            "created_at": datetime.now().isoformat(),
        }

        return True, "Lectura generada exitosamente.", result

    except Exception as exc:
        err_msg = str(exc)
        # Ofrecer mensaje amigable si es de autenticación o cuota
        if "API_KEY_INVALID" in err_msg or "401" in err_msg or "403" in err_msg:
            friendly = "Error de autenticación con la API de Google Gemini (verifica tu GEMINI_TOKEN)."
        elif "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg:
            friendly = "Límite de cuota alcanzado en la API de Google Gemini. Intenta en unos minutos."
        else:
            friendly = f"Error al consultar Gemini: {err_msg}"
        return False, friendly, None
