"""Retrieval metrics over evidence quotes.

A question has one or more pieces of evidence: a document and a quote from it. A
retrieved chunk supports a piece of evidence if it belongs to that document and holds
the quote, so the metrics do not depend on how the documents were chunked.

- recall@k: the share of a question's evidence found in its top k chunks, averaged
  over questions. A question answered from the policy and the law scores 0.5 if only
  one of them is found.
- MRR: the mean of 1 / rank of the first chunk that supports any evidence (0 if none
  is in the list).
"""

import re
from dataclasses import dataclass

from lease_redflag_detector.rag.chunking import Chunk


@dataclass(frozen=True)
class Evidence:
    doc: str
    quote: str


def normalize(text: str) -> str:
    text = re.sub(r"(?m)^\s*-\s+", "", text)
    text = text.replace("’", "'").replace(" ", " ")
    return " ".join(text.split()).casefold()


def supports(chunk: Chunk, evidence: Evidence) -> bool:
    return chunk.doc_id == evidence.doc and normalize(evidence.quote) in normalize(
        chunk.text
    )


def found_at(chunks: list[Chunk], evidence: Evidence) -> int | None:
    """1-based rank of the first chunk that supports the evidence."""
    for rank, chunk in enumerate(chunks, start=1):
        if supports(chunk, evidence):
            return rank
    return None


def recall_at(chunks: list[Chunk], evidence: list[Evidence], k: int) -> float:
    ranks = [found_at(chunks, item) for item in evidence]
    return sum(rank is not None and rank <= k for rank in ranks) / len(evidence)


def reciprocal_rank(chunks: list[Chunk], evidence: list[Evidence]) -> float:
    ranks = [r for item in evidence if (r := found_at(chunks, item)) is not None]
    return 1.0 / min(ranks) if ranks else 0.0
