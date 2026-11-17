"""Render the term-sheet template (markdown with {{placeholders}}) into .docx."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from docx import Document
from docx.shared import Pt, RGBColor

_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")
_BOLD = re.compile(r"\*\*(.+?)\*\*")


def render_term_sheet(template_path: Path, values: dict[str, Any], out_path: Path) -> Path:
    text = _PLACEHOLDER.sub(lambda m: str(values.get(m.group(1), m.group(0))), template_path.read_text(encoding="utf-8"))
    doc = Document()
    doc.core_properties.title = f"Illustrative term sheet {values.get('deal_id', '')}"
    doc.core_properties.author = "Caldova Deal System"
    banner = doc.add_paragraph().add_run(
        "Fictional sample data. Illustrative term sheet from the local Deal System; nothing is sent to a customer."
    )
    banner.bold = True
    banner.font.color.rgb = RGBColor(0xC0, 0x00, 0x00)
    table_rows: list[list[str]] = []

    def flush_table() -> None:
        if not table_rows:
            return
        rows = [r for r in table_rows if not all(set(c) <= set("-: ") for c in r)]
        table = doc.add_table(rows=len(rows), cols=max(len(r) for r in rows))
        table.style = "Table Grid"
        for i, r in enumerate(rows):
            for j, cell in enumerate(r):
                table.cell(i, j).text = _BOLD.sub(r"\1", cell)
        table_rows.clear()

    for line in text.splitlines():
        s = line.strip()
        if s.startswith("|"):
            table_rows.append([c.strip() for c in s.strip("|").split("|")])
            continue
        flush_table()
        if not s:
            continue
        if s.startswith("# "):
            doc.add_heading(s[2:], level=1)
        elif s.startswith("## "):
            doc.add_heading(s[3:], level=2)
        elif s.startswith("- "):
            _add_runs(doc.add_paragraph(style="List Bullet"), s[2:])
        else:
            _add_runs(doc.add_paragraph(), s)
    flush_table()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path


def _add_runs(paragraph: Any, text: str) -> None:
    pos = 0
    for m in _BOLD.finditer(text):
        if m.start() > pos:
            paragraph.add_run(text[pos : m.start()])
        paragraph.add_run(m.group(1)).bold = True
        pos = m.end()
    if pos < len(text):
        paragraph.add_run(text[pos:])
    for run in paragraph.runs:
        run.font.size = Pt(10.5)
