"""Módulo de persistencia aislado: lectura y escritura de tareas."""
import json
import os
from pathlib import Path
import tempfile
import uuid
from datetime import datetime
from filelock import FileLock

_BASE_DIR = Path(__file__).resolve().parent.parent


def _clean_scope(scope: str) -> str:
    """Normalize scope identifier to safe alphanumeric string.

    Args:
        scope: Raw scope identifier string.

    Returns:
        str: Normalized safe scope string.
    """
    cleaned = "".join(
        c for c in (scope or "").lower() if c.isalnum() or c in ("_", "-")
    ).strip("_-")
    return cleaned or "casa"


def _get_paths(scope: str = "casa") -> tuple[str, str]:
    """Return database file path and lock path for given scope.

    Args:
        scope: Task scope (e.g. 'casa', 'lau', 'fidel', or custom slug).

    Returns:
        tuple[str, str]: DB path and lock file path.
    """
    clean = _clean_scope(scope)
    if clean in ("casa", "tasks_db", "default"):
        db_path = str(_BASE_DIR / "data" / "tasks_db.json")
    elif clean in ("lau", "tasks_lau"):
        db_path = str(_BASE_DIR / "data" / "tasks_lau_db.json")
    else:
        db_path = str(_BASE_DIR / "data" / f"tasks_{clean}_db.json")
    return db_path, db_path + ".lock"


def _ensure_db_exists(scope: str = "casa") -> None:
    """Ensure task JSON database file exists for scope."""
    db_path, _ = _get_paths(scope)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if not os.path.exists(db_path):
        with open(db_path, "w", encoding="utf-8") as f:
            json.dump({"tasks": []}, f, ensure_ascii=False, indent=2)


def read_tasks(scope: str = "casa") -> list:
    """Lectura desacoplada del archivo JSON de tareas."""
    db_path, _ = _get_paths(scope)
    _ensure_db_exists(scope)
    with open(db_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("tasks", [])


def get_pending_tasks(scope: str = "casa") -> list:
    """Obtiene únicamente las tareas en estado pendiente."""
    return [t for t in read_tasks(scope) if t.get("status") == "pending"]


def get_completed_tasks(scope: str = "casa") -> list:
    """Obtiene todas las tareas completadas por fecha reciente."""
    completed = [
        t for t in read_tasks(scope) if t.get("status") == "completed"
    ]
    return sorted(
        completed,
        key=lambda t: t.get("completed_at") or "",
        reverse=True,
    )


def _write_tasks_atomic(tasks: list, scope: str = "casa") -> None:
    """Escritura atómica protegida por FileLock."""
    db_path, _ = _get_paths(scope)
    _ensure_db_exists(scope)
    directory = os.path.dirname(db_path)
    fd, tmp_path = tempfile.mkstemp(
        dir=directory, prefix=f".tmp_tasks_{scope}_", suffix=".json"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            json.dump({"tasks": tasks}, tmp_file, ensure_ascii=False, indent=2)
        os.replace(tmp_path, db_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def create_task(
    title: str,
    description: str,
    priority: str,
    target_date: str | None,
    scope: str = "casa",
) -> dict:
    """Crea y persiste una nueva tarea."""
    db_path, lock_path = _get_paths(scope)
    with FileLock(lock_path):
        tasks = read_tasks(scope)
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
        _write_tasks_atomic(tasks, scope)
        return new_task


def toggle_task(task_id: str, scope: str = "casa") -> None:
    """Alterna el estado pendiente / completado de una tarea."""
    db_path, lock_path = _get_paths(scope)
    with FileLock(lock_path):
        tasks = read_tasks(scope)
        for task in tasks:
            if task["id"] == task_id:
                if task["status"] == "pending":
                    task["status"] = "completed"
                    task["completed_at"] = datetime.now().isoformat()
                else:
                    task["status"] = "pending"
                    task["completed_at"] = None
                break
        _write_tasks_atomic(tasks, scope)


def archive_task(task_id: str, scope: str = "casa") -> None:
    """Marca una tarea como archivada."""
    db_path, lock_path = _get_paths(scope)
    with FileLock(lock_path):
        tasks = read_tasks(scope)
        for task in tasks:
            if task["id"] == task_id:
                task["status"] = "archived"
                break
        _write_tasks_atomic(tasks, scope)


def delete_task(task_id: str, scope: str = "casa") -> None:
    """Elimina permanentemente una tarea."""
    db_path, lock_path = _get_paths(scope)
    with FileLock(lock_path):
        tasks = read_tasks(scope)
        tasks = [t for t in tasks if t["id"] != task_id]
        _write_tasks_atomic(tasks, scope)


def archive_completed(scope: str = "casa") -> None:
    """Archiva todas las tareas que se encuentren completadas."""
    db_path, lock_path = _get_paths(scope)
    with FileLock(lock_path):
        tasks = read_tasks(scope)
        for task in tasks:
            if task["status"] == "completed":
                task["status"] = "archived"
        _write_tasks_atomic(tasks, scope)


def update_task(
    task_id: str,
    title: str,
    description: str,
    priority: str,
    target_date: str | None,
    scope: str = "casa",
) -> bool:
    """Update title, description, priority, and date of a task.

    Args:
        task_id: Unique UUID string of the task.
        title: Updated title string.
        description: Updated description or notes.
        priority: Updated priority string (Alta, Media, Baja).
        target_date: Updated due date string or None.
        scope: Task scope (e.g. 'casa', 'lau', 'fidel', or slug).

    Returns:
        bool: True if task was found and updated, False otherwise.
    """
    db_path, lock_path = _get_paths(scope)
    with FileLock(lock_path):
        tasks = read_tasks(scope)
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
            _write_tasks_atomic(tasks, scope)
        return found

