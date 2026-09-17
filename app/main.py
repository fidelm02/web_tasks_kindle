"""Kindle Tasks & Home Portal - Punto de Entrada de la Aplicación.

Objetivo:
    Ensamblar la aplicación FastAPI en capas, montando los recursos estáticos
    y registrando los enrutadores modulares (home, reportes, clickup,
    tareas y lector de documentos).

Autor:
    Fidel Moreno Miranda <fidelm02@gmail.com>
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.templates import templates
from app.routers import (
    ai_router,
    clickup_router,
    home_router,
    reader_router,
    reports_router,
    tasks_router,
)

# Inicialización de la aplicación FastAPI
app = FastAPI(title="Kindle Tasks & Home Portal")

# Montaje de archivos estáticos (CSS, iconos, assets)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Registro ordenado de enrutadores (estáticos antes que dinámicos)
app.include_router(home_router)
app.include_router(ai_router)
app.include_router(reports_router)
app.include_router(clickup_router)
app.include_router(tasks_router)
app.include_router(reader_router)

# Exportar templates para compatibilidad interna
__all__ = ["app", "templates"]
