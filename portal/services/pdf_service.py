"""Servicio de Generación de Documentos PDF y TXT.

Convierte notas y contenidos Markdown de la Base de Conocimiento (Vault Obsidian)
en documentos profesionales con formato PDF (usando ReportLab) o TXT plano,
listos para ser despachados como archivos adjuntos en el chat de WhatsApp.
"""

from __future__ import annotations

from datetime import date, datetime
import html
import logging
from pathlib import Path
import re
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)


class NumberedCanvas(canvas.Canvas):
    """Canvas de dos pasos para numerar páginas dinámicamente ('Página X de Y')."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count: int) -> None:
        self.saveState()
        page_w, page_h = letter

        # Línea separadora inferior
        self.setStrokeColor(colors.HexColor("#CBD5E0"))
        self.setLineWidth(0.6)
        self.line(40, 38, page_w - 40, 38)

        # Texto del pie de página
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#718096"))
        self.drawString(40, 24, "Vault Obsidian • Asistente Inteligente Chismoso")
        page_str = f"Página {self._pageNumber} de {page_count}"
        self.drawRightString(page_w - 40, 24, page_str)

        self.restoreState()


def _clean_markdown_text(text: str) -> str:
    """Escapa entidades HTML e interpreta negritas, cursivas y código para ReportLab."""
    if not text:
        return ""
    # Escapar caracteres XML para evitar que rompan el parser de Platypus
    escaped = html.escape(text.strip())

    # Bold: **texto** o __texto__
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"__(.+?)__", r"<b>\1</b>", escaped)

    # Italic: *texto* o _texto_ (evitando URLs)
    escaped = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"<i>\1</i>", escaped)
    escaped = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<i>\1</i>", escaped)

    # Monospace code: `codigo`
    escaped = re.sub(
        r"`(.+?)`",
        r'<font face="Courier" color="#9C4221" size="9">\1</font>',
        escaped,
    )

    # Convertir wikilinks de Obsidian [[Nota|Alias]] o [[Nota]] a texto legible
    escaped = re.sub(r"\[\[([^|\]]+)\|([^\]]+)\]\]", r"<b>\2</b>", escaped)
    escaped = re.sub(r"\[\[([^\]]+)\]\]", r"<b>\1</b>", escaped)

    return escaped


def _strip_frontmatter(content: str) -> str:
    """Elimina el bloque frontmatter YAML inicial si existe."""
    trimmed = content.strip()
    if trimmed.startswith("---"):
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", trimmed, re.DOTALL)
        if match:
            return trimmed[match.end() :].strip()
    return trimmed


def generate_pdf(
    title: str,
    markdown_content: str,
    output_path: Path,
    author: str = "Asistente Chismoso",
    category: str = "Documentos",
    tags: list[str] | None = None,
) -> Path:
    """Convierte texto en Markdown a un documento PDF profesional y elegante.

    Args:
        title: Título principal del documento.
        markdown_content: Cuerpo del documento en formato Markdown.
        output_path: Ruta del archivo .pdf destino.
        author: Nombre del autor o usuario destinatario.
        category: Carpeta o temática del documento.
        tags: Lista de etiquetas clasificadoras.

    Returns:
        Path: Ruta absoluta del archivo PDF generado.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=40,
        rightMargin=40,
        topMargin=40,
        bottomMargin=55,
    )

    styles = getSampleStyleSheet()

    # Definir paleta de estilos tipográficos modernos
    color_primary = colors.HexColor("#1A365D")    # Azul noche profundo
    color_secondary = colors.HexColor("#2B6CB0")  # Azul profesional
    color_text = colors.HexColor("#2D3748")       # Gris carbón legible
    color_muted = colors.HexColor("#718096")      # Gris suave
    color_quote_bg = colors.HexColor("#F7FAFC")   # Fondo tenue para citas

    style_title = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=color_primary,
        spaceAfter=6,
    )

    style_meta = ParagraphStyle(
        "DocMeta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=color_muted,
        spaceAfter=12,
    )

    style_h1 = ParagraphStyle(
        "Heading1_Custom",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=19,
        textColor=color_primary,
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True,
    )

    style_h2 = ParagraphStyle(
        "Heading2_Custom",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=color_secondary,
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True,
    )

    style_h3 = ParagraphStyle(
        "Heading3_Custom",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=14,
        textColor=color_text,
        spaceBefore=8,
        spaceAfter=3,
        keepWithNext=True,
    )

    style_body = ParagraphStyle(
        "Body_Custom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=color_text,
        spaceAfter=6,
    )

    style_bullet = ParagraphStyle(
        "Bullet_Custom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=color_text,
        leftIndent=15,
        firstLineIndent=-10,
        spaceAfter=3,
    )

    style_quote = ParagraphStyle(
        "Quote_Custom",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor("#4A5568"),
        leftIndent=16,
        rightIndent=10,
        spaceBefore=6,
        spaceAfter=6,
    )

    style_table_header = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=colors.white,
    )

    style_table_cell = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=color_text,
    )

    story: list[Any] = []

    # 1. ENCABEZADO Y METADATOS DEL DOCUMENTO
    story.append(Paragraph(_clean_markdown_text(title), style_title))

    today_str = date.today().strftime("%d de %B de %Y")
    tags_line = f" • Tags: {', '.join(tags)}" if tags else ""
    meta_text = f"<b>Autor:</b> {author} | <b>Categoría:</b> {category} | <b>Fecha:</b> {today_str}{tags_line}"
    story.append(Paragraph(meta_text, style_meta))

    story.append(HRFlowable(
        width="100%",
        thickness=1.5,
        color=color_primary,
        spaceBefore=0,
        spaceAfter=14,
    ))

    # 2. PROCESAMIENTO DEL CUERPO MARKDOWN
    clean_body = _strip_frontmatter(markdown_content)
    lines = clean_body.split("\n")

    i = 0
    total_lines = len(lines)

    while i < total_lines:
        line = lines[i]
        stripped = line.strip()

        # Línea en blanco
        if not stripped:
            i += 1
            continue

        # Separador horizontal
        if re.match(r"^(\-{3,}|\*{3,}|_{3,})$", stripped):
            story.append(Spacer(1, 4))
            story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#E2E8F0"), spaceAfter=8))
            i += 1
            continue

        # Encabezados
        if stripped.startswith("#"):
            match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
            if match:
                level = len(match.group(1))
                h_text = _clean_markdown_text(match.group(2))
                if level == 1:
                    story.append(Paragraph(h_text, style_h1))
                elif level == 2:
                    story.append(Paragraph(h_text, style_h2))
                else:
                    story.append(Paragraph(h_text, style_h3))
                i += 1
                continue

        # Citas (Blockquotes)
        if stripped.startswith(">"):
            quote_lines: list[str] = []
            while i < total_lines and lines[i].strip().startswith(">"):
                quote_lines.append(re.sub(r"^>\s*", "", lines[i].strip()))
                i += 1
            q_text = " ".join(quote_lines)
            story.append(Paragraph(_clean_markdown_text(q_text), style_quote))
            continue

        # Tablas Markdown (| Col1 | Col2 |)
        if stripped.startswith("|") and stripped.endswith("|"):
            table_lines: list[str] = []
            while i < total_lines and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
                table_lines.append(lines[i].strip())
                i += 1

            if len(table_lines) >= 2:
                table_flowable = _parse_markdown_table(
                    table_lines,
                    style_table_header,
                    style_table_cell,
                )
                if table_flowable:
                    story.append(Spacer(1, 4))
                    story.append(table_flowable)
                    story.append(Spacer(1, 6))
                    continue

        # Viñetas no ordenadas (- o * o •)
        if re.match(r"^[-*•]\s+(.*)$", stripped):
            bullet_match = re.match(r"^[-*•]\s+(.*)$", stripped)
            bullet_content = _clean_markdown_text(bullet_match.group(1) if bullet_match else stripped)
            story.append(Paragraph(f"• {bullet_content}", style_bullet))
            i += 1
            continue

        # Listas numeradas (1. 2. 3.)
        if re.match(r"^\d+[\.\)]\s+(.*)$", stripped):
            num_match = re.match(r"^(\d+[\.\)])\s+(.*)$", stripped)
            if num_match:
                prefix = num_match.group(1)
                num_content = _clean_markdown_text(num_match.group(2))
                story.append(Paragraph(f"<b>{prefix}</b> {num_content}", style_bullet))
            i += 1
            continue

        # Párrafos regulares (pueden ocupar múltiples líneas seguidas)
        p_lines: list[str] = [stripped]
        i += 1
        while i < total_lines:
            nxt = lines[i].strip()
            if not nxt or nxt.startswith(("#", ">", "|", "-", "*", "•")) or re.match(r"^\d+[\.\)]", nxt):
                break
            p_lines.append(nxt)
            i += 1

        p_full = " ".join(p_lines)
        story.append(Paragraph(_clean_markdown_text(p_full), style_body))

    # Construir el documento con el canvas numerado
    doc.build(story, canvasmaker=NumberedCanvas)
    logger.info("PDF generado exitosamente en: %s", output_path)
    return output_path


def _parse_markdown_table(
    table_lines: list[str],
    header_style: ParagraphStyle,
    cell_style: ParagraphStyle,
) -> Table | None:
    """Convierte filas de texto en formato markdown a un Table de ReportLab."""
    parsed_rows: list[list[Paragraph]] = []
    has_separator = False

    for row_idx, line in enumerate(table_lines):
        raw_cells = [c.strip() for c in line.strip("|").split("|")]

        # Omitir fila separadora (|---|---|)
        if any(re.match(r"^:?-+:?$", c) for c in raw_cells):
            has_separator = True
            continue

        row_flowables: list[Paragraph] = []
        is_header = (row_idx == 0) and has_separator is False

        for cell_text in raw_cells:
            st = header_style if is_header else cell_style
            cell_html = _clean_markdown_text(cell_text)
            row_flowables.append(Paragraph(cell_html, st))

        parsed_rows.append(row_flowables)

    if not parsed_rows:
        return None

    # Ajuste automático del ancho de columnas
    col_count = max(len(r) for r in parsed_rows)
    usable_width = letter[0] - 80  # 612 - 80 = 532 pt
    col_width = usable_width / max(col_count, 1)

    t = Table(parsed_rows, colWidths=[col_width] * col_count)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1A365D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#F7FAFC"), colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ("TOPPADDING", (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
    ]))
    return t


def generate_txt(
    title: str,
    content: str,
    output_path: Path,
    author: str = "Asistente Chismoso",
    category: str = "Documentos",
    tags: list[str] | None = None,
) -> Path:
    """Genera un archivo de texto plano (.txt) bien estructurado y formateado.

    Args:
        title: Título legible del documento.
        content: Contenido principal en texto.
        output_path: Ruta del archivo .txt destino.
        author: Nombre del autor o usuario.
        category: Categoría temática.
        tags: Lista de etiquetas.

    Returns:
        Path: Ruta absoluta del archivo TXT generado.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    today_str = date.today().isoformat()
    tags_str = ", ".join(tags) if tags else "documento"

    clean_content = _strip_frontmatter(content)

    header = (
        "=" * 78 + "\n"
        f"DOCUMENTO:  {title}\n"
        f"AUTOR:      {author}\n"
        f"FECHA:      {today_str}\n"
        f"CATEGORÍA:  {category}\n"
        f"ETIQUETAS:  {tags_str}\n"
        + "=" * 78 + "\n\n"
    )

    full_txt = header + clean_content.strip() + "\n"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_txt)

    logger.info("Archivo TXT generado exitosamente en: %s", output_path)
    return output_path
