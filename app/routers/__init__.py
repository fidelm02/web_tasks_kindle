"""Capa de enrutamiento y controladores HTTP (FastAPI APIRouter)."""

from app.routers.clickup import router as clickup_router
from app.routers.home import router as home_router
from app.routers.reader import router as reader_router
from app.routers.reports import router as reports_router
from app.routers.tasks import router as tasks_router

__all__ = [
    "clickup_router",
    "home_router",
    "reader_router",
    "reports_router",
    "tasks_router",
]
