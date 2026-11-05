"""Compare structure-aware chunking with fixed-size windows on a few documents.

    uv run python scripts/compare_chunking.py

For each document, counts the units a lawyer cites — sections (a law article, a clause
of the clause library, a policy or contract section) and numbered clauses ("3.2.") —
and how many of them each chunker keeps whole inside one chunk. A unit cut in two
leaves half of a rule in each chunk: the half without the condition, or without the
exception, can be retrieved alone. Also reports chunks that start in the middle of a
sentence and the share of chunks that can be cited by section.

Writes the table to results/rag/chunking_comparison.md.
"""

import re
import statistics
from pathlib import Path

from lease_redflag_detector.rag.chunking import (
    MAX_TOKENS,
    NUMBERED,
    TARGET_TOKENS,
    chunk_fixed,
    chunk_structural,
    count_tokens,
    sections,
)
from lease_redflag_detector.rag.document import Document

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = ROOT / "data" / "corpus" / "documents"
OUT = ROOT / "results" / "rag" / "chunking_comparison.md"
SAMPLE = [
    "policy_2026",
    "clause_library_2026",
    "civil_code",
    "law_157_ix",
    "lease_06288",
    "lease_83432",
]


def norm(text: str) -> str:
    text = re.sub(r"(?m)^- ", "", text)
    return " ".join(text.split())


def units(document: Document) -> list[str]:
    """Sections that fit a chunk, and numbered clauses."""
    result = []
    for section in sections(document):
        text = norm(" ".join(block.text for block in section.blocks))
        if count_tokens(text) <= MAX_TOKENS:
            result.append(text)
        result += [
            norm(block.text)
            for block in section.blocks
            if NUMBERED.match(block.text) and count_tokens(block.text) <= MAX_TOKENS
        ]
    return list(dict.fromkeys(u for u in result if len(u) > 20))


def mid_sentence(text: str) -> bool:
    first = text.lstrip("- ")[:1]
    return bool(first) and (first.islower() or first in ",.;:)")


def evaluate(document: Document, chunks) -> dict:
    texts = [norm(chunk.text) for chunk in chunks]
    doc_units = units(document)
    whole = sum(any(unit in text for text in texts) for unit in doc_units)
    return {
        "chunks": len(chunks),
        "median_tokens": statistics.median(chunk.tokens for chunk in chunks),
        "units": len(doc_units),
        "whole": whole / len(doc_units) if doc_units else 1.0,
        "mid_sentence": sum(mid_sentence(c.text) for c in chunks) / len(chunks),
        "with_section": sum(bool(c.section_path) for c in chunks) / len(chunks),
    }


def main() -> None:
    rows = []
    totals = {"structural": [], "fixed": []}
    for doc_id in SAMPLE:
        document = Document.load(DOCUMENTS / f"{doc_id}.json")
        for name, chunks in [
            ("structural", chunk_structural(document)),
            ("fixed", chunk_fixed(document)),
        ]:
            result = evaluate(document, chunks)
            totals[name].append(result)
            rows.append(
                f"| {doc_id} | {name} | {result['chunks']} | "
                f"{result['median_tokens']:.0f} | {result['units']} | "
                f"{result['whole']:.0%} | {result['mid_sentence']:.0%} | "
                f"{result['with_section']:.0%} |"
            )
    for name, results in totals.items():
        n_units = sum(r["units"] for r in results)
        whole = sum(r["whole"] * r["units"] for r in results) / n_units
        n_chunks = sum(r["chunks"] for r in results)
        mid = sum(r["mid_sentence"] * r["chunks"] for r in results) / n_chunks
        cited = sum(r["with_section"] * r["chunks"] for r in results) / n_chunks
        rows.append(
            f"| **all** | **{name}** | {n_chunks} | | {n_units} | **{whole:.0%}** | "
            f"**{mid:.0%}** | **{cited:.0%}** |"
        )
    table = "\n".join(
        [
            (
                f"Structural: sections and clauses, target {TARGET_TOKENS} / max "
                f"{MAX_TOKENS} tokens. Fixed: windows of {TARGET_TOKENS} tokens with "
                "50 tokens of overlap."
            ),
            "",
            (
                "| Document | Chunking | Chunks | Median tokens | Units | Units kept whole "
                "| Chunks starting mid-sentence | Chunks citable by section |"
            ),
            "|---|---|---|---|---|---|---|---|",
            *rows,
        ]
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("# Chunking comparison\n\n" + table + "\n", encoding="utf-8")
    print(table)


if __name__ == "__main__":
    main()
