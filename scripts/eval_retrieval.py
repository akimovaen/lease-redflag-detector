"""Evaluate retrieval on the question set in evals/retrieval_questions.toml.

    uv run python scripts/eval_retrieval.py

Runs every question through vector search, BM25, hybrid search and hybrid search with
reranking, over the structural chunks and over fixed-size windows (computed here from
the documents), and once more with reranking but without the default filter, to show
what the filter keeps out. Writes results/rag/retrieval_metrics.md and the top
chunks of every run to results/rag/retrieval_runs.json.
"""

import json
import statistics
import time
import tomllib
from pathlib import Path

from lease_redflag_detector.rag.chunking import chunk_fixed
from lease_redflag_detector.rag.document import Document
from lease_redflag_detector.rag.metrics import (
    Evidence,
    found_at,
    recall_at,
    reciprocal_rank,
)
from lease_redflag_detector.rag.retrieve import (
    MODES,
    NO_FILTERS,
    Filters,
    Retriever,
    load_chunks,
)

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / "evals" / "retrieval_questions.toml"
DOCUMENTS = ROOT / "data" / "corpus" / "documents"
OUT = ROOT / "results" / "rag"
TOP = 10
KS = (1, 3, 5, 10)


def load_questions() -> list[dict]:
    questions = tomllib.loads(QUESTIONS.read_text(encoding="utf-8"))["question"]
    for question in questions:
        question["evidence"] = [Evidence(**item) for item in question["evidence"]]
    return questions


def check_evidence(questions: list[dict], chunkings: dict) -> None:
    """Every quote must be in some chunk of its document in every chunking."""
    for name, chunks in chunkings.items():
        for question in questions:
            for item in question["evidence"]:
                if found_at(chunks, item) is None:
                    raise SystemExit(
                        f"{question['id']}: {item.doc} has no {name} chunk with "
                        f"the quote {item.quote!r}"
                    )


def main() -> None:
    questions = load_questions()
    documents = [Document.load(p) for p in sorted(DOCUMENTS.glob("*.json"))]
    chunkings = {
        "structural": load_chunks(),
        "fixed": [c for document in documents for c in chunk_fixed(document)],
    }
    check_evidence(questions, chunkings)

    configs = [(chunking, mode, "in force") for chunking in chunkings for mode in MODES]
    configs.append(("structural", "hybrid_rerank", "all versions"))
    retrievers = {
        name: Retriever(chunks, collection=f"chunks_{name}")
        for name, chunks in chunkings.items()
    }

    rows, ranks, runs = [], {}, {}
    for chunking, mode, scope in configs:
        name = f"{chunking} / {mode}" + (
            " / all versions" if scope != "in force" else ""
        )
        filters = Filters() if scope == "in force" else NO_FILTERS
        recalls = {k: [] for k in KS}
        rr, outdated, latencies = [], 0, []
        for question in questions:
            start = time.perf_counter()
            hits = retrievers[chunking].search(question["question"], mode, TOP, filters)
            latencies.append(time.perf_counter() - start)
            chunks = [hit.chunk for hit in hits]
            evidence = question["evidence"]
            for k in KS:
                recalls[k].append(recall_at(chunks, evidence, k))
            rr.append(reciprocal_rank(chunks, evidence))
            outdated += sum(c.meta.get("status") == "outdated" for c in chunks[:5])
            first = [found_at(chunks, item) for item in evidence]
            ranks.setdefault(question["id"], {})[name] = first
            runs.setdefault(name, {})[question["id"]] = [c.id for c in chunks]
        rows.append(
            f"| {name} | "
            + " | ".join(f"{statistics.mean(recalls[k]):.2f}" for k in KS)
            + f" | **{statistics.mean(rr):.2f}** | {outdated} | "
            f"{statistics.median(latencies) * 1000:.0f} ms |"
        )
        print(rows[-1])

    names = list(runs)
    per_question = [
        f"| {q['id']} | {q['kind']} | "
        + " | ".join(
            " ".join("–" if r is None else str(r) for r in ranks[q["id"]][name])
            for name in names
        )
        + " |"
        for q in questions
    ]
    report = "\n".join(
        [
            "# Retrieval evaluation",
            "",
            (
                f"{len(questions)} questions from `evals/retrieval_questions.toml`, "
                f"{sum(len(q['evidence']) for q in questions)} pieces of evidence, "
                f"top {TOP}. Filter: documents in force unless marked otherwise."
            ),
            "",
            (
                "| Config | recall@1 | recall@3 | recall@5 | recall@10 | MRR "
                "| Outdated chunks in top 5 | Latency p50 |"
            ),
            "|---|---|---|---|---|---|---|---|",
            *rows,
            "",
            "## Rank of each piece of evidence",
            "",
            "– means not in the top 10.",
            "",
            "| Question | Kind | " + " | ".join(names) + " |",
            "|---|---|" + "---|" * len(names),
            *per_question,
            "",
        ]
    )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "retrieval_metrics.md").write_text(report, encoding="utf-8")
    (OUT / "retrieval_runs.json").write_text(
        json.dumps(runs, ensure_ascii=False, indent=1), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
