"""Servicio de Gestión del Vault de Conocimiento estilo Obsidian y Recordatorios.

Maneja:
1. Estructura de Vault para Fidel, Laura y Martha con MOCs (Índices) y Perfiles.
2. Ingesta de documentos con Frontmatter YAML estándar y [[wikilinks]].
3. Búsqueda contextual rápida y ligera para responder preguntas en el chat de WhatsApp.
4. Persistencia segura y atómica de Recordatorios (reminders.json y Recordatorios.md).
"""

from __future__ import annotations

from datetime import date, datetime
import json
import logging
import os
from pathlib import Path
import re
import tempfile
from typing import Any
import uuid

from filelock import FileLock
from app.constants import VAULT_DIR, MEMBERS_INFO

logger = logging.getLogger(__name__)

REMINDERS_LOCK_PATH = str(VAULT_DIR / "Recordatorios" / "reminders.lock")
REMINDERS_JSON_PATH = VAULT_DIR / "Recordatorios" / "reminders.json"


def _normalize_name(name: str) -> str:
    """Normaliza nombres o alias a las claves canónicas: 'Fidel', 'Laura', 'Martha', 'Compartido'."""
    lower = (name or "").strip().lower()
    if any(k in lower for k in ("lau", "lalis", "laura", "lalita")):
        return "Laura"
    if any(k in lower for k in ("martha", "marta", "elena", "86313")):
        return "Martha"
    if any(k in lower for k in ("fidel", "moreno", "yo")):
        return "Fidel"
    return "Compartido"


def init_vault() -> None:
    """Inicializa la estructura de directorios, perfiles e índices del Vault."""
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    reminders_dir = VAULT_DIR / "Recordatorios"
    reminders_dir.mkdir(parents=True, exist_ok=True)

    # Inicializar archivo de recordatorios JSON si no existe
    if not REMINDERS_JSON_PATH.exists():
        with open(REMINDERS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump({"reminders": []}, f, indent=2, ensure_ascii=False)

    # Carpetas por miembro
    members = {
        "Fidel": ["Notas", "Documentos", "Proyectos"],
        "Laura": ["Notas", "Documentos", "Pacientes"],
        "Martha": ["Notas", "Documentos", "Tramites"],
        "Compartido": ["General", "Diario", "Compras"],
    }

    for member, subfolders in members.items():
        member_dir = VAULT_DIR / member
        member_dir.mkdir(parents=True, exist_ok=True)
        for sub in subfolders:
            (member_dir / sub).mkdir(parents=True, exist_ok=True)

        # Crear Perfil.md si no existe
        perfil_path = member_dir / "Perfil.md"
        if not perfil_path.exists():
            _create_default_profile(member, perfil_path)

        # Crear _Indice.md si no existe
        indice_path = member_dir / "_Indice.md"
        if not indice_path.exists():
            _create_default_index(member, indice_path, subfolders)

        # Crear Recordatorios.md si no existe
        if member != "Compartido":
            rec_path = member_dir / "Recordatorios.md"
            if not rec_path.exists():
                with open(rec_path, "w", encoding="utf-8") as f:
                    f.write(
                        f"# Recordatorios y Pendientes de {member}\n\n"
                        f"> Actualizado automáticamente por el Asistente Chismoso y revisado diariamente a las 6:00 AM.\n\n"
                        f"## Próximos Compromisos\n\n"
                    )


def _create_default_profile(member: str, path: Path) -> None:
    """Crea la ficha o perfil base para un miembro."""
    today_str = date.today().isoformat()
    canonical_key = "fidel" if member == "Fidel" else ("lau" if member == "Laura" else "martha")
    info = MEMBERS_INFO.get(canonical_key, {})
    email = info.get("email", "")
    role = info.get("role", "")

    content = f"""---
titulo: "Ficha de Perfil - {member}"
autor: "{member}"
fecha: {today_str}
tags: [perfil, contacto, familia]
---

# Perfil: {member}

- **Nombre Completo:** {info.get("name", member)}
- **Correo Principal:** `{email}`
- **Rol / Relación:** {role}
- **Última Actualización:** {today_str}

## Notas y Preferencias
- Canal principal de comunicación: WhatsApp (Grupo Chismoso).
- Alertas de calendario sincronizadas hacia su cuenta oficial.
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _create_default_index(member: str, path: Path, subfolders: list[str]) -> None:
    """Crea el Map of Content (_Indice.md) de un miembro."""
    today_str = date.today().isoformat()
    sub_links = "\n".join([f"- [[{member}/{sub}/_Indice_{sub}|Carpeta: {sub}]]" for sub in subfolders])
    content = f"""---
titulo: "Índice General - {member}"
autor: "{member}"
fecha: {today_str}
tags: [moc, indice]
---

# Map of Content (MOC): {member}

> Vault Personal integrado con el Asistente Chismoso y Kindle Tasks Pro.

## Secciones Principales
- [[{member}/Perfil|Ficha de Perfil y Datos Personales]]
- [[{member}/Recordatorios|Recordatorios Activos]]
{sub_links}

## Documentos Recientes
*(Se actualiza automáticamente al ingresar nuevas notas o documentos)*
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def save_vault_document(
    author: str,
    category: str,
    title: str,
    markdown_content: str,
    tags: list[str] | None = None,
    related_links: list[str] | None = None,
) -> Path:
    """Guarda un documento con formato Obsidian en el Vault y actualiza el índice del autor.

    Args:
        author: Nombre del autor o destinatario (Fidel, Laura, Martha, Compartido).
        category: Subcarpeta temática (Notas, Documentos, Pacientes, Tramites, General).
        title: Título legible del documento.
        markdown_content: Contenido formateado en Markdown.
        tags: Lista de etiquetas (ej. ["salud", "pacientes"]).
        related_links: Enlaces [[wikilinks]] a notas relacionadas.

    Returns:
        Path: Ruta absoluta del archivo creado.
    """
    init_vault()
    canon_author = _normalize_name(author)
    clean_cat = "".join(c for c in category if c.isalnum() or c in ("_", "-")).strip("_-") or "Documentos"

    dest_dir = VAULT_DIR / canon_author / clean_cat
    dest_dir.mkdir(parents=True, exist_ok=True)

    slug = re.sub(r"[^a-zA-Z0-9_-]", "_", title.lower()).strip("_")[:45] or "nota"
    today_str = date.today().isoformat()
    filename = f"{today_str}_{slug}.md"
    file_path = dest_dir / filename

    tag_list = tags or ["chismoso"]
    rel_list = related_links or [f"[[{canon_author}/_Indice]]"]

    # Construir Frontmatter YAML
    tags_formatted = "[" + ", ".join(f'"{t.strip()}"' for t in tag_list) + "]"
    rel_formatted = "[" + ", ".join(f'"{r.strip()}"' for r in rel_list) + "]"

    frontmatter = f"""---
titulo: "{title}"
autor: "{canon_author}"
fecha: {today_str}
categoria: "{clean_cat}"
tags: {tags_formatted}
relacionados: {rel_formatted}
tipo: "documento"
---

"""
    full_text = frontmatter + markdown_content.strip() + "\n"

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(full_text)

    # Actualizar _Indice.md del autor
    try:
        indice_path = VAULT_DIR / canon_author / "_Indice.md"
        if indice_path.exists():
            rel_link = f"- [[{canon_author}/{clean_cat}/{filename[:-3]}|{title}]] ({today_str})\n"
            with open(indice_path, "a", encoding="utf-8") as f:
                f.write(rel_link)
    except Exception as exc:
        logger.warning("No se pudo actualizar _Indice.md: %s", exc)

    logger.info("Documento guardado en Vault: %s", file_path)
    return file_path


def search_vault(
    query: str,
    author: str | None = None,
    max_results: int = 4,
) -> list[dict[str, Any]]:
    """Realiza una búsqueda rápida de texto y tags dentro de los documentos del Vault.

    Args:
        query: Consulta o términos clave a buscar.
        author: Filtro opcional por miembro (Fidel, Laura, Martha).
        max_results: Cantidad máxima de notas a retornar.

    Returns:
        list[dict]: Lista de resultados con título, autor, ruta relativa y fragmento contextual.
    """
    init_vault()
    terms = [t.lower() for t in re.findall(r"\w+", query) if len(t) > 2]
    if not terms:
        return []

    results: list[dict[str, Any]] = []
    canon_author = _normalize_name(author) if author else None

    # Directorios a buscar
    search_dirs = [VAULT_DIR / canon_author] if canon_author and (VAULT_DIR / canon_author).is_dir() else [VAULT_DIR]

    for search_dir in search_dirs:
        for md_file in search_dir.rglob("*.md"):
            # Omitir archivos temporales o de bloqueo
            if md_file.name.startswith("."):
                continue
            try:
                content = md_file.read_text(encoding="utf-8", errors="replace")
                content_lower = content.lower()
                matches = sum(content_lower.count(t) for t in terms)
                if matches > 0:
                    # Extraer título del Frontmatter o primera línea #
                    title_match = re.search(r'titulo:\s*"([^"]+)"', content) or re.search(r"^#\s+(.+)$", content, re.M)
                    doc_title = title_match.group(1) if title_match else md_file.stem

                    # Extraer autor del path o frontmatter
                    rel_parts = md_file.relative_to(VAULT_DIR).parts
                    doc_author = rel_parts[0] if len(rel_parts) > 1 else "General"

                    # Extraer extracto contextual con coincidencia
                    first_idx = min((content_lower.find(t) for t in terms if t in content_lower), default=0)
                    start = max(0, first_idx - 60)
                    end = min(len(content), first_idx + 240)
                    snippet = content[start:end].replace("\n", " ").strip()

                    results.append({
                        "score": matches,
                        "title": doc_title,
                        "author": doc_author,
                        "path": str(md_file),
                        "rel_path": str(md_file.relative_to(VAULT_DIR)),
                        "snippet": f"...{snippet}...",
                    })
            except Exception as e:
                continue

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:max_results]


def add_reminder(
    requester: str,
    target: str,
    reminder_date: str,
    text: str,
    time_str: str | None = None,
) -> dict[str, Any]:
    """Registra un recordatorio en reminders.json y en Recordatorios.md del destinatario.

    Args:
        requester: Quién solicitó el recordatorio (Fidel, Laura, Martha).
        target: Para quién es el recordatorio (Fidel, Laura, Martha).
        reminder_date: Fecha objetivo en formato YYYY-MM-DD.
        text: Descripción del compromiso o recordatorio.
        time_str: Hora opcional (ej. "15:00") si se indicó.

    Returns:
        dict: Objeto del recordatorio creado.
    """
    init_vault()
    canon_target = _normalize_name(target)
    canon_requester = _normalize_name(requester)
    reminder_id = str(uuid.uuid4())[:8]
    created_at = datetime.now().isoformat()

    reminder_entry = {
        "id": reminder_id,
        "created_at": created_at,
        "requester": canon_requester,
        "target": canon_target,
        "reminder_date": reminder_date,
        "time": time_str,
        "text": text,
        "notified_day_before": False,
        "notified_day_of": False,
        "status": "pending",
    }

    # Escritura segura con FileLock en reminders.json
    with FileLock(REMINDERS_LOCK_PATH):
        data = {"reminders": []}
        if REMINDERS_JSON_PATH.exists():
            try:
                with open(REMINDERS_JSON_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {"reminders": []}

        data.setdefault("reminders", []).append(reminder_entry)

        # Escritura atómica
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(REMINDERS_JSON_PATH.parent), prefix=".tmp_rem_", suffix=".json")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp_f:
                json.dump(data, tmp_f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, REMINDERS_JSON_PATH)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    # Actualizar nota Markdown en el Vault de la persona
    try:
        rec_md_path = VAULT_DIR / canon_target / "Recordatorios.md"
        hour_tag = f" a las {time_str}" if time_str else ""
        req_notice = f" *(Pedido por {canon_requester})*" if canon_requester != canon_target else ""
        entry_md = f"- [ ] **{reminder_date}**{hour_tag}: {text}{req_notice} `[ID: {reminder_id}]`\n"

        with open(rec_md_path, "a", encoding="utf-8") as f:
            f.write(entry_md)
    except Exception as exc:
        logger.warning("No se pudo actualizar Recordatorios.md para %s: %s", canon_target, exc)

    logger.info("Recordatorio registrado [%s] para %s: %s", reminder_id, canon_target, text)
    return reminder_entry


def get_all_reminders() -> list[dict[str, Any]]:
    """Lee y retorna la lista completa de recordatorios."""
    init_vault()
    if not REMINDERS_JSON_PATH.exists():
        return []
    try:
        with open(REMINDERS_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("reminders", [])
    except Exception:
        return []


def mark_reminder_notified(
    reminder_id: str,
    notified_day_before: bool = False,
    notified_day_of: bool = False,
) -> None:
    """Marca un recordatorio como notificado el día antes o el mismo día."""
    init_vault()
    with FileLock(REMINDERS_LOCK_PATH):
        if not REMINDERS_JSON_PATH.exists():
            return
        try:
            with open(REMINDERS_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        reminders = data.get("reminders", [])
        for rem in reminders:
            if rem.get("id") == reminder_id:
                if notified_day_before:
                    rem["notified_day_before"] = True
                if notified_day_of:
                    rem["notified_day_of"] = True
                    rem["status"] = "completed"
                break

        # Escritura atómica
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(REMINDERS_JSON_PATH.parent), prefix=".tmp_rem_", suffix=".json")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp_f:
                json.dump(data, tmp_f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, REMINDERS_JSON_PATH)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise
