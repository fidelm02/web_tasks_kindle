"""Módulo de persistencia aislado: lectura/escritura segura y atómica del JSON."""
import json
import os
import tempfile
import uuid
from datetime import datetime
from filelock import FileLock

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "tasks_db.json")
LOCK_PATH = DB_PATH + ".lock"


def _ensure_db_exists() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if not os.path.exists(DB_PATH):
        with open(DB_PATH, "w", encoding="utf-8") as f:
            json.dump({"tasks": []}, f, ensure_ascii=False, indent=2)


def read_tasks() -> list:
    """Lectura desacoplada del archivo JSON (sin bloqueo, apta para consumo externo)."""
    _ensure_db_exists()
    with open(DB_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("tasks", [])


def get_pending_tasks() -> list:
    """Obtiene únicamente las tareas en estado pendiente."""
    return [t for t in read_tasks() if t.get("status") == "pending"]


def get_completed_tasks() -> list:
    """Obtiene todas las tareas completadas ordenadas por fecha de completado más reciente."""
    completed = [t for t in read_tasks() if t.get("status") == "completed"]
    return sorted(completed, key=lambda t: t.get("completed_at") or "", reverse=True)


def _write_tasks_atomic(tasks: list) -> None:
    """Escritura atómica: temporal + os.replace, protegida por FileLock."""
    _ensure_db_exists()
    directory = os.path.dirname(DB_PATH)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp_tasks_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            json.dump({"tasks": tasks}, tmp_file, ensure_ascii=False, indent=2)
        os.replace(tmp_path, DB_PATH)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def create_task(title: str, description: str, priority: str, target_date: str | None) -> dict:
    with FileLock(LOCK_PATH):
        tasks = read_tasks()
        new_task = {
            "id": str(uuid.uuid4()),
            "title": title,
            "description": description or "",
            "priority": priority,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "target_date": target_date or None,
            "completed_at": None,
        }
        tasks.append(new_task)
        _write_tasks_atomic(tasks)
        return new_task


def toggle_task(task_id: str) -> None:
    with FileLock(LOCK_PATH):
        tasks = read_tasks()
        for task in tasks:
            if task["id"] == task_id:
                if task["status"] == "pending":
                    task["status"] = "completed"
                    task["completed_at"] = datetime.now().isoformat()
                else:
                    task["status"] = "pending"
                    task["completed_at"] = None
                break
        _write_tasks_atomic(tasks)


def archive_task(task_id: str) -> None:
    with FileLock(LOCK_PATH):
        tasks = read_tasks()
        for task in tasks:
            if task["id"] == task_id:
                task["status"] = "archived"
                break
        _write_tasks_atomic(tasks)


def delete_task(task_id: str) -> None:
    with FileLock(LOCK_PATH):
        tasks = read_tasks()
        tasks = [t for t in tasks if t["id"] != task_id]
        _write_tasks_atomic(tasks)


def archive_completed() -> None:
    with FileLock(LOCK_PATH):
        tasks = read_tasks()
        for task in tasks:
            if task["status"] == "completed":
                task["status"] = "archived"
        _write_tasks_atomic(tasks)
