"""A parser for the Markdown subset used by the documents written for the corpus.

Headings (`#`), paragraphs, bullet and numbered lists, block quotes and pipe tables.
Inline markup (`**bold**`, `*italic*`) is kept as text by `parse` and can be removed
with `strip_inline`.
"""

import re

from lease_redflag_detector.rag.document import Block, table_markdown

HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
BULLET = re.compile(r"^\s*(?:[-*]|\d+\.)\s+(.*)$")
TABLE_RULE = re.compile(r"^\|?\s*:?-{3,}")
INLINE = re.compile(r"\*\*(.+?)\*\*|\*(.+?)\*")


def strip_inline(text: str) -> str:
    return INLINE.sub(lambda m: m.group(1) or m.group(2), text)


def table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse(text: str) -> list[Block]:
    blocks: list[Block] = []
    paragraph: list[str] = []
    table: list[list[str]] = []

    def flush() -> None:
        if paragraph:
            blocks.append(Block("paragraph", " ".join(paragraph)))
            paragraph.clear()
        if table:
            rows = [row for row in table if any(row)]
            blocks.append(Block("table", table_markdown(rows), rows=rows))
            table.clear()

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            flush()
        elif stripped.startswith("|"):
            if paragraph:
                flush()
            if not TABLE_RULE.match(stripped):
                table.append(table_cells(stripped))
        elif match := HEADING.match(stripped):
            flush()
            level = len(match.group(1))
            blocks.append(Block("heading", match.group(2).strip(), level=level))
        elif stripped.startswith(">"):
            flush()
            blocks.append(Block("quote", stripped.lstrip("> ").strip()))
        elif (match := BULLET.match(line)) and not re.match(r"^\d+\.\d", stripped):
            flush()
            blocks.append(Block("list_item", match.group(1).strip()))
        else:
            if table:
                flush()
            paragraph.append(stripped)
    flush()
    return blocks
