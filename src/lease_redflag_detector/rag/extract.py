"""Text extraction that keeps the structure of a document: headings, paragraphs, list
items, block quotes and tables.

- PDF: the text layer, read with pdfplumber. Documents typeset with larger heading
  fonts get their headings from the font size; scans and plain contracts get them from
  the numbering of the clauses. A missing or broken text layer (a scan, or OCR that
  read Cyrillic as Latin) falls back to OCR text.
- DOCX: paragraph styles (Heading N, List Bullet, Quote) and tables, in body order.
- HTML: zakon.rada.gov.ua acts get their structure from the site's markup (books,
  sections, chapters, articles); other pages from h1–h4, p, li and table, without the
  site chrome (menus, cookie banner, forms, footer).
- Markdown: the subset in `markdown.py`.
"""

import re
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import docx
import pdfplumber
from bs4 import BeautifulSoup, Tag

from lease_redflag_detector.rag import markdown
from lease_redflag_detector.rag.document import Block, table_markdown

CYRILLIC = re.compile(r"[а-яіїєґА-ЯІЇЄҐ]")
LETTER = re.compile(r"[^\W\d_]")
# A clause number at the start of a line: "1.", "2.3.", "4.1.2".
CLAUSE = re.compile(r"^\d{1,2}(\.\d{1,2}){1,3}\.?\s")
# A section heading of a contract: "1. ПРЕДМЕТ ДОГОВОРУ", "РОЗДІЛ 2. ОРЕНДНА ПЛАТА".
SECTION = re.compile(
    r"^(?:[Рр]озділ\s+|РОЗДІЛ\s+)?\d{1,2}\.?\s*[^a-zа-яіїєґ\d.][^a-zа-яіїєґ]{3,}$"
)
# A party's name in capitals, which opens and closes a contract but is not a heading.
PARTY = re.compile(r"^\W*(ТОВАРИСТВО|АКЦІОНЕРНЕ|ПРИВАТНЕ|ПУБЛІЧНЕ|ФІЗИЧНА ОСОБА)")
PAGE_NUMBER = re.compile(
    r"^[\s\-–—]*(?:сторінка\s+)?\d{1,3}(?:\s+(?:з|із|of)\s+\d{1,3})?[\s\-–—]*$",
    re.IGNORECASE,
)
MIN_CYRILLIC_SHARE = 0.6
# Height of the top and bottom page margins where running headers and footers sit, pt.
MARGIN = 70


def cyrillic_share(text: str) -> float:
    letters = LETTER.findall(text)
    return len(CYRILLIC.findall(text)) / len(letters) if letters else 0.0


def is_upper(line: str) -> bool:
    letters = LETTER.findall(line)
    return len(letters) >= 4 and all(not ch.islower() for ch in letters)


# Plain text (OCR output and contracts without styled headings)


def is_title_line(line: str) -> bool:
    """An unnumbered heading in capitals ("РЕКВІЗИТИ ТА ПІДПИСИ СТОРІН"), not a stamp,
    a code or OCR noise from a signature."""
    words = [w for w in re.findall(r"[^\W\d_]{3,}", line) if CYRILLIC.search(w)]
    digits = sum(ch.isdigit() for ch in line)
    return (
        is_upper(line)
        and not line.rstrip().endswith((".", ",", ";"))
        and not PARTY.match(line)
        and len(words) >= 2
        and digits < 4
        and cyrillic_share(line) >= MIN_CYRILLIC_SHARE
    )


def line_key(line: str) -> str:
    """A line with digits masked, to match running headers with page numbers."""
    return re.sub(r"\d+", "#", " ".join(line.split()).casefold())


def repeated_lines(lines: list[str], min_count: int = 3) -> set[str]:
    """Short lines that repeat through a document: running headers and footers."""
    counts = Counter(line_key(line) for line in lines if 0 < len(line.strip()) <= 80)
    return {k for k, n in counts.items() if n >= min_count}


def is_plain_heading(line: str) -> bool:
    """A heading of a contract without styles: a numbered section title in capitals or
    an unnumbered title line, but not a numbered clause."""
    if len(line) > 90 or CLAUSE.match(line):
        return False
    numbered = SECTION.match(line) and len(LETTER.findall(line)) >= 6
    return bool(numbered or is_title_line(line))


def plain_text_blocks(text: str, page_breaks: bool = True) -> list[Block]:
    """Structure a contract given as plain lines.

    Headings are numbered section titles in capitals and the title line; paragraphs
    start at a clause number or after a line that ends a sentence followed by a blank
    line. Words hyphenated at the end of a line are joined.
    """
    lines = text.replace("\f", "\n").splitlines()
    noise = repeated_lines(lines)
    blocks: list[Block] = []
    current: list[str] = []
    blank_before = False

    def flush() -> None:
        if current:
            blocks.append(Block("paragraph", join_lines(current)))
            current.clear()

    for raw in lines:
        line = " ".join(raw.split())
        if not line:
            blank_before = True
            continue
        if PAGE_NUMBER.match(line) or line_key(line) in noise:
            continue
        if is_plain_heading(line):
            flush()
            level = 1 if not blocks and re.match(r"(?i)договір", line) else 2
            if blocks and blocks[-1].kind == "heading" and blocks[-1].level == level:
                blocks[-1].text += " " + line  # a title split over two lines
            else:
                blocks.append(Block("heading", line, level=level))
        elif CLAUSE.match(line):
            flush()
            current.append(line)
        else:
            ends_sentence = bool(current) and current[-1].rstrip().endswith(
                (".", ";", ":")
            )
            if blank_before and ends_sentence:
                flush()
            current.append(line)
        blank_before = False
    flush()
    return blocks


def join_lines(lines: list[str]) -> str:
    text = lines[0]
    for line in lines[1:]:
        if re.search(r"\w-$", text) and line[:1].islower():
            text = text[:-1] + line  # a word hyphenated at the line end
        else:
            text += " " + line
    return text


# PDF


def pdf_has_text(pdf_path: Path) -> bool:
    with pdfplumber.open(pdf_path) as pdf:
        text = "".join(page.extract_text() or "" for page in pdf.pages)
    return len(text.split()) >= 100 and cyrillic_share(text) >= MIN_CYRILLIC_SHARE


def pdf_blocks(
    pdf_path: Path,
    ocr: Callable[[Path], str] | None = None,
    styled: bool = True,
) -> list[Block]:
    """Blocks of a PDF; `ocr` returns the text of a scan (or a broken text layer).

    `styled=False` structures the text by its clause numbering even when the PDF has
    larger fonts: contracts use them for the title only, and their layout tables
    (parties, signatures) are not data.
    """
    if not pdf_has_text(pdf_path):
        if ocr is None:
            raise ValueError(
                f"{pdf_path} has no usable text layer and no OCR was given"
            )
        return plain_text_blocks(ocr(pdf_path))
    with pdfplumber.open(pdf_path) as pdf:
        sizes = Counter(
            round(char["size"]) for page in pdf.pages for char in page.chars
        )
        body_size = sizes.most_common(1)[0][0]
        heading_sizes = sorted((s for s in sizes if s >= body_size + 2), reverse=True)
        if not styled or not heading_sizes:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            return plain_text_blocks(text)
        return styled_pdf_blocks(pdf, body_size, heading_sizes)


def styled_pdf_blocks(pdf, body_size: int, heading_sizes: list[int]) -> list[Block]:
    pages = []
    for number, page in enumerate(pdf.pages, start=1):
        tables = page.find_tables()
        boxes = [table.bbox for table in tables]

        def outside(obj, boxes=boxes) -> bool:
            return not any(
                x0 <= obj["x0"]
                and obj["x1"] <= x1
                and top <= obj["top"]
                and obj["bottom"] <= bottom
                for x0, top, x1, bottom in boxes
            )

        lines = page.filter(outside).extract_text_lines()
        items = [(line["top"], "line", line) for line in lines]
        items += [(table.bbox[1], "table", table) for table in tables]
        pages.append((number, page.height, sorted(items, key=lambda item: item[0])))

    # Running headers and footers: lines in the top or bottom margin of most pages.
    margin_lines = Counter()
    for _, height, items in pages:
        for top, kind, obj in items:
            if kind == "line" and (top < MARGIN or top > height - MARGIN):
                margin_lines[line_key(obj["text"])] += 1
    chrome = {text for text, n in margin_lines.items() if n >= max(2, len(pages) // 2)}

    blocks: list[Block] = []
    current: list[str] = []
    last_bottom = None

    def flush() -> None:
        if current:
            text = join_lines(current)
            if text.startswith("•"):
                blocks.append(
                    Block("list_item", text.lstrip("• ").strip(), page=page_number)
                )
            else:
                blocks.append(Block("paragraph", text, page=page_number))
            current.clear()

    for page_number, height, items in pages:
        last_bottom = None
        for top, kind, obj in items:
            if kind == "table":
                flush()
                rows = [
                    [" ".join((cell or "").split()) for cell in row]
                    for row in obj.extract()
                ]
                blocks.append(
                    Block("table", table_markdown(rows), rows=rows, page=page_number)
                )
                last_bottom = obj.bbox[3]
                continue
            text = obj["text"].strip()
            if line_key(text) in chrome or PAGE_NUMBER.match(text):
                continue
            size = round(max(char["size"] for char in obj["chars"]))
            if size in heading_sizes:
                flush()
                level = heading_sizes.index(size) + 1
                if (
                    blocks
                    and blocks[-1].kind == "heading"
                    and blocks[-1].level == level
                    and last_bottom is not None
                    and top - last_bottom < size
                ):
                    blocks[-1].text += " " + text  # a heading wrapped over two lines
                else:
                    blocks.append(Block("heading", text, level=level, page=page_number))
            else:
                gap = top - last_bottom if last_bottom is not None else 0
                if text.startswith("•") or gap > body_size * 0.9:
                    flush()
                current.append(text)
            last_bottom = obj["bottom"]
    flush()
    return blocks


# DOCX


def docx_blocks(path: Path) -> list[Block]:
    document = docx.Document(path)
    blocks: list[Block] = []
    paragraphs = {p._element: p for p in document.paragraphs}
    tables = {t._element: t for t in document.tables}
    for element in document.element.body.iterchildren():
        if element in tables:
            rows = [
                [" ".join(cell.text.split()) for cell in row.cells]
                for row in tables[element].rows
            ]
            blocks.append(Block("table", table_markdown(rows), rows=rows))
            continue
        paragraph = paragraphs.get(element)
        if paragraph is None:
            continue
        text = " ".join(paragraph.text.split())
        if not text:
            continue
        style = paragraph.style.name if paragraph.style is not None else ""
        if style == "Title":
            blocks.append(Block("heading", text, level=1))
        elif style.startswith("Heading"):
            level = int(style.split()[-1]) if style.split()[-1].isdigit() else 1
            blocks.append(Block("heading", text, level=level))
        elif style.startswith("List"):
            blocks.append(Block("list_item", text))
        elif style in ("Quote", "Intense Quote"):
            blocks.append(Block("quote", text))
        elif is_plain_heading(text):
            # Contracts typed without heading styles: "1. ПРЕДМЕТ ДОГОВОРУ".
            level = 1 if not blocks and re.match(r"(?i)договір", text) else 2
            blocks.append(Block("heading", text, level=level))
        else:
            blocks.append(Block("paragraph", text))
    return blocks


# HTML

CHROME_TAGS = [
    "script",
    "style",
    "noscript",
    "nav",
    "header",
    "footer",
    "form",
    "button",
    "svg",
]
CHROME_CLASSES = re.compile(r"cookie|breadcrumb|banner|lang|btn|menu|share|social")


def html_blocks(path: Path) -> list[Block]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")
    source = soup.find("meta", property="og:url")
    if source is not None and "zakon.rada.gov.ua" in source.get("content", ""):
        return rada_blocks(soup)
    for tag in soup.find_all(CHROME_TAGS):
        tag.decompose()
    for tag in soup.find_all(class_=CHROME_CLASSES):
        tag.decompose()
    body = soup.find("main") or soup.body or soup
    blocks: list[Block] = []
    for tag in body.find_all(["h1", "h2", "h3", "h4", "p", "li", "table"]):
        if tag.find_parent("table") is not None:
            continue
        if tag.name == "table":
            rows = [
                [
                    " ".join(cell.get_text(" ").split())
                    for cell in row.find_all(["td", "th"])
                ]
                for row in tag.find_all("tr")
            ]
            blocks.append(Block("table", table_markdown(rows), rows=rows))
            continue
        text = " ".join(tag.get_text(" ").split())
        if not text:
            continue
        if tag.name.startswith("h"):
            blocks.append(Block("heading", text, level=int(tag.name[1])))
        elif tag.name == "li":
            blocks.append(Block("list_item", text))
        else:
            blocks.append(Block("paragraph", text))
    return blocks


def rada_text(tag: Tag) -> str:
    text = " ".join(tag.get_text(" ").split())
    # Inserted points and articles are numbered with a superscript: "29 - 1 ." → "29-1."
    return re.sub(r"(\d+) - (\d+) ?\.", r"\1-\2.", text)


def rada_heading_level(text: str, classes: set[str]) -> int:
    if "rvts23" in classes:
        return 1
    lowered = text.casefold()
    if lowered.startswith("розділ"):
        return 2
    if lowered.startswith("глава"):
        return 3
    if lowered.startswith("§"):
        return 4
    return 2


def rada_blocks(soup: BeautifulSoup) -> list[Block]:
    """An act from zakon.rada.gov.ua without editorial notes and signatures.

    Levels: 1 the act or an annex it approves (a Procedure, a Methodology) or a book of
    a code, 2 a section, 3 a chapter, 4 a paragraph (§), 5 an article.
    """
    for note in soup.find_all("em"):
        note.decompose()  # editorial notes: "{Із змінами, внесеними …}"
    blocks: list[Block] = []
    body = soup.find(class_="rvps6") or soup.find(class_="rvts9")
    if body is not None:
        tags = body.find_parent("div").find_all(["p", "table", "pre"])
    else:
        tags = soup.find_all("pre")  # an older act, typeset as preformatted text
    for tag in tags:
        if tag.name == "p" and tag.find_parent("table") is not None:
            continue
        classes = set(tag.get("class") or [])
        if tag.name == "table":
            blocks += rada_table(tag)
            continue
        if tag.name == "pre":
            blocks += rada_pre(tag)
            continue
        text = rada_text(tag)
        if (
            not text
            or text.startswith("{")
            or classes & {"rvps4", "rvps15", "rvps17", "rvps18"}
        ):
            continue
        span_classes = {
            c for span in tag.find_all("span") for c in (span.get("class") or [])
        }
        if classes & {"rvps6", "rvps7"} and span_classes & {"rvts15", "rvts23"}:
            level = 1 if "rvps6" in classes else rada_heading_level(text, span_classes)
            if (
                blocks
                and blocks[-1].kind == "heading"
                and blocks[-1].level == level
                and len(blocks[-1].text) < 25
            ):
                blocks[-1].text += " " + text  # "Глава 58" + "НАЙМ (ОРЕНДА)"
            else:
                blocks.append(Block("heading", text, level=level))
        elif "rvts15" in span_classes and text.startswith(("Розділ", "§", "Глава")):
            blocks.append(
                Block("heading", text, level=rada_heading_level(text, span_classes))
            )
        elif re.match(r"Стаття \d", text) and "rvts9" in span_classes:
            blocks.append(Block("heading", text, level=5))
        else:
            blocks.append(Block("paragraph", text))
    return blocks


def rada_pre(pre: Tag) -> list[Block]:
    """Older acts are typeset as preformatted text: "<b>Стаття 3.</b> Розмір пені …"."""
    for note in pre.find_all("i"):
        note.decompose()  # "( Статтю 2 виключено … )"
    text = rada_text(pre)
    if not text or text.startswith(("{", "(")):
        return []
    bold = pre.find("b")
    title = " ".join(bold.get_text(" ").split()) if bold is not None else ""
    if re.match(r"Стаття \d", title) and text.startswith(title):
        body = text[len(title) :].strip()
        return [Block("heading", title, level=5)] + (
            [Block("paragraph", body)] if body else []
        )
    return [Block("paragraph", text)]


def rada_table(table: Tag) -> list[Block]:
    """A data table as a table block; a layout table (formulas) as its paragraphs."""
    rows = []
    for row in table.find_all("tr"):
        cells = [
            " ".join(cell.get_text(" ").split()) for cell in row.find_all(["td", "th"])
        ]
        if any(cells):
            rows.append(cells)
    if not rows or table.find("img") is not None:
        return []
    if max(sum(bool(cell) for cell in row) for row in rows) >= 3:
        return [Block("table", table_markdown(rows), rows=rows)]
    return [
        Block("paragraph", cell)
        for row in rows
        for cell in row
        if cell and not cell.startswith("{")
    ]


def select_sections(blocks: list[Block], prefixes: list[str]) -> list[Block]:
    """Keep only the headings that start with one of `prefixes` and their content."""
    selected: list[Block] = []
    keep_level: int | None = None
    for block in blocks:
        if block.kind == "heading":
            if keep_level is not None and block.level <= keep_level:
                keep_level = None
            if keep_level is None and block.text.startswith(tuple(prefixes)):
                keep_level = block.level
        if keep_level is not None:
            selected.append(block)
    return selected


# Markdown


def markdown_blocks(path: Path) -> list[Block]:
    blocks = markdown.parse(path.read_text(encoding="utf-8"))
    for block in blocks:
        block.text = markdown.strip_inline(block.text)
        block.rows = [
            [markdown.strip_inline(cell) for cell in row] for row in block.rows
        ]
    return blocks


def extract(
    path: Path, ocr: Callable[[Path], str] | None = None, styled: bool = True
) -> list[Block]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return pdf_blocks(path, ocr, styled)
    if suffix == ".docx":
        return docx_blocks(path)
    if suffix in (".html", ".htm"):
        return html_blocks(path)
    if suffix in (".md", ".txt"):
        return markdown_blocks(path)
    raise ValueError(f"unsupported format: {path}")
