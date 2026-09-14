"""Servidor FastAPI SSR para gestión de tareas, optimizado para Kindle Scribe."""
from datetime import date, datetime
from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from app import storage

app = FastAPI(title="Kindle Tasks")
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

PRIORITY_ORDER = {"Alta": 0, "Media": 1, "Baja": 2}


def format_datetime_filter(val: str | None) -> str:
    """Formatea timestamps ISO para visualización clara en E-Ink."""
    if not val:
        return ""
    try:
        dt = datetime.fromisoformat(val)
        today = date.today()
        if dt.date() == today:
            return f"Hoy, {dt.strftime('%H:%M')}"
        return dt.strftime("%d/%m/%Y, %H:%M")
    except Exception:
        return str(val)[:16].replace("T", " ")


def format_target_date_filter(val: str | None) -> str:
    """Formatea la fecha de vencimiento con etiquetas relativas amigables."""
    if not val:
        return ""
    try:
        d = date.fromisoformat(val)
        today = date.today()
        diff = (d - today).days
        if diff == 0:
            return "Hoy"
        elif diff == 1:
            return "Mañana"
        elif diff < 0:
            return f"Venció el {d.strftime('%d/%m/%Y')}"
        return d.strftime("%d/%m/%Y")
    except Exception:
        return str(val)


templates.env.filters["format_datetime"] = format_datetime_filter
templates.env.filters["format_target_date"] = format_target_date_filter


def _sort_pending(tasks: list) -> list:
    return sorted(
        tasks,
        key=lambda t: (PRIORITY_ORDER.get(t["priority"], 3), t.get("target_date") or "9999-99-99"),
    )


def _safe_redirect(target: str | None, default: str = "/") -> str:
    allowed = {"/", "/completed"}
    if target and target in allowed:
        return target
    return default


@app.get("/")
def dashboard(request: Request):
    pending = _sort_pending(storage.get_pending_tasks())
    completed = storage.get_completed_tasks()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "pending_tasks": pending,
            "pending_count": len(pending),
            "completed_count": len(completed),
            "active_tab": "pending",
        },
    )


@app.get("/completed")
def completed_dashboard(request: Request):
    pending = storage.get_pending_tasks()
    completed = storage.get_completed_tasks()
    return templates.TemplateResponse(
        request,
        "completed.html",
        {
            "completed_tasks": completed,
            "pending_count": len(pending),
            "completed_count": len(completed),
            "active_tab": "completed",
        },
    )


@app.post("/tasks/create")
def create_task(
    title: str = Form(...),
    description: str = Form(""),
    priority: str = Form("Media"),
    target_date: str = Form(""),
    redirect_to: str = Form("/"),
):
    storage.create_task(title, description, priority, target_date or None)
    return RedirectResponse(_safe_redirect(redirect_to, "/"), status_code=303)


@app.post("/tasks/{task_id}/toggle")
def toggle_task(task_id: str, redirect_to: str = Form("/")):
    storage.toggle_task(task_id)
    return RedirectResponse(_safe_redirect(redirect_to, "/"), status_code=303)


@app.post("/tasks/{task_id}/delete")
def delete_task(task_id: str, redirect_to: str = Form("/")):
    storage.delete_task(task_id)
    return RedirectResponse(_safe_redirect(redirect_to, "/"), status_code=303)


@app.post("/tasks/{task_id}/archive")
def archive_task(task_id: str, redirect_to: str = Form("/")):
    storage.archive_task(task_id)
    return RedirectResponse(_safe_redirect(redirect_to, "/"), status_code=303)


@app.post("/tasks/archive-completed")
def archive_completed():
    storage.archive_completed()
    return RedirectResponse("/completed", status_code=303)


@app.get("/api/tasks")
def api_tasks():
    return JSONResponse(content={"tasks": storage.read_tasks()})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=False)

