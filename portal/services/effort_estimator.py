"""Servicio de análisis y estimación de esfuerzo con Inteligencia Artificial (Gemini).

Utiliza Google Gemini (gemini-3.6-flash y fallbacks) para descomponer tareas, evaluar complejidad,
calcular Story Points según la serie de Fibonacci y sugerir subtareas y riesgos.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.constants import GEMINI_TOKEN

logger = logging.getLogger(__name__)

ESTIMATOR_PROMPT_TEMPLATE = """Eres un Senior Technical Product Manager y Agile Coach experto en Scrum y estimación de software y proyectos.
Tu objetivo es analizar la siguiente tarea, evaluar su complejidad técnica u operativa, calcular el esfuerzo en Story Points (Fibonacci: 1, 2, 3, 5, 8, 13, 21), estimar las horas aproximadas de dedicación, descomponerla en subtareas accionables e identificar consideraciones o riesgos.

DATOS DE LA TAREA:
- Título: {title}
- Descripción: {description}
- Proyecto / Scope: {scope}
- Contexto Adicional: {context}

CRITERIOS DE STORY POINTS:
- 1 SP: Tarea trivial, inmediata, sin incertidumbre (< 1 hora).
- 2 SP: Tarea pequeña, clara, cambio simple o rutinario (1 - 3 horas).
- 3 SP: Tarea mediana, esfuerzo moderado, pocos bloqueos (3 - 6 horas).
- 5 SP: Tarea de complejidad considerable, posible coordinación o investigación (1 - 2 días).
- 8 SP: Tarea grande, alta incertidumbre o múltiples dependencias (3 - 4 días).
- 13 SP: Épica o tarea crítica que debería dividirse en subtareas menores (1+ semanas).

Debes responder ÚNICAMENTE con un objeto JSON válido con la siguiente estructura exacta (sin texto introductorio ni formato markdown extra):
{{
  "story_points": 3,
  "estimated_hours": 4.5,
  "complexity": "Media",
  "summary": "Breve justificación del esfuerzo y razonamiento de la puntuación.",
  "subtasks": [
    "Subtarea 1 accionable",
    "Subtarea 2 accionable",
    "Subtarea 3 accionable"
  ],
  "risks_and_considerations": [
    "Riesgo o dependencia relevante",
    "Consideración técnica u operativa"
  ],
  "is_recurrent_candidate": false,
  "recurrent_reasoning": "Explicación de si esta tarea tiene naturaleza repetitiva/rutina (ej. limpieza, gym, backups) o es un hito único/proyecto.",
  "suggested_frequency": "none"
}}
"""

MODEL_CANDIDATES = [
    "gemini-3.6-flash",
    "gemini-flash-latest",
    "gemini-3.1-flash-lite",
]


def _clean_json_response(raw_text: str) -> dict[str, Any]:
    """Limpia bloques de código markdown y parsea JSON."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()
    return json.loads(cleaned)


def estimate_task_effort(
    title: str,
    description: str = "",
    scope: str = "fidel",
    context: str = "",
) -> dict[str, Any]:
    """Estima el esfuerzo de una tarea usando Gemini con reintentos y fallback de modelos.

    Args:
        title: Título de la tarea.
        description: Descripción detallada.
        scope: Ámbito o proyecto (fidel, casa, lau, etc.).
        context: Información adicional sobre el entorno o requerimiento.

    Returns:
        dict[str, Any]: Estimación estructurada con story_points, hours, subtasks, etc.
    """
    if not title or not title.strip():
        return {
            "error": "El título de la tarea no puede estar vacío.",
            "story_points": 1,
            "estimated_hours": 1.0,
            "complexity": "Baja",
            "summary": "Tarea sin título especificado.",
            "subtasks": [],
            "risks_and_considerations": [],
        }

    prompt = ESTIMATOR_PROMPT_TEMPLATE.format(
        title=title.strip(),
        description=(description or "Sin descripción detallada").strip(),
        scope=scope.strip(),
        context=(context or "Ninguno").strip(),
    )

    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_TOKEN)
    except Exception as init_err:
        logger.error("No se pudo instanciar cliente genai: %s", init_err)
        return _fallback_estimation(title, scope, str(init_err))

    last_error = None
    for model_name in MODEL_CANDIDATES:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            raw_text = response.text or ""
            parsed = _clean_json_response(raw_text)

            # Validación y saneamiento de campos
            sp = parsed.get("story_points", 2)
            try:
                sp = float(sp)
            except (ValueError, TypeError):
                sp = 2.0

            hrs = parsed.get("estimated_hours", 2.0)
            try:
                hrs = float(hrs)
            except (ValueError, TypeError):
                hrs = 2.0

            return {
                "title": title.strip(),
                "scope": scope,
                "story_points": sp,
                "estimated_hours": hrs,
                "complexity": parsed.get("complexity", "Media"),
                "summary": parsed.get("summary", "Estimación calculada automáticamente con IA."),
                "subtasks": parsed.get("subtasks", []),
                "risks_and_considerations": parsed.get("risks_and_considerations", []),
                "is_recurrent_candidate": bool(parsed.get("is_recurrent_candidate", False)),
                "recurrent_reasoning": parsed.get(
                    "recurrent_reasoning",
                    "No se detecta patrón de recurrencia evidente."
                ),
                "suggested_frequency": parsed.get("suggested_frequency", "none"),
                "model": model_name,
            }
        except Exception as exc:
            logger.warning("Fallo al consultar modelo %s: %s", model_name, exc)
            last_error = exc
            continue

    logger.error("Todos los modelos Gemini fallaron. Último error: %s", last_error)
    return _fallback_estimation(title, scope, str(last_error))


def _fallback_estimation(title: str, scope: str, err_msg: str) -> dict[str, Any]:
    """Retorna una estimación heurística si el servicio de IA no responde."""
    return {
        "title": title.strip(),
        "scope": scope,
        "story_points": 2.0,
        "estimated_hours": 3.0,
        "complexity": "Media",
        "summary": f"Estimación manual por contingencia ({err_msg})",
        "subtasks": [
            f"Planificar y desglosar requerimiento para '{title}'",
            "Ejecutar implementación principal",
            "Realizar pruebas de validación y entrega",
        ],
        "risks_and_considerations": [
            "Revisar dependencias técnicas antes de comenzar",
            "Alinear requerimientos con el equipo",
        ],
        "is_recurrent_candidate": False,
        "recurrent_reasoning": "Estimación de contingencia sin análisis profundo.",
        "suggested_frequency": "none",
        "model": "fallback",
    }
