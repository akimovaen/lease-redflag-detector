"""Render the documents written for the RAG corpus into the formats they would have.

    uv run python scripts/render_corpus.py

The texts are kept as Markdown in `data/corpus/authored/`, which is easy to review and
edit. A company keeps its policies and minutes in Word and sends brochures and reports
as PDF, so this script writes them to `data/corpus/sources/` as DOCX and PDF, with the
page headers and footers such files usually have. The web page and the newsletter are
copied as they are (HTML and Markdown).

The rendered files are committed: they are the corpus. Rerun the script after editing
a Markdown source. PDF rendering uses the Arial font of macOS.
"""

import re
import shutil
from pathlib import Path

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
from fpdf import FPDF
from fpdf.fonts import FontFace

from lease_redflag_detector.rag.document import Block
from lease_redflag_detector.rag.markdown import parse, strip_inline

ROOT = Path(__file__).resolve().parents[1]
AUTHORED = ROOT / "data" / "corpus" / "authored"
SOURCES = ROOT / "data" / "corpus" / "sources"
FONTS = Path("/System/Library/Fonts/Supplemental")
COMPANY = "ТОВ «Демо Нерухомість»"

# Markdown source → (format, running header).
RENDER = {
    "landlord_policy_2026": (
        "docx",
        "Політика укладення договорів оренди · версія 2.0",
    ),
    "landlord_policy_2024": (
        "docx",
        "Політика укладення договорів оренди · версія 1.0",
    ),
    "clause_library_2026": ("docx", "Бібліотека погоджених формулювань · версія 2.0"),
    "commercial_committee_minutes_2026_03": ("docx", "Конфіденційно"),
    "demo_city_brochure": ("pdf", "ТРЦ «Демо Сіті» · пропозиція для орендарів"),
    "market_research_2025": ("pdf", "Для внутрішнього використання"),
}
COPY = ["demo_plaza_page.html", "staff_newsletter_2026_04.md"]

BOLD = re.compile(r"\*\*(.+?)\*\*")


def add_runs(paragraph, text: str) -> None:
    """Add text to a DOCX paragraph, with **bold** spans as bold runs."""
    for i, part in enumerate(BOLD.split(text)):
        if part:
            run = paragraph.add_run(strip_inline(part))
            run.bold = i % 2 == 1


def render_docx(blocks: list[Block], header: str, path: Path) -> None:
    document = docx.Document()
    style = document.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(12)
    section = document.sections[0]
    section.header.paragraphs[0].text = f"{COMPANY} · {header}"
    footer = section.footer.paragraphs[0]
    footer.text = "Документ є власністю Компанії. Копіювання без дозволу заборонено."
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER

    for block in blocks:
        if block.kind == "heading":
            document.add_heading(strip_inline(block.text), level=min(block.level, 3))
        elif block.kind == "list_item":
            add_runs(document.add_paragraph(style="List Bullet"), block.text)
        elif block.kind == "quote":
            add_runs(document.add_paragraph(style="Quote"), block.text)
        elif block.kind == "table":
            table = document.add_table(rows=0, cols=len(block.rows[0]))
            table.style = "Table Grid"
            for row in block.rows:
                cells = table.add_row().cells
                for cell, value in zip(cells, row, strict=False):
                    cell.text = strip_inline(value)
        else:
            add_runs(document.add_paragraph(), block.text)
    document.save(path)


class Pdf(FPDF):
    def __init__(self, header_text: str):
        super().__init__()
        self.header_text = header_text
        self.add_font("Arial", "", FONTS / "Arial.ttf")
        self.add_font("Arial", "B", FONTS / "Arial Bold.ttf")
        self.add_font("Arial", "I", FONTS / "Arial Italic.ttf")
        self.set_margins(20, 20, 20)
        self.set_auto_page_break(True, margin=20)

    def header(self):
        self.set_font("Arial", "", 8)
        self.cell(0, 6, f"{COMPANY} · {self.header_text}", align="R")
        self.ln(10)

    def footer(self):
        self.set_y(-14)
        self.set_font("Arial", "", 8)
        self.cell(0, 6, f"Сторінка {self.page_no()} з {{nb}}", align="C")


def pdf_markdown(text: str) -> str:
    """fpdf2 markup: **bold** stays, *italic* becomes __italic__."""
    return re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"__\1__", text)


def render_pdf(blocks: list[Block], header: str, path: Path) -> None:
    pdf = Pdf(header)
    pdf.add_page()
    sizes = {1: 18, 2: 14, 3: 12}
    for block in blocks:
        if block.kind == "heading":
            pdf.ln(3)
            pdf.set_font("Arial", "B", sizes.get(block.level, 12))
            pdf.multi_cell(0, 8, strip_inline(block.text))
            pdf.ln(1)
        elif block.kind == "table":
            pdf.set_font("Arial", "", 9)
            headings = FontFace(emphasis="BOLD")
            with pdf.table(headings_style=headings, line_height=5) as table:
                for row in block.rows:
                    cells = table.row()
                    for value in row:
                        cells.cell(strip_inline(value))
            pdf.ln(3)
        else:
            pdf.set_font("Arial", "", 10.5)
            text = pdf_markdown(block.text)
            if block.kind == "list_item":
                text = "•  " + text
            pdf.multi_cell(0, 5.5, text, markdown=True)
            pdf.ln(2)
    pdf.output(str(path))


def main() -> None:
    SOURCES.mkdir(parents=True, exist_ok=True)
    for name, (fmt, header) in RENDER.items():
        blocks = parse((AUTHORED / f"{name}.md").read_text(encoding="utf-8"))
        path = SOURCES / f"{name}.{fmt}"
        if fmt == "docx":
            render_docx(blocks, header, path)
        else:
            render_pdf(blocks, header, path)
        print(f"{path.relative_to(ROOT)}  {len(blocks)} blocks")
    for name in COPY:
        shutil.copyfile(AUTHORED / name, SOURCES / name)
        print(f"{(SOURCES / name).relative_to(ROOT)}  copied")


if __name__ == "__main__":
    main()
