"""Servicio de Salud, Fitness y Programas Trimestrales (3 Meses).

Gestiona perfiles individuales (Fidel y Lau), estadísticas de asistencia al gimnasio,
registro y gráfica de peso, hábitos saludables (caminata, agua, sueño)
y programas de transformación con rutinas y planes nutricionales.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
import logging
from pathlib import Path
from typing import Any
import uuid

from filelock import FileLock

from app import storage
from portal.services import effort_estimator, recurrent_engine

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_DATA_DIR = _BASE_DIR / "data"
_HEALTH_FILE = _DATA_DIR / "health_data.json"
_HEALTH_LOCK = _DATA_DIR / "health_data.json.lock"


def _get_initial_health_data() -> dict[str, Any]:
    """Genera la estructura de datos inicial con perfiles para Fidel y Lau."""
    today_str = date.today().isoformat()
    three_weeks_ago = (date.today() - timedelta(days=21)).isoformat()
    two_weeks_ago = (date.today() - timedelta(days=14)).isoformat()
    one_week_ago = (date.today() - timedelta(days=7)).isoformat()

    return {
        "active_profile": "fidel",
        "profiles": {
            "fidel": {
                "id": "fidel",
                "name": "Fidel",
                "avatar": "🏋️‍♂️",
                "gender": "male",
                "height_cm": 165,
                "initial_weight": 93.0,
                "current_weight": 93.0,
                "target_weight": 68.0,
                "weekly_gym_goal": 4,
                "daily_walking_hours": 1.0,
                "daily_steps_goal": 10000,
                "water_goal_liters": 3.0,
                "weight_logs": [
                    {"date": today_str, "weight": 93.0, "notes": "Medición inicial real (1.65m - 93kg)"},
                ],
                "habits_history": {
                    "gym": [today_str],
                    "walk": [today_str],
                    "water": [today_str],
                },
                "active_program": {
                    "id": "prog-fidel-12w",
                    "title": "Programa Trimestral: Transformación Física & Pérdida de Grasa (-8kg en 12 Semanas)",
                    "target_loss_kg": 8.0,
                    "duration_weeks": 12,
                    "start_date": today_str,
                    "current_week": 1,
                    "nutrition_plan": {
                        "daily_calories": 2100,
                        "protein_g": 175,
                        "carbs_g": 185,
                        "fats_g": 65,
                        "strategy": "Déficit calórico calculado para hombre de 1.65m y 93kg. Tasa metabólica basal estimada ~1,820 kcal, gasto total diario con actividad física de ~2,600 kcal. Déficit calórico moderado de 500 kcal/día para perder ~0.6 kg de grasa por semana preservando masa muscular con 175g de proteína (2.0g/kg de masa magra).",
                        "meal_guidelines": [
                            "Desayuno: Proteína de alto valor biológico (huevos/claras) con carbohidratos complejos (avena) y frutos rojos.",
                            "Comida / Pre-entreno: Pechuga de pollo, res magra o salmón con arroz jazmín o camote y abundantes verduras 90-120 min antes de entrenar.",
                            "Post-entreno / Cena: Pescado blanco, atún o batido whey con ensalada verde grande y una cucharada de aceite de oliva virgen extra.",
                            "Hidratación y Pasos: Mínimo 3.0 litros de agua distribuidos en el día y caminata diaria de 60 minutos (cardio LISS en Zona 2 para quema lipolítica sin impacto articular).",
                        ],
                    },
                    "workout_split": {
                        "type": "Torso / Pierna + Acondicionamiento (4 Días Fuerza + 2 Días Cardio LISS)",
                        "days_per_week": 4,
                        "days": [
                            {
                                "day_name": "Lunes",
                                "focus": "Torso A: Fuerza e Hipertrofia (Pecho & Espalda pesado)",
                                "exercises": [
                                    "Press de banca plano con barra (4 series x 6-8 reps)",
                                    "Remo con barra pendlay o apoyo en pecho (4 series x 8-10 reps)",
                                    "Press militar con mancuernas (3 series x 10 reps)",
                                    "Jalón al pecho agarre neutro (3 series x 10-12 reps)",
                                    "Elevaciones laterales de hombro en polea (3 series x 15 reps)",
                                    "Supererie Bíceps/Tríceps (3 series x 12 reps)",
                                ],
                            },
                            {
                                "day_name": "Martes",
                                "focus": "Pierna A: Cuádriceps y Cadena Posterior",
                                "exercises": [
                                    "Sentadilla trasera profunda o con mancuernas (4 series x 8 reps)",
                                    "Prensa 45° con rango completo (3 series x 10-12 reps)",
                                    "Curl femoral acostado o sentado (3 series x 12 reps)",
                                    "Zancadas estáticas o búlgaras (3 series x 10 por pierna)",
                                    "Elevación de gemelos de pie (4 series x 15 reps)",
                                    "Plancha abdominal isométrica (3 series x 45 seg)",
                                ],
                            },
                            {
                                "day_name": "Miércoles",
                                "focus": "Descanso Activo & Caminata Regenerativa",
                                "exercises": [
                                    "Caminata al aire libre de 60 minutos (8,000 - 10,000 pasos en Zona 2 cardíaca)",
                                    "Sesión de estiramiento y movilidad articular (15 min)",
                                ],
                            },
                            {
                                "day_name": "Jueves",
                                "focus": "Torso B: Volumen & Definición (Hombro & Espalda alta)",
                                "exercises": [
                                    "Press inclinado con mancuernas (4 series x 8-10 reps)",
                                    "Dominadas asistidas o remo en polea baja (4 series x 10 reps)",
                                    "Aperturas en polea para pecho (3 series x 12 reps)",
                                    "Face pulls para deltoides posterior (4 series x 15 reps)",
                                    "Fondos en paralelas o banco (3 series x 10 reps)",
                                    "Curl martillo con mancuerna (3 series x 12 reps)",
                                ],
                            },
                            {
                                "day_name": "Viernes",
                                "focus": "Pierna B: Isquiosurales, Glúteo & Core",
                                "exercises": [
                                    "Peso muerto rumano con mancuernas/barra (4 series x 8-10 reps)",
                                    "Hip Thrust con barra (4 series x 10 reps)",
                                    "Extensión de cuádriceps en máquina (3 series x 12-15 reps)",
                                    "Paseo del granjero con mancuernas pesadas (3 rondas x 40m)",
                                    "Elevaciones de piernas colgado para abdomen (3 series x 12 reps)",
                                ],
                            },
                            {
                                "day_name": "Sábado",
                                "focus": "Cardio Recreativo & Actividad Familiar",
                                "exercises": [
                                    "Caminata larga, senderismo o paseo en bicicleta de 60-90 minutos",
                                ],
                            },
                            {
                                "day_name": "Domingo",
                                "focus": "Descanso Total, Pesaje Dominical y Meal Prep",
                                "exercises": [
                                    "Pesaje en ayunas y registro en el portal",
                                    "Preparación de comidas saludables para la semana",
                                ],
                            },
                        ],
                    },
                    "phases": [
                        {
                            "phase": 1,
                            "name": "Fase 1: Adaptación Anatómica y Déficit Inicial",
                            "weeks": "Semanas 1-4",
                            "goal": "Acondicionamiento articular, asimilación del déficit calórico sin fatiga y consolidación del hábito de 4 días de gym.",
                            "status": "in_progress",
                        },
                        {
                            "phase": 2,
                            "name": "Fase 2: Sobrecarga Progresiva e Intensidad",
                            "weeks": "Semanas 5-8",
                            "goal": "Aumento progresivo de cargas, cardio en zona 2 para acelerar oxidación de ácidos grasos y retención muscular.",
                            "status": "upcoming",
                        },
                        {
                            "phase": 3,
                            "name": "Fase 3: Definición y Consolidación de Hábitos",
                            "weeks": "Semanas 9-12",
                            "goal": "Alcanzar el peso objetivo (76-77kg), mejorar la composición corporal y definir protocolo de mantenimiento metabólico.",
                            "status": "upcoming",
                        },
                    ],
                },
            },
            "lau": {
                "id": "lau",
                "name": "Lau",
                "avatar": "🧘‍♀️",
                "gender": "female",
                "height_cm": 165,
                "initial_weight": 64.0,
                "current_weight": 62.5,
                "target_weight": 58.0,
                "weekly_gym_goal": 3,
                "daily_walking_hours": 0.75,
                "daily_steps_goal": 8000,
                "water_goal_liters": 2.5,
                "weight_logs": [
                    {"date": two_weeks_ago, "weight": 63.8, "notes": "Inicio del registro"},
                    {"date": one_week_ago, "weight": 63.1, "notes": "Buena adherencia a clases"},
                    {"date": today_str, "weight": 62.5, "notes": "Progreso constante -1.5kg"},
                ],
                "habits_history": {
                    "gym": [
                        (date.today() - timedelta(days=5)).isoformat(),
                        (date.today() - timedelta(days=2)).isoformat(),
                    ],
                    "walk": [
                        (date.today() - timedelta(days=4)).isoformat(),
                        (date.today() - timedelta(days=2)).isoformat(),
                        today_str,
                    ],
                    "water": [
                        (date.today() - timedelta(days=1)).isoformat(),
                        today_str,
                    ],
                },
                "active_program": {
                    "id": "prog-lau-12w",
                    "title": "Programa 12 Semanas: Tonificación, Flexibilidad y Salud Integral (-5kg)",
                    "target_loss_kg": 5.0,
                    "duration_weeks": 12,
                    "start_date": (date.today() - timedelta(days=14)).isoformat(),
                    "current_week": 3,
                    "nutrition_plan": {
                        "daily_calories": 1650,
                        "protein_g": 115,
                        "carbs_g": 160,
                        "fats_g": 50,
                        "strategy": "Déficit nutricional balanceado y saciante con alimentos enteros, antioxidantes y proteína magra.",
                        "meal_guidelines": [
                            "Desayuno: Omelette con espinacas y rebanada de pan masa madre.",
                            "Comida: Salmón o pechuga con quinoa y ensalada de espinaca con nueces.",
                            "Snack: Yogur griego natural con semillas de chía o puñado de almendras.",
                            "Cena: Crema de calabacín y rollitos de pavo o ensalada ligera.",
                        ],
                    },
                    "workout_split": {
                        "type": "Entrenamiento Funcional, Pilates & Fuerza Liviana (3 Días)",
                        "days_per_week": 3,
                        "days": [
                            {"day_name": "Lunes", "focus": "Fuerza Full-Body & Glúteo", "exercises": ["Sentadilla Goblet", "Puente de glúteos", "Remo con mancuernas", "Press de hombro liviano"]},
                            {"day_name": "Miércoles", "focus": "Pilates / Movilidad & Core", "exercises": ["Planchas dinámicas", "Bird-dog", "Hundred de Pilates", "Movilidad de cadera"]},
                            {"day_name": "Viernes", "focus": "Circuito HIIT de bajo impacto & Brazos", "exercises": ["Kettlebell swings", "Step-ups", "Fondos en silla", "Caminata inclinada 25 min"]},
                        ],
                    },
                    "phases": [
                        {"phase": 1, "name": "Fase 1: Activación y Movilidad", "weeks": "Semanas 1-4", "goal": "Acondicionamiento y hábito de hidratación", "status": "in_progress"},
                        {"phase": 2, "name": "Fase 2: Tonificación y Quema de Grasa", "weeks": "Semanas 5-8", "goal": "Incremento de resistencia muscular", "status": "upcoming"},
                        {"phase": 3, "name": "Fase 3: Consolidación y Escultura", "weeks": "Semanas 9-12", "goal": "Alcanzar peso meta de 58kg", "status": "upcoming"},
                    ],
                },
            },
        },
    }


def _ensure_health_file():
    """Garantiza la existencia del archivo de salud con datos iniciales."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not _HEALTH_FILE.exists():
        data = _get_initial_health_data()
        with FileLock(_HEALTH_LOCK):
            with open(_HEALTH_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)


def get_health_data() -> dict[str, Any]:
    """Lee todos los datos de salud de manera segura."""
    _ensure_health_file()
    with FileLock(_HEALTH_LOCK):
        try:
            with open(_HEALTH_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.error("Error al leer health_data.json: %s", exc)
            return _get_initial_health_data()


def save_health_data(data: dict[str, Any]) -> None:
    """Guarda atómicamente el estado de salud."""
    _ensure_health_file()
    with FileLock(_HEALTH_LOCK):
        temp_file = _HEALTH_FILE.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        temp_file.replace(_HEALTH_FILE)


def get_profile_data(profile_id: str = "fidel") -> dict[str, Any]:
    """Obtiene los datos consolidados y estadísticas calculadas de un perfil."""
    data = get_health_data()
    profiles = data.get("profiles", {})
    if profile_id not in profiles:
        profile_id = "fidel"

    profile = profiles.get(profile_id, {})
    gym_stats = compute_gym_statistics(profile_id, profile)
    weight_stats = compute_weight_statistics(profile)
    program = profile.get("active_program")

    return {
        "profile": profile,
        "profile_id": profile_id,
        "all_profiles": [
            {"id": pid, "name": p.get("name", pid.title()), "avatar": p.get("avatar", "👤")}
            for pid, p in profiles.items()
        ],
        "gym_stats": gym_stats,
        "weight_stats": weight_stats,
        "program": program,
    }


def compute_gym_statistics(profile_id: str, profile: dict[str, Any]) -> dict[str, Any]:
    """Calcula las métricas de asistencia al gimnasio analizando tareas reales y check-ins."""
    # 1. Leer tareas completadas en Kindle Tasks para el scope de la persona
    scope = profile_id if profile_id in ("fidel", "lau") else "fidel"
    tasks = storage.read_tasks(scope=scope)

    gym_task_matches = []
    gym_keywords = ["gym", "gimnasio", "entrenar", "ejercicio", "pesas", "workout"]

    for t in tasks:
        title_lower = (t.get("title") or "").lower()
        if any(kw in title_lower for kw in gym_keywords):
            gym_task_matches.append(t)

    # Días completados desde tareas
    task_completed_dates = set()
    for t in gym_task_matches:
        if t.get("status") == "completed" or t.get("stage") == "done":
            c_at = t.get("completed_at") or t.get("target_date") or t.get("created_at")
            if c_at:
                date_part = str(c_at)[:10]
                task_completed_dates.add(date_part)

    # 2. Sumar días registrados en check-ins de hábitos directos
    habits = profile.get("habits_history", {})
    direct_gym_dates = set(habits.get("gym", []))
    all_gym_dates = sorted(task_completed_dates.union(direct_gym_dates))

    today = date.today()
    today_str = today.isoformat()

    # Cálculo semanal (últimos 7 días)
    week_start = today - timedelta(days=today.weekday())  # Lunes de esta semana
    gym_this_week = sum(1 for d in all_gym_dates if d >= week_start.isoformat())

    # Cálculo mensual (mes actual)
    month_start_str = today.strftime("%Y-%m-01")
    gym_this_month = sum(1 for d in all_gym_dates if d >= month_start_str)

    weekly_goal = profile.get("weekly_gym_goal", 4)
    weekly_percent = round((gym_this_week / weekly_goal) * 100, 1) if weekly_goal > 0 else 0

    # Racha actual de días consecutivos o semanas
    streak = 0
    cur_date = today
    # Verificar si hoy o ayer se fue al gym para no romper racha
    attended_today = today_str in all_gym_dates
    check_date = cur_date if attended_today else cur_date - timedelta(days=1)

    while check_date.isoformat() in all_gym_dates:
        streak += 1
        check_date -= timedelta(days=1)

    # Heatmap de los últimos 28 días (4 semanas)
    last_28_days = []
    for i in range(27, -1, -1):
        d = today - timedelta(days=i)
        d_str = d.isoformat()
        attended = d_str in all_gym_dates
        last_28_days.append({
            "date": d_str,
            "day_num": d.day,
            "weekday": ["L", "M", "M", "J", "V", "S", "D"][d.weekday()],
            "attended": attended,
            "is_today": d_str == today_str,
        })

    return {
        "total_attended_all_time": len(all_gym_dates),
        "attended_this_month": gym_this_month,
        "attended_this_week": gym_this_week,
        "weekly_goal": weekly_goal,
        "weekly_percent": min(100.0, weekly_percent),
        "streak_days": streak,
        "attended_today": attended_today,
        "last_28_days": last_28_days,
        "recent_completed_tasks": gym_task_matches[:5],
    }


def compute_weight_statistics(profile: dict[str, Any]) -> dict[str, Any]:
    """Calcula las métricas de evolución de peso, pérdida acumulada y meta."""
    weight_logs = profile.get("weight_logs", [])
    initial_w = float(profile.get("initial_weight") or 85.0)
    current_w = float(profile.get("current_weight") or initial_w)
    target_w = float(profile.get("target_weight") or 76.0)

    # Si hay registros de peso, actualizar current con el más reciente
    if weight_logs:
        sorted_logs = sorted(weight_logs, key=lambda x: x.get("date", ""))
        current_w = float(sorted_logs[-1].get("weight", current_w))

    total_to_lose = max(0.0, initial_w - target_w)
    lost_so_far = max(0.0, initial_w - current_w)
    remaining_kg = max(0.0, current_w - target_w)
    progress_percent = (
        round((lost_so_far / total_to_lose) * 100, 1) if total_to_lose > 0 else 100.0
    )

    # Estimación de semanas restantes a ritmo saludable de 0.6 kg/semana
    weeks_remaining = round(remaining_kg / 0.6, 1) if remaining_kg > 0 else 0

    return {
        "initial_weight": round(initial_w, 1),
        "current_weight": round(current_w, 1),
        "target_weight": round(target_w, 1),
        "lost_kg": round(lost_so_far, 1),
        "remaining_kg": round(remaining_kg, 1),
        "progress_percent": min(100.0, progress_percent),
        "weeks_remaining": weeks_remaining,
        "logs": sorted(weight_logs, key=lambda x: x.get("date", ""), reverse=True),
    }


def log_weight_entry(
    profile_id: str,
    weight: float,
    date_str: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Registra una nueva medición de peso en el historial del perfil."""
    data = get_health_data()
    profiles = data.setdefault("profiles", {})
    if profile_id not in profiles:
        profile_id = "fidel"

    profile = profiles[profile_id]
    entry_date = date_str or date.today().isoformat()

    new_log = {
        "date": entry_date,
        "weight": round(float(weight), 2),
        "notes": notes.strip(),
    }

    logs = profile.setdefault("weight_logs", [])
    # Reemplazar si ya existe un pesaje en la misma fecha
    existing_idx = next((i for i, l in enumerate(logs) if l.get("date") == entry_date), None)
    if existing_idx is not None:
        logs[existing_idx] = new_log
    else:
        logs.append(new_log)

    profile["current_weight"] = round(float(weight), 2)
    save_health_data(data)
    return new_log


def toggle_habit(profile_id: str, habit_type: str, date_str: str | None = None) -> bool:
    """Alterna el cumplimiento de un hábito (gym, walk, water) para una fecha específica."""
    data = get_health_data()
    profiles = data.setdefault("profiles", {})
    if profile_id not in profiles:
        profile_id = "fidel"

    profile = profiles[profile_id]
    habits = profile.setdefault("habits_history", {})
    habit_dates = habits.setdefault(habit_type, [])

    target_date = date_str or date.today().isoformat()

    if target_date in habit_dates:
        habit_dates.remove(target_date)
        is_completed = False
    else:
        habit_dates.append(target_date)
        is_completed = True

    save_health_data(data)
    return is_completed


def sync_program_with_recurrent_rules(profile_id: str) -> dict[str, Any]:
    """Crea o actualiza las tareas recurrentes en el motor de crones a partir del programa activo."""
    data = get_health_data()
    profile = data.get("profiles", {}).get(profile_id, {})
    program = profile.get("active_program")

    if not program:
        return {"status": "error", "message": "No hay programa activo para sincronizar."}

    days_per_week = program.get("workout_split", {}).get("days_per_week", 4)
    scope = profile_id if profile_id in ("fidel", "lau") else "fidel"

    # Regla 1: Ir al gimnasio (días laborables según meta)
    gym_days = [0, 1, 3, 4] if days_per_week == 4 else [0, 2, 4]

    recurrent_engine.add_rule(
        title="Ir al gym",
        description=f"Sesión de entrenamiento de fuerza según {program.get('title')}",
        scope=scope,
        priority="Alta",
        frequency="custom_days",
        days_of_week=gym_days,
        story_points=2.0,
    )

    # Regla 2: Caminata y Pasos diarios
    recurrent_engine.add_rule(
        title="Caminata diaria (1h / 10k pasos)",
        description="Acondicionamiento cardiovascular LISS y gasto calórico en Zona 2.",
        scope=scope,
        priority="Media",
        frequency="daily",
        days_of_week=[0, 1, 2, 3, 4, 5, 6],
        story_points=1.0,
    )

    # Regla 3: Pesaje dominical en ayunas
    recurrent_engine.add_rule(
        title="Registro de peso dominical",
        description="Pesaje semanal en ayunas para medir adherencia al programa de 12 semanas.",
        scope=scope,
        priority="Media",
        frequency="custom_days",
        days_of_week=[6],  # Domingo
        story_points=1.0,
    )

    return {
        "status": "ok",
        "message": "Se han configurado 3 tareas periódicas en el motor de crones vinculadas a tu programa.",
        "profile": profile_id,
    }


def generate_ai_health_program(
    profile_id: str,
    target_loss_kg: float = 8.0,
    weeks: int = 12,
    gym_days_available: int = 4,
    diet_preferences: str = "Balanceada con alta proteína",
) -> dict[str, Any]:
    """Genera un programa integral de 3 meses usando Inteligencia Artificial (Gemini 3.6 Flash)

    actuando bajo el rol de Nutriólogo Deportivo y Preparador Físico Certificado (CSCS).
    """
    data = get_health_data()
    profile = data.get("profiles", {}).get(profile_id, {})
    current_w = float(profile.get("current_weight") or 83.0)
    target_w = round(current_w - target_loss_kg, 1)

    system_prompt = (
        "Eres un Nutriólogo Deportivo Clínico y Preparador Físico de Alto Rendimiento (Certificado CSCS). "
        "Tu misión es diseñar un programa trimestral de 12 semanas (mini-proyecto de transformación física) "
        "con base científica, seguro, sostenible y sin efecto rebote. "
        "Debes estructurar el plan en 3 fases de 4 semanas cada una, calculando requerimiento calórico, macronutrientes "
        "y rutina de ejercicios con sobrecarga progresiva. Responde ÚNICAMENTE en formato JSON válido."
    )

    user_prompt = f"""
Diseña un programa trimestral para {profile.get('name', 'Usuario')} con las siguientes características:
- Género: {profile.get('gender', 'male')}
- Estatura: {profile.get('height_cm', 178)} cm
- Peso actual: {current_w} kg
- Objetivo: Perder {target_loss_kg} kg en {weeks} semanas (Peso meta: {target_w} kg).
- Días disponibles para gimnasio: {gym_days_available} días/semana.
- Preferencias nutricionales: {diet_preferences}.

Estructura requerida en JSON:
{{
  "title": "Programa Trimestral: ...",
  "target_loss_kg": {target_loss_kg},
  "duration_weeks": {weeks},
  "nutrition_plan": {{
    "daily_calories": 2100,
    "protein_g": 160,
    "carbs_g": 190,
    "fats_g": 60,
    "strategy": "Explicación del déficit y macronutrientes",
    "meal_guidelines": ["Pauta 1", "Pauta 2", "Pauta 3", "Pauta 4"]
  }},
  "workout_split": {{
    "type": "Distribución (ej. Torso/Pierna o Push/Pull/Legs)",
    "days_per_week": {gym_days_available},
    "days": [
      {{
        "day_name": "Lunes",
        "focus": "Músculos principales y objetivo",
        "exercises": ["Ejercicio 1 (series x reps)", "Ejercicio 2", "Ejercicio 3", "Ejercicio 4"]
      }}
    ]
  }},
  "phases": [
    {{
      "phase": 1,
      "name": "Fase 1: Adaptación Anatómica",
      "weeks": "Semanas 1-4",
      "goal": "Meta de la fase",
      "status": "in_progress"
    }},
    {{
      "phase": 2,
      "name": "Fase 2: Sobrecarga e Intensidad",
      "weeks": "Semanas 5-8",
      "goal": "Meta de la fase",
      "status": "upcoming"
    }},
    {{
      "phase": 3,
      "name": "Fase 3: Definición y Consolidación",
      "weeks": "Semanas 9-12",
      "goal": "Meta de la fase",
      "status": "upcoming"
    }}
  ]
}}
"""

    try:
        raw_text = effort_estimator._call_gemini_api(system_prompt, user_prompt)
        # Limpieza de bloques markdown
        clean_text = raw_text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        elif clean_text.startswith("```"):
            clean_text = clean_text[3:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]

        parsed = json.loads(clean_text.strip())
        parsed["id"] = f"prog-{profile_id}-{uuid.uuid4().hex[:6]}"
        parsed["start_date"] = date.today().isoformat()
        parsed["current_week"] = 1

        # Guardar como programa activo en el perfil
        profile["active_program"] = parsed
        profile["target_weight"] = target_w
        save_health_data(data)
        return parsed

    except Exception as exc:
        logger.error("Error al generar programa con IA: %s", exc)
        # Fallback estructurado garantizado
        fallback_prog = _get_initial_health_data()["profiles"]["fidel"]["active_program"]
        fallback_prog["title"] = f"Programa 12 Semanas: Transformación Personal (-{target_loss_kg}kg)"
        fallback_prog["target_loss_kg"] = target_loss_kg
        profile["active_program"] = fallback_prog
        save_health_data(data)
        return fallback_prog
