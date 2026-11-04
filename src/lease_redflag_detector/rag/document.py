"""A document of the RAG corpus as a sequence of structural blocks.

Every extractor (PDF, DOCX, HTML, Markdown) turns its input into the same form, so
cleaning and chunking do not depend on the source format.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

BlockKind = Literal["heading", "paragraph", "list_item", "table", "quote"]


@dataclass
class Block:
    kind: BlockKind
    text: str = ""
    # Heading level (1 is the document title or a top-level section).
    level: int = 0
    # Table cells, row by row; `text` holds the same table as Markdown.
    rows: list[list[str]] = field(default_factory=list)
    # Page in the source PDF, when known.
    page: int | None = None


@dataclass
class Document:
    id: str
    title: str
    blocks: list[Block]
    meta: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n".join(block.text for block in self.blocks)

    @property
    def content_hash(self) -> str:
        """sha256 of the text with whitespace collapsed, for exact deduplication."""
        normalized = " ".join(self.text.split()).casefold()
        return hashlib.sha256(normalized.encode()).hexdigest()

    def save(self, path: Path) -> None:
        path.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> "Document":
        data = json.loads(path.read_text(encoding="utf-8"))
        blocks = [Block(**block) for block in data.pop("blocks")]
        return cls(blocks=blocks, **data)


def table_markdown(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
    lines += ["| " + " | ".join(row) + " |" for row in rows[1:]]
    return "\n".join(lines)
