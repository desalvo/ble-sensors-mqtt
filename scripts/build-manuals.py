#!/usr/bin/env python3
"""Build separate English and Italian PDF manuals from the Markdown usage guides."""

from __future__ import annotations

import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
LOGO = ROOT / "assets" / "ble-sensors-mqtt-logo.png"
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def inline_markup(text: str) -> str:
    escaped = html.escape(text, quote=False)
    escaped = re.sub(r"`([^`]+)`", r"<font name='Courier'>\1</font>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"\[([^]]+)\]\(([^)]+)\)", r"<u>\1</u>", escaped)
    return escaped


def styles():
    base = getSampleStyleSheet()
    normal = ParagraphStyle(
        "ManualBody", parent=base["BodyText"], fontName="Helvetica", fontSize=9.2,
        leading=12.3, spaceAfter=5, splitLongWords=True,
    )
    bullet = ParagraphStyle(
        "ManualBullet", parent=normal, leftIndent=14, firstLineIndent=-8, bulletIndent=4,
        spaceAfter=3,
    )
    h1 = ParagraphStyle(
        "ManualH1", parent=base["Heading1"], fontName="Helvetica-Bold", fontSize=16,
        leading=19, spaceBefore=10, spaceAfter=6, keepWithNext=True,
    )
    h2 = ParagraphStyle(
        "ManualH2", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=12.5,
        leading=15, spaceBefore=9, spaceAfter=4, keepWithNext=True,
    )
    h3 = ParagraphStyle(
        "ManualH3", parent=base["Heading3"], fontName="Helvetica-Bold", fontSize=10.5,
        leading=13, spaceBefore=7, spaceAfter=3, keepWithNext=True,
    )
    code = ParagraphStyle(
        "ManualCode", parent=normal, fontName="Courier", fontSize=7.4, leading=9.3,
        leftIndent=7, rightIndent=7, spaceBefore=3, spaceAfter=7, backColor=colors.HexColor("#F3F4F6"),
        borderPadding=5,
    )
    cover = ParagraphStyle(
        "CoverTitle", parent=base["Title"], fontName="Helvetica-Bold", fontSize=23,
        leading=28, alignment=TA_CENTER, spaceAfter=12,
    )
    subtitle = ParagraphStyle(
        "CoverSubtitle", parent=normal, fontSize=11, leading=15, alignment=TA_CENTER,
        textColor=colors.HexColor("#444444"),
    )
    return normal, bullet, h1, h2, h3, code, cover, subtitle


def markdown_story(text: str):
    normal, bullet, h1, h2, h3, code, _, _ = styles()
    story = []
    lines = text.splitlines()
    i = 0
    paragraph: list[str] = []

    def flush_paragraph():
        nonlocal paragraph
        if paragraph:
            story.append(Paragraph(inline_markup(" ".join(x.strip() for x in paragraph)), normal))
            paragraph = []

    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            flush_paragraph()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            story.append(Preformatted("\n".join(code_lines), code))
        elif line.startswith("# "):
            flush_paragraph()
            # The document title is already on the cover.
        elif line.startswith("## "):
            flush_paragraph()
            story.append(Paragraph(inline_markup(line[3:].strip()), h1))
        elif line.startswith("### "):
            flush_paragraph()
            story.append(Paragraph(inline_markup(line[4:].strip()), h2))
        elif line.startswith("#### "):
            flush_paragraph()
            story.append(Paragraph(inline_markup(line[5:].strip()), h3))
        elif line.startswith("- "):
            flush_paragraph()
            story.append(Paragraph(inline_markup(line[2:].strip()), bullet, bulletText="•"))
        elif line.startswith("| ") and i + 1 < len(lines) and lines[i + 1].startswith("| ---"):
            flush_paragraph()
            table_lines = [line]
            i += 2  # skip delimiter row
            while i < len(lines) and lines[i].startswith("|"):
                table_lines.append(lines[i])
                i += 1
            rows = []
            for row in table_lines:
                cells = [c.strip() for c in row.strip().strip("|").split("|")]
                rows.append([Paragraph(inline_markup(c), normal) for c in cells])
            if rows:
                width = 170 * mm
                col_widths = [width / len(rows[0])] * len(rows[0])
                table = Table(rows, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
                table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E9EEF5")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B8C1CC")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]))
                story.append(table)
                story.append(Spacer(1, 5))
            continue
        elif not line.strip():
            flush_paragraph()
        elif line.startswith("**English**") or line.startswith("[English]"):
            # Navigation links are useful in Markdown but not in a language-specific PDF.
            flush_paragraph()
        else:
            paragraph.append(line)
        i += 1
    flush_paragraph()
    return story


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.drawString(20 * mm, 10 * mm, f"ble-sensors-mqtt {VERSION}")
    canvas.drawRightString(190 * mm, 10 * mm, str(doc.page))
    canvas.restoreState()


def build(language: str, source_name: str, output_name: str) -> None:
    _, _, _, _, _, _, cover, subtitle = styles()
    title = "Installation and usage manual" if language == "en" else "Manuale di installazione e utilizzo"
    language_name = "English edition" if language == "en" else "Edizione italiana"
    output = DOCS / output_name
    doc = SimpleDocTemplate(
        str(output), pagesize=A4, rightMargin=20 * mm, leftMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"ble-sensors-mqtt {VERSION} - {title}", author="Alessandro De Salvo",
    )
    story = []
    story.append(Spacer(1, 22 * mm))
    if LOGO.exists():
        logo = Image(str(LOGO), width=46 * mm, height=46 * mm)
        logo.hAlign = "CENTER"
        story.append(logo)
        story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("ble-sensors-mqtt", cover))
    story.append(Paragraph(title, subtitle))
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph(f"Version {VERSION} - {language_name}", subtitle))
    story.append(Paragraph("Alessandro De Salvo - EUPL-1.2", subtitle))
    story.append(PageBreak())
    source = (DOCS / source_name).read_text(encoding="utf-8")
    story.extend(markdown_story(source))
    # keep a tiny final spacer so the last paragraph has comfortable bottom breathing room
    story.append(Spacer(1, 3 * mm))
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def main() -> None:
    build("en", "USAGE.en.md", f"ble-sensors-mqtt-manual-v{VERSION}-en.pdf")
    build("it", "USAGE.it.md", f"ble-sensors-mqtt-manual-v{VERSION}-it.pdf")


if __name__ == "__main__":
    main()
