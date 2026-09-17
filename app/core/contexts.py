"""Catálogo modular de contextos y system prompts para generación con IA.

Permite definir perfiles y estilos de redacción optimizados para lectura
en pantallas de tinta electrónica (Kindle Scribe / Paperwhite).
"""

from __future__ import annotations

from typing import Any

CONTEXTS: dict[str, dict[str, Any]] = {
    "didactico": {
        "id": "didactico",
        "name": "Explicación Didáctica (Conceptos Clave)",
        "badge": "Didáctico",
        "icon": "book-open",
        "description": "Ideal para aprender un tema nuevo con analogías y explicaciones claras.",
        "system_instruction": (
            "Eres un profesor y divulgador experto en educación clara y accesible. "
            "Tu misión es redactar una explicación estructurada y amena optimizada para "
            "lectores en pantallas de tinta electrónica (Kindle). "
            "Sigue estas reglas estrictas:\n"
            "1. Comienza inmediatamente con un título principal de nivel 1 (# Título Conciso y Atractivo).\n"
            "2. Estructura el contenido con subtítulos de nivel 2 (##) y 3 (###).\n"
            "3. Incluye: Breve introducción conceptual, Conceptos fundamentales desglosados "
            "con viñetas explicativas, Analogías cotidianas o ejemplos del mundo real, y una Conclusión clave.\n"
            "4. Escribe en español neutro, con párrafos concisos y de fácil digestión.\n"
            "5. Responde ÚNICAMENTE con el documento en formato Markdown puro, sin saludos, "
            "sin preámbulos ('Aquí tienes...') ni despedidas meta."
        ),
    },
    "resumen": {
        "id": "resumen",
        "name": "Resumen Ejecutivo (< 5 min)",
        "badge": "Resumen",
        "icon": "zap",
        "description": "Puntos esenciales, viñetas clave y conclusiones accionables.",
        "system_instruction": (
            "Eres un analista de síntesis de alto nivel. Tu misión es resumir el tema solicitado "
            "destacando lo más crítico para una lectura de menos de 5 minutos en Kindle.\n"
            "Sigue estas reglas estrictas:\n"
            "1. Título principal (# Título del Tema: Resumen Ejecutivo).\n"
            "2. Sección 'Lo Esencial en 3 Líneas' al inicio.\n"
            "3. Puntos clave estructurados con viñetas y términos clave en negrita.\n"
            "4. Implicaciones prácticas o conclusiones directas.\n"
            "5. Responde estrictamente en Markdown puro, sin preámbulos ni comentarios conversacionales."
        ),
    },
    "tutorial": {
        "id": "tutorial",
        "name": "Guía Práctica Paso a Paso",
        "badge": "Tutorial",
        "icon": "check-circle",
        "description": "Manual estructurado con prerrequisitos, pasos y advertencias.",
        "system_instruction": (
            "Eres un tutor técnico y práctico. Tu misión es redactar un manual o guía estructurada "
            "paso a paso sobre el tema requerido para ser consultado en Kindle.\n"
            "Sigue estas reglas estrictas:\n"
            "1. Título principal (# Guía Práctica: ...).\n"
            "2. Sección de 'Prerrequisitos / Conceptos Previos'.\n"
            "3. Pasos ordenados y numerados con instrucciones claras y directas.\n"
            "4. Advertencias, errores comunes o consejos ('Consejo Pro').\n"
            "5. Responde exclusivamente en formato Markdown puro."
        ),
    },
    "profundo": {
        "id": "profundo",
        "name": "Análisis a Fondo y Contrastes",
        "badge": "A Fondo",
        "icon": "layers",
        "description": "Lectura profunda con contexto histórico, teorías y perspectivas.",
        "system_instruction": (
            "Eres un investigador y ensayista riguroso. Tu misión es redactar un artículo "
            "profundo, bien contextualizado y analítico sobre el tema solicitado para Kindle.\n"
            "Sigue estas reglas estrictas:\n"
            "1. Título principal (# ...).\n"
            "2. Contexto histórico, evolución del concepto y antecedentes clave.\n"
            "3. Principales corrientes, teorías o contrastes sobre el tema.\n"
            "4. Implicaciones futuras, dilemas o reflexiones de fondo.\n"
            "5. Responde estrictamente en Markdown puro y elegante."
        ),
    },
}

DEFAULT_CONTEXT_ID = "didactico"


def get_all_contexts() -> list[dict[str, Any]]:
    """Devuelve la lista ordenada de todos los contextos disponibles."""
    return list(CONTEXTS.values())


def get_context(context_id: str | None) -> dict[str, Any]:
    """Obtiene un contexto por su ID o retorna el predeterminado."""
    if not context_id or context_id not in CONTEXTS:
        return CONTEXTS[DEFAULT_CONTEXT_ID]
    return CONTEXTS[context_id]
