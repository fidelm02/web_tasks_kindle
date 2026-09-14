"""Servicio de generación de reportes PDF para proyectos y lecturas."""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _safe(text: str | None) -> str:
    """Escape text safely for ReportLab XML paragraph parsing.

    Args:
        text: Raw text string or None.

    Returns:
        str: Escaped XML-safe string.
    """
    if not text:
        return ""
    return escape(str(text).strip())


def generate_tasks_pdf(
    project_name: str,
    tasks: list[dict[str, Any]],
) -> bytes:
    """Generate a clean PDF report of tasks sorted by status and title.

    Tasks are organized by status ('pending', 'completed', 'archived')
    and sorted alphabetically by title within each group.

    Args:
        project_name: Name of the project or section.
        tasks: Raw list of task dictionaries.

    Returns:
        bytes: Generated PDF binary content.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=40,
        rightMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.black,
        spaceAfter=4,
    )
    meta_style = ParagraphStyle(
        "DocMeta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#444444"),
        spaceAfter=12,
    )
    section_heading = ParagraphStyle(
        "SecHead",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=17,
        textColor=colors.black,
        spaceBefore=12,
        spaceAfter=6,
    )
    task_title_style = ParagraphStyle(
        "TaskTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        textColor=colors.black,
    )
    task_desc_style = ParagraphStyle(
        "TaskDesc",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#333333"),
    )
    badge_style = ParagraphStyle(
        "TaskBadge",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        alignment=2,
        textColor=colors.HexColor("#222222"),
    )

    story: list[Any] = []

    # Encabezado
    story.append(
        Paragraph(f"Reporte de Tareas: {_safe(project_name)}", title_style)
    )
    now_str = datetime.now().strftime("%d/%m/%Y, %H:%M")
    story.append(
        Paragraph(
            f"Generado el {now_str} • Total: {len(tasks)} tarea(s)",
            meta_style,
        )
    )
    story.append(
        HRFlowable(
            width="100%",
            thickness=1.5,
            color=colors.black,
            spaceAfter=14,
        )
    )

    # Agrupamiento por status
    groups: dict[str, list[dict[str, Any]]] = {
        "pending": [],
        "completed": [],
        "archived": [],
    }

    for t in tasks:
        st = (t.get("status") or "pending").lower()
        if st in groups:
            groups[st].append(t)
        else:
            groups["pending"].append(t)

    status_labels: dict[str, str] = {
        "pending": "Tareas Pendientes",
        "completed": "Tareas Completadas",
        "archived": "Tareas Archivadas",
    }

    if not tasks:
        empty_msg = Paragraph(
            "No hay tareas registradas en este proyecto.", meta_style
        )
        story.append(empty_msg)

    for st_key in ("pending", "completed", "archived"):
        group_tasks = groups[st_key]
        if not group_tasks:
            continue

        # Ordenar alfabéticamente por título dentro del status
        group_tasks.sort(
            key=lambda t: (t.get("title") or "").strip().lower()
        )

        label = status_labels[st_key]
        count_lbl = f"{label} ({len(group_tasks)})"
        story.append(Paragraph(count_lbl, section_heading))

        table_data: list[list[Any]] = []
        for task in group_tasks:
            title_text = _safe(task.get("title") or "Sin título")
            desc_text = _safe(task.get("description") or "")
            prio = _safe(task.get("priority") or "Media")
            date_val = _safe(task.get("target_date") or "")

            meta_parts: list[str] = [f"Prioridad: {prio}"]
            if date_val:
                meta_parts.append(f"Fecha meta: {date_val}")
            if st_key == "completed" and task.get("completed_at"):
                comp_dt = str(task.get("completed_at"))[:10]
                meta_parts.append(f"Completada: {comp_dt}")

            meta_line = " | ".join(meta_parts)

            content_cell = [
                Paragraph(f"• {title_text}", task_title_style),
            ]
            if desc_text:
                content_cell.append(Spacer(1, 2))
                content_cell.append(Paragraph(desc_text, task_desc_style))
            content_cell.append(Spacer(1, 2))
            content_cell.append(
                Paragraph(
                    f"<font size='8' color='#666666'>{meta_line}</font>",
                    task_desc_style,
                )
            )

            status_cell = Paragraph(
                f"[{prio.upper()}]",
                badge_style,
            )

            table_data.append([content_cell, status_cell])

        table = Table(table_data, colWidths=[450, 80])
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    (
                        "LINEBELOW",
                        (0, 0),
                        (-1, -1),
                        0.5,
                        colors.HexColor("#DDDDDD"),
                    ),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 10))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def generate_documents_pdf(
    project_name: str,
    categories: dict[str, list[dict[str, Any]]],
) -> bytes:
    """Generate a clean PDF report of the documents library catalog.

    Args:
        project_name: Name of the project or section.
        categories: Mapping of category names to document lists.

    Returns:
        bytes: Generated PDF binary content.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=40,
        rightMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.black,
        spaceAfter=4,
    )
    meta_style = ParagraphStyle(
        "DocMeta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#444444"),
        spaceAfter=12,
    )
    category_heading = ParagraphStyle(
        "CatHead",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=17,
        textColor=colors.black,
        spaceBefore=12,
        spaceAfter=6,
    )
    doc_title_style = ParagraphStyle(
        "DocItemTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        textColor=colors.black,
    )
    doc_desc_style = ParagraphStyle(
        "DocItemDesc",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#333333"),
    )
    meta_tag_style = ParagraphStyle(
        "DocTag",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        alignment=2,
        textColor=colors.HexColor("#555555"),
    )

    story: list[Any] = []

    story.append(
        Paragraph(
            f"Biblioteca de Documentos: {_safe(project_name)}",
            title_style,
        )
    )
    total_docs = sum(len(docs) for docs in categories.values())
    now_str = datetime.now().strftime("%d/%m/%Y, %H:%M")
    story.append(
        Paragraph(
            f"Generado el {now_str} • Total: {total_docs} archivo(s)",
            meta_style,
        )
    )
    story.append(
        HRFlowable(
            width="100%",
            thickness=1.5,
            color=colors.black,
            spaceAfter=14,
        )
    )

    if not categories or total_docs == 0:
        story.append(
            Paragraph(
                "No hay documentos ni lecturas en este proyecto.",
                meta_style,
            )
        )

    for cat_name, docs in sorted(categories.items()):
        if not docs:
            continue

        story.append(
            Paragraph(
                f"Carpeta: {_safe(cat_name)} ({len(docs)})",
                category_heading,
            )
        )

        table_data: list[list[Any]] = []
        for d in docs:
            d_title = _safe(d.get("title") or d.get("name") or "Documento")
            d_file = _safe(d.get("name") or "")
            d_ext = _safe(d.get("ext") or "")
            d_desc = _safe(d.get("description") or "")
            d_size = d.get("size_kb", 0)
            d_date = _safe(d.get("date") or "")

            content_cell = [
                Paragraph(f"• {d_title}", doc_title_style),
            ]
            if d_desc:
                content_cell.append(Spacer(1, 2))
                content_cell.append(Paragraph(d_desc, doc_desc_style))

            content_cell.append(Spacer(1, 2))
            info_line = (
                f"<font size='8' color='#666666'>"
                f"Archivo: {d_file} | Formato: {d_ext} | "
                f"Tamaño: {d_size} KB | Fecha: {d_date}"
                f"</font>"
            )
            content_cell.append(Paragraph(info_line, doc_desc_style))

            ext_badge = Paragraph(f"[{d_ext}]", meta_tag_style)
            table_data.append([content_cell, ext_badge])

        table = Table(table_data, colWidths=[450, 80])
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    (
                        "LINEBELOW",
                        (0, 0),
                        (-1, -1),
                        0.5,
                        colors.HexColor("#DDDDDD"),
                    ),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 10))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
