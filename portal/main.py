"""Punto de entrada de la aplicación FastAPI para el Portal Pro (iPad/Laptop/Móvil).

Puerto por defecto: 8090.
Incluye tablero Kanban estilo Jira, gestión de tareas recurrentes (crones)
y estimador de esfuerzo con Inteligencia Artificial (Gemini).
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from portal.routers import estimator, health, kanban, recurrent
from portal.services import recurrent_engine

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("portal")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


async def _cron_scheduler_loop():
    """Bucle en segundo plano que evalúa tareas recurrentes periódicamente."""
    logger.info("Iniciando bucle de scheduler de tareas recurrentes...")
    while True:
        try:
            # Ejecutar evaluación y deduplicación
            res = recurrent_engine.evaluate_and_generate()
            if res.get("generated_count", 0) > 0:
                logger.info(
                    "Scheduler de crones: %d tareas generadas, %d omitidas",
                    res["generated_count"],
                    res["skipped_count"],
                )
        except Exception as exc:
            logger.error("Error en ciclo del scheduler de crones: %s", exc)

        # Esperar 30 minutos entre comprobaciones
        await asyncio.sleep(1800)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida de la aplicación: inicialización y apagado ordenado."""
    logger.info("Iniciando Kindle Tasks Pro Portal en puerto 8090...")

    # Ejecutar primera pasada de tareas recurrentes al arrancar
    try:
        initial_res = recurrent_engine.evaluate_and_generate()
        logger.info(
            "Arranque inicial: %d tareas generadas, %d omitidas",
            initial_res.get("generated_count", 0),
            initial_res.get("skipped_count", 0),
        )
    except Exception as init_exc:
        logger.error("Error al evaluar crones en el arranque: %s", init_exc)

    # Iniciar tarea en segundo plano
    cron_task = asyncio.create_task(_cron_scheduler_loop())

    yield

    # Apagado
    cron_task.cancel()
    try:
        await cron_task
    except asyncio.CancelledError:
        pass
    logger.info("Kindle Tasks Pro Portal detenido.")


app = FastAPI(
    title="Kindle Tasks Pro Portal",
    description="Portal avanzado de gestión de proyectos, crones y estimación de esfuerzo",
    version="2.0.0",
    lifespan=lifespan,
)

# Servir archivos estáticos
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Registrar routers
app.include_router(kanban.router)
app.include_router(recurrent.router)
app.include_router(estimator.router)
app.include_router(health.router)


@app.get("/api/system/health")
async def health_check():
    """Endpoint de salud del portal."""
    return {"status": "healthy", "service": "Kindle Tasks Pro Portal", "port": 8090}
