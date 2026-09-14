"""Módulo de persistencia aislado: lectura y escritura de tareas."""
import json
import os
from pathlib import Path
import tempfile
import uuid
from datetime import datetime
from filelock import FileLock

_BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = str(_BASE_DIR / "data" / "tasks_db.json")
LOCK_PATH = DB_PATH + ".lock"


def _ensure_db_exists() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if not os.path.exists(DB_PATH):
        with open(DB_PATH, "w", encoding="utf-8") as f:
            json.dump({"tasks": []}, f, ensure_ascii=False, indent=2)


def read_tasks() -> list:
    """Lectura desacoplada del archivo JSON de tareas."""
    _ensure_db_exists()
    with open(DB_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("tasks", [])


def get_pending_tasks() -> list:
    """Obtiene únicamente las tareas en estado pendiente."""
    return [t for t in read_tasks() if t.get("status") == "pending"]


def get_completed_tasks() -> list:
    """Obtiene todas las tareas completadas por fecha reciente."""
    completed = [t for t in read_tasks() if t.get("status") == "completed"]
    return sorted(
        completed,
        key=lambda t: t.get("completed_at") or "",
        reverse=True,
    )


def _write_tasks_atomic(tasks: list) -> None:
    """Escritura atómica protegida por FileLock."""
    _ensure_db_exists()
    directory = os.path.dirname(DB_PATH)
    fd, tmp_path = tempfile.mkstemp(
        dir=directory, prefix=".tmp_tasks_", suffix=".json"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            json.dump({"tasks": tasks}, tmp_file, ensure_ascii=False, indent=2)
        os.replace(tmp_path, DB_PATH)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def create_task(
    title: str,
    description: str,
    priority: str,
    target_date: str | None,
) -> dict:
    """Crea y persiste una nueva tarea."""
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


def update_task(
    task_id: str,
    title: str,
    description: str,
    priority: str,
    target_date: str | None,
) -> bool:
    """Update title, description, priority, and date of a task.

    Args:
        task_id: Unique UUID string of the task.
        title: Updated title string.
        description: Updated description or notes.
        priority: Updated priority string (Alta, Media, Baja).
        target_date: Updated due date string or None.

    Returns:
        bool: True if task was found and updated, False otherwise.
    """
    with FileLock(LOCK_PATH):
        tasks = read_tasks()
        found = False
        for task in tasks:
            if task["id"] == task_id:
                task["title"] = title.strip()
                task["description"] = (description or "").strip()
                task["priority"] = priority
                task["target_date"] = target_date or None
                found = True
                break
        if found:
            _write_tasks_atomic(tasks)
        return found

