"""Ingestion of the RAG corpus: extraction, cleaning, pseudonymization, deduplication.

    uv run python -m lease_redflag_detector.rag.ingest

Reads the document list from `data/corpus/sources.toml` and writes:

    data/corpus/documents/<id>.json   blocks and metadata of each document
    data/corpus/manifest.csv          one row per document

Exact duplicates (the same text after whitespace and case normalization) are dropped.
Near duplicates (contracts on one template) are kept, since each holds its own
parties, premises and rent, and marked with the document they are closest to.
"""

import argparse
import csv
import json
import re
import tomllib
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

from lease_redflag_detector.rag.clean import (
    clean_blocks,
    normalize,
    pseudonymize,
    vocabulary,
)
from lease_redflag_detector.rag.document import Block, Document
from lease_redflag_detector.rag.extract import extract, select_sections
from lease_redflag_detector.rag.ocr import ocr_pdf

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "data" / "corpus"
SOURCES = CORPUS / "sources.toml"
DOCUMENTS = CORPUS / "documents"
MANIFEST = CORPUS / "manifest.csv"
PROZORRO = ROOT / "data" / "raw" / "prozorro"
PSEUDONYMS = PROZORRO / "pseudonyms.json"

AUTHORED_LICENSE = "MIT (written for this project)"
LAW_LICENSE = "official document, not an object of copyright"
PROZORRO_LICENSE = "public information, published on Prozorro.Sale"
STATE_LEASE_METHODS = ("legitimatePropertyLease", "regulationsPropertyLease")
# Word 3-gram Jaccard similarity above which two documents are near duplicates. The
# contracts on one template score 0.4–0.6 despite OCR errors, other pairs below 0.2.
NEAR_DUPLICATE = 0.3

MANIFEST_COLUMNS = [
    "id", "title", "type", "format", "access", "status", "version", "date",
    "replaced_by", "source", "source_url", "license", "words", "blocks",
    "content_hash", "near_duplicate_of", "similarity", "path",
]  # fmt: skip


def law_meta(path: Path) -> dict:
    """URL and edition date of an act: the latest date in its editorial notes."""
    downloaded = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")
    notes = " ".join(tag.get_text(" ") for tag in soup.find_all(["em", "i"]))
    dates = [
        date(int(y), int(m), int(d))
        for d, m, y in re.findall(r"(\d{2})\.(\d{2})\.(\d{4})", notes)
    ]
    return {
        "source": "zakon.rada.gov.ua",
        "source_url": downloaded["url"].removesuffix("/print"),
        "date": max(dates).isoformat() if dates else "",
        "license": LAW_LICENSE,
    }


LEGAL_FORMS = [
    ("ТОВАРИСТВО З ОБМЕЖЕНОЮ ВІДПОВІДАЛЬНІСТЮ", "ТОВ"),
    ("ПУБЛІЧНЕ АКЦІОНЕРНЕ ТОВАРИСТВО", "ПАТ"),
    ("ПРИВАТНЕ АКЦІОНЕРНЕ ТОВАРИСТВО", "ПрАТ"),
    ("АКЦІОНЕРНЕ ТОВАРИСТВО", "АТ"),
    ("ПРИВАТНЕ ПІДПРИЄМСТВО", "ПП"),
    ("ФЕРМЕРСЬКЕ ГОСПОДАРСТВО", "ФГ"),
]


def short_name(name: str) -> str:
    """'ТОВАРИСТВО З ОБМЕЖЕНОЮ ВІДПОВІДАЛЬНІСТЮ "НОРМА ТРЕЙД"' → 'ТОВ «Норма Трейд»'."""
    name = normalize(name)
    form = ""
    changed = True
    while changed:  # 'АТ "АКЦІОНЕРНЕ ТОВАРИСТВО "ДТЕК ЗАХІДЕНЕРГО""'
        changed = False
        for full, short in LEGAL_FORMS:
            for candidate in (full, short):
                pattern = rf"^\W*{candidate}\b\W*"
                if re.match(pattern, name, flags=re.IGNORECASE):
                    name = re.sub(pattern, "", name, flags=re.IGNORECASE)
                    form, changed = short, True
    name = re.sub(r'["«»“”]', "", name).strip()
    if name.isupper():  # keep short acronyms: "ДТЕК Західенерго"
        name = " ".join(w if len(w) <= 4 else w.title() for w in name.split())
    return f"{form} «{name}»" if form else name


def prozorro_meta(auction: str) -> dict:
    procedure = json.loads((PROZORRO / auction / "procedure.json").read_text())
    organizations = procedure.get("relatedOrganizations") or {}
    landlord = organizations.get("sellingEntity") or procedure.get("sellingEntity")
    contract = procedure["contracts"][0]
    tenant = contract["buyers"][0]["name"]["uk_UA"]
    address = (procedure.get("items") or [{}])[0].get("address", {})
    city = address.get("locality", {}).get("uk_UA", "")
    city = re.sub(r"^(м\.|смт\.?|с\.)\s*", "", city).strip()
    state = procedure["sellingMethod"].startswith(STATE_LEASE_METHODS)
    landlord_name = short_name(landlord["name"]["uk_UA"])
    signed = (contract.get("dateSigned") or contract.get("datePublished") or "")[:10]
    return {
        "id": "lease_" + auction.rsplit("-", 1)[1],
        "path": str((PROZORRO / auction / "contract.pdf").relative_to(ROOT)),
        "title": f"Договір оренди: {landlord_name} — {short_name(tenant)}, {city}",
        "type": "lease",
        "access": "public",
        "status": "current",
        "date": signed,
        "landlord": landlord_name,
        "tenant": short_name(tenant),
        "city": city,
        "regime": "law_157_ix" if state else "civil_code",
        "source": "Prozorro.Sale",
        "source_url": f"https://prozorro.sale/auction/{auction}",
        "license": PROZORRO_LICENSE,
    }


def load_sources() -> list[dict]:
    entries = tomllib.loads(SOURCES.read_text(encoding="utf-8"))["document"]
    sources = []
    for entry in entries:
        if "auction" in entry:
            meta = prozorro_meta(entry["auction"])
        else:
            meta = dict(entry)
            if meta["type"] == "law":
                meta |= law_meta(ROOT / meta["path"])
            else:
                meta.setdefault("source", "project author")
                meta.setdefault("license", AUTHORED_LICENSE)
        sources.append(meta)
    return sources


def extract_blocks(meta: dict) -> list[Block]:
    path = ROOT / meta["path"]
    # Contracts are structured by their clause numbers, other PDFs by font sizes.
    styled = meta["type"] not in ("lease", "lease_draft")
    blocks = extract(path, ocr=ocr_pdf, styled=styled)
    if sections := meta.get("sections"):
        blocks = select_sections(blocks, sections)
    return blocks


def build_document(
    meta: dict, blocks: list[Block], pseudonyms: dict[str, str], words: set[str]
) -> Document:
    """Clean extracted blocks; OCR'd contracts get whole Latin words read as Cyrillic
    by the corpus vocabulary `words`, before pseudonymization looks for names."""
    lease = meta["type"] == "lease"
    blocks = clean_blocks(blocks, words if lease else None)
    if lease:
        for block in blocks:
            block.text = pseudonymize(block.text, pseudonyms)
            block.rows = [
                [pseudonymize(c, pseudonyms) for c in row] for row in block.rows
            ]
    extra = {k: v for k, v in meta.items() if k not in ("id", "title", "sections")}
    extra["format"] = Path(meta["path"]).suffix.lstrip(".").lower()
    return Document(id=meta["id"], title=meta["title"], blocks=blocks, meta=extra)


def shingles(text: str, n: int = 3) -> set[tuple[str, ...]]:
    words = re.findall(r"\w+", text.casefold())
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def mark_near_duplicates(documents: list[Document]) -> None:
    """Mark each document with its most similar earlier one above the threshold."""
    sets = [shingles(doc.text) for doc in documents]
    for i, doc in enumerate(documents):
        best, best_score = None, 0.0
        for j in range(i):
            union = len(sets[i] | sets[j])
            score = len(sets[i] & sets[j]) / union if union else 0.0
            if score > best_score:
                best, best_score = documents[j], score
        if best is not None and best_score >= NEAR_DUPLICATE:
            doc.meta["near_duplicate_of"] = best.id
            doc.meta["similarity"] = round(best_score, 2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", nargs="+", metavar="ID", help="rebuild these only")
    args = parser.parse_args()

    pseudonyms = {}
    if PSEUDONYMS.exists():
        pseudonyms = json.loads(PSEUDONYMS.read_text(encoding="utf-8"))
    DOCUMENTS.mkdir(parents=True, exist_ok=True)

    extracted: list[tuple[dict, list[Block] | Document]] = []
    for meta in load_sources():
        if args.only and meta["id"] not in args.only:
            extracted.append((meta, Document.load(DOCUMENTS / f"{meta['id']}.json")))
        else:
            extracted.append((meta, extract_blocks(meta)))
    words = vocabulary(
        normalize(block.text)
        for _, item in extracted
        for block in (item.blocks if isinstance(item, Document) else item)
    )

    documents: list[Document] = []
    hashes: dict[str, str] = {}
    for meta, item in extracted:
        if isinstance(item, Document):
            documents.append(item)
            continue
        document = build_document(meta, item, pseudonyms, words)
        if (duplicate := hashes.get(document.content_hash)) is not None:
            print(f"{document.id:<28} skipped: same text as {duplicate}")
            continue
        hashes[document.content_hash] = document.id
        documents.append(document)
        n_words = len(document.text.split())
        print(f"{document.id:<28} {len(document.blocks):>5} blocks {n_words:>7} words")

    mark_near_duplicates(documents)
    with MANIFEST.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        for document in documents:
            document.save(DOCUMENTS / f"{document.id}.json")
            meta = document.meta
            writer.writerow(
                {k: meta.get(k, "") for k in MANIFEST_COLUMNS}
                | {
                    "id": document.id,
                    "title": document.title,
                    "words": len(document.text.split()),
                    "blocks": len(document.blocks),
                    "content_hash": document.content_hash[:16],
                }
            )
    print(f"{len(documents)} documents in {MANIFEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
