"""Chunking of corpus documents: by structure, and by fixed size for comparison.

Structure-aware chunking (the one used by the index):

1. A document is split into sections at its headings: an article of a law, a clause
   of the clause library, a section of a policy or a contract. A chunk never spans two
   sections, so it can be cited as "document, section".
2. A section that fits `max_tokens` is one chunk. A longer one (a contract section,
   a chapter of the lease procedure) is packed from whole blocks — paragraphs, list
   items, tables — up to `target_tokens`, preferring to cut before a numbered clause
   ("3.2.", "12."). A list stays with the sentence that introduces it.
3. A single block over `max_tokens` is split at sentence ends; a table at row ends,
   repeating its header row.
4. A short tail is merged into the previous chunk of the same section.
5. A few words of a contract with no sentence in them, or in its signature block
   ("АКЦІОНЕРНЕ ТОВАРИСТВО ОРЕНДАР:"), are dropped: they carry nothing to retrieve.

Every chunk keeps the path of headings above it, which is prepended to its text for
retrieval (a contextual header: "Політика … > 4. Дострокове розірвання …"). The
header counts toward the limit of the embedding model, so a section under a long
heading gets smaller chunks.

Sizes are in tokens of the embedding model's tokenizer.
"""

import hashlib
import re
from dataclasses import asdict, dataclass, field
from functools import lru_cache

from tokenizers import Tokenizer

from lease_redflag_detector.rag.document import Block, Document, table_markdown

TOKENIZER = "intfloat/multilingual-e5-base"
TARGET_TOKENS = 350
MAX_TOKENS = 450
MIN_TOKENS = 60
# The embedding model reads 512 tokens, two of them special, and passages are
# prefixed with "passage: ".
EMBEDDING_MAX_TOKENS = 510
PASSAGE_PREFIX = "passage: "
# A contract chunk shorter than this is a stub if it has no sentence end or is in the
# signature block.
STUB_TOKENS = 25
SIGNATURES = re.compile(r"(?i)підпис|реквізит|погоджено")
# A numbered clause or point: "3.2.", "12.", "Ф-2.3."
NUMBERED = re.compile(r"^(?:Ф-)?\d{1,3}(?:[.-]\d{1,3})*\.?\s")
SENTENCE_END = re.compile(r"(?<=[.;:!?])\s+(?=[А-ЯІЇЄҐA-Z0-9«\"(])")


@lru_cache(maxsize=1)
def tokenizer() -> Tokenizer:
    return Tokenizer.from_pretrained(TOKENIZER)


def count_tokens(text: str) -> int:
    return len(tokenizer().encode(text, add_special_tokens=False).ids)


@dataclass
class Chunk:
    id: str
    doc_id: str
    text: str
    # Headings above the chunk, outermost first.
    section_path: list[str]
    tokens: int
    meta: dict = field(default_factory=dict)

    @property
    def section(self) -> str:
        return " > ".join(self.section_path)

    @property
    def context(self) -> str:
        """The contextual header: document title and section path."""
        title = self.meta.get("title", "")
        return f"{title} > {self.section}" if self.section else title

    @property
    def search_text(self) -> str:
        """What is embedded and indexed for BM25: the header and the text."""
        return f"{self.context}\n{self.text}"

    def to_dict(self) -> dict:
        return asdict(self) | {"section": self.section, "context": self.context}


@dataclass
class Section:
    path: list[str]
    blocks: list[Block]


def sections(document: Document) -> list[Section]:
    """Split a document at its headings; the heading text opens its section."""
    result: list[Section] = []
    path: list[tuple[int, str]] = []
    current = Section([], [])
    for block in document.blocks:
        if block.kind == "heading":
            if current.blocks:
                result.append(current)
            path = [(lvl, text) for lvl, text in path if lvl < block.level]
            path.append((block.level, block.text))
            current = Section([text for _, text in path], [])
        else:
            current.blocks.append(block)
    if current.blocks:
        result.append(current)
    # The document title is in the chunk header already; drop it from the paths.
    title = document.title.casefold()
    for section in result:
        if section.path and section.path[0].casefold() in title:
            section.path = section.path[1:]
    return result


def split_long_block(block: Block, limit: int) -> list[str]:
    """Pieces of a block over the limit: tables by rows, text by sentences."""
    if block.kind == "table" and len(block.rows) > 2:
        header, rows = block.rows[0], block.rows[1:]
        pieces, current = [], []
        for row in rows:
            if count_tokens(table_markdown([header, row])) > limit:
                # A row too long for a chunk alone: its cells as text.
                if current:
                    pieces.append(table_markdown([header, *current]))
                    current = []
                pieces += split_long_block(Block("paragraph", " | ".join(row)), limit)
                continue
            candidate = table_markdown([header, *current, row])
            if current and count_tokens(candidate) > limit:
                pieces.append(table_markdown([header, *current]))
                current = []
            current.append(row)
        if current:
            pieces.append(table_markdown([header, *current]))
        return pieces
    sentences: list[str] = []
    for sentence in SENTENCE_END.split(block.text):
        if sentences and len(sentences[-1].split()) == 1:
            sentences[-1] += " " + sentence  # a clause number: "1." + "Орган …"
        else:
            sentences.append(sentence)
    pieces, current = [], ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip()
        if current and count_tokens(candidate) > limit:
            pieces.append(current)
            current = sentence
        else:
            current = candidate
    pieces.append(current)
    # A "sentence" with no end in sight (a long list typed as one paragraph): words.
    return [part for piece in pieces for part in split_words(piece, limit)]


def split_words(text: str, limit: int) -> list[str]:
    if count_tokens(text) <= limit:
        return [text]
    parts, current = [], []
    for word in text.split():
        if current and count_tokens(" ".join([*current, word])) > limit:
            parts.append(" ".join(current))
            current = []
        current.append(word)
    parts.append(" ".join(current))
    return parts


def block_text(block: Block) -> str:
    return f"- {block.text}" if block.kind == "list_item" else block.text


def pack_section(
    section: Section, target: int, max_tokens: int, min_tokens: int
) -> list[str]:
    """Texts of the chunks of one section."""
    units: list[str] = []
    for block in section.blocks:
        text = block_text(block)
        if count_tokens(text) > max_tokens:
            units += split_long_block(block, target)
        elif (
            block.kind == "list_item"
            and units
            and not NUMBERED.match(text)
            and count_tokens(f"{units[-1]}\n{text}") <= max_tokens
        ):
            units[-1] += "\n" + text  # keep a list with its lead-in sentence
        else:
            units.append(text)

    if count_tokens("\n".join(units)) <= max_tokens:
        return ["\n".join(units)]
    chunks: list[str] = []
    current: list[str] = []
    for unit in units:
        candidate = "\n".join([*current, unit])
        size = count_tokens(candidate)
        over_target = size > target and NUMBERED.match(unit)
        if current and (size > max_tokens or over_target):
            chunks.append("\n".join(current))
            current = []
        current.append(unit)
    if current:
        tail = "\n".join(current)
        merged = f"{chunks[-1]}\n{tail}" if chunks else ""
        if (
            chunks
            and count_tokens(tail) < min_tokens
            and count_tokens(merged) <= max_tokens
        ):
            chunks[-1] = merged
        else:
            chunks.append(tail)
    return chunks


def chunk_meta(document: Document) -> dict:
    keys = [
        "type", "access", "status", "version", "date", "replaced_by", "format",
        "source", "source_url", "license", "near_duplicate_of", "landlord",
        "tenant", "city", "regime",
    ]  # fmt: skip
    meta = {k: document.meta[k] for k in keys if document.meta.get(k)}
    return meta | {"title": document.title, "doc_hash": document.content_hash}


def chunk_structural(
    document: Document,
    target: int = TARGET_TOKENS,
    max_tokens: int = MAX_TOKENS,
    min_tokens: int = MIN_TOKENS,
) -> list[Chunk]:
    meta = chunk_meta(document)
    chunks = []
    for section in sections(document):
        header = " > ".join([document.title, *section.path])
        room = EMBEDDING_MAX_TOKENS - count_tokens(f"{PASSAGE_PREFIX}{header}\n")
        limit = min(max_tokens, room)
        for text in pack_section(section, min(target, limit), limit, min_tokens):
            if not is_stub(text, section.path, meta):
                chunk = make_chunk(document, len(chunks), text, section.path, meta)
                chunks.append(chunk)
    return chunks


def is_stub(text: str, path: list[str], meta: dict) -> bool:
    """A few words of a contract with nothing to retrieve: a party's name from the
    signature block, OCR noise from a stamp."""
    if meta.get("type") != "lease" or count_tokens(text) >= STUB_TOKENS:
        return False
    no_sentence = not text.rstrip().endswith((".", "!", "?", ";"))
    return no_sentence or any(SIGNATURES.search(heading) for heading in path)


def chunk_fixed(
    document: Document, size: int = TARGET_TOKENS, overlap: int = 50
) -> list[Chunk]:
    """Baseline: windows of `size` tokens with `overlap`, ignoring the structure."""
    text = "\n".join(block_text(block) for block in document.blocks)
    encoding = tokenizer().encode(text, add_special_tokens=False)
    meta = chunk_meta(document)
    chunks = []
    step = size - overlap
    for start in range(0, max(len(encoding.ids) - overlap, 1), step):
        end = min(start + size, len(encoding.ids))
        char_start = encoding.offsets[start][0]
        char_end = encoding.offsets[end - 1][1]
        piece = text[char_start:char_end].strip()
        chunks.append(make_chunk(document, len(chunks), piece, [], meta))
    return chunks


def make_chunk(
    document: Document, index: int, text: str, path: list[str], meta: dict
) -> Chunk:
    digest = hashlib.sha256(text.encode()).hexdigest()[:12]
    return Chunk(
        id=f"{document.id}#{index:03d}",
        doc_id=document.id,
        text=text,
        section_path=list(path),
        tokens=count_tokens(text),
        meta=meta | {"chunk_hash": digest},
    )


def main() -> None:
    """Write data/corpus/chunks.jsonl, the structural chunks of every document.

    Fixed-size chunks are not written: the comparisons compute them on the fly.
    """
    import argparse
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    corpus = root / "data" / "corpus"
    parser = argparse.ArgumentParser(description=main.__doc__.splitlines()[0])
    parser.add_argument("--target", type=int, default=TARGET_TOKENS)
    parser.add_argument("--max", type=int, default=MAX_TOKENS)
    args = parser.parse_args()

    documents = [
        Document.load(p) for p in sorted((corpus / "documents").glob("*.json"))
    ]
    chunks = [
        chunk
        for document in documents
        for chunk in chunk_structural(document, args.target, args.max)
    ]
    with (corpus / "chunks.jsonl").open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n")
    print(f"chunks.jsonl: {len(chunks)} chunks from {len(documents)} documents")


if __name__ == "__main__":
    main()
