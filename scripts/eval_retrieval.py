"""Evaluate retrieval on the red flag set in evals/redflag_retrieval.toml.

    uv run python scripts/eval_retrieval.py --name reviewed-set --note "first run"

Every red flag is searched three ways:

1. **One list**: the clause and its type description as one query over the whole
   corpus, top 10, in each search mode, over the structural chunks and over fixed-size
   windows (computed here from the documents), and once more with reranking but
   without the default filter, to show what the filter keeps out.
2. **By role** (`rag/redline_search.py`): each role with its own filter and k, with
   and without the type description in the query. The scored roles return at most
   3 + 3 + 3 + 2 = 11 chunks, about the budget of the one list (10).
3. **Thresholds**: the role search scored without a threshold and cut at several
   reranker scores, for the recall of each role and the share of flags with no
   precedent whose precedent slot comes back empty.

Trap flags list under `avoid` passages of outdated or wrong-regime documents that
match the clause better than the right sources. Every search reports the share of
them it returned; the one list also counts the flags where a trap passage ranks above
all the right evidence.

Every run goes to its own folder, results/rag/retrieval/<date>_<name>/, and is never
overwritten:

- run.json: what was run (commit, hashes of the flag set and the chunks, models,
  parameters, note);
- metrics.json: every metric;
- hits.json: the chunks every search returned, with reranker scores;
- report.md: the tables of this run.

results/rag/retrieval/history.md is rebuilt from all runs, one row each. Runs compare
only on the same flag set and chunks: the table shows their hashes.
"""

import argparse
import datetime
import hashlib
import json
import statistics
import subprocess
import time
import tomllib
from pathlib import Path

from lease_redflag_detector.extraction.schema import RedFlag
from lease_redflag_detector.rag import redline_search, retrieve
from lease_redflag_detector.rag.chunking import Chunk, chunk_fixed
from lease_redflag_detector.rag.document import Document
from lease_redflag_detector.rag.embeddings import MODEL as EMBEDDING_MODEL
from lease_redflag_detector.rag.metrics import (
    Evidence,
    found_at,
    recall_at,
    reciprocal_rank,
)
from lease_redflag_detector.rag.redline_search import (
    MIN_SCORE,
    ROLES,
    RedlineSearch,
    build_query,
)
from lease_redflag_detector.rag.retrieve import (
    CHUNKS,
    MODES,
    NO_FILTERS,
    Filters,
    Hit,
    Retriever,
    load_chunks,
)

ROOT = Path(__file__).resolve().parents[1]
FLAGS = ROOT / "evals" / "redflag_retrieval.toml"
DOCUMENTS = ROOT / "data" / "corpus" / "documents"
OUT = ROOT / "results" / "rag" / "retrieval"
TOP = 10
KS = (1, 3, 5, 10)
SCORED_ROLES = ("position", "wording", "law", "precedent")
THRESHOLDS = (0.0, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3)
QUERIES = {True: "clause + type description", False: "clause only"}


def load_flags() -> list[dict]:
    flags = tomllib.loads(FLAGS.read_text(encoding="utf-8"))["flag"]
    for flag in flags:
        flag["red_flag"] = RedFlag(type=flag["type"], quote=flag["quote"])
        flag["evidence"] = {
            role: [Evidence(**item) for item in flag[role]] for role in SCORED_ROLES
        }
        flag["avoid"] = [Evidence(**item) for item in flag.get("avoid", [])]
    return flags


def all_evidence(flag: dict) -> list[Evidence]:
    return [item for role in SCORED_ROLES for item in flag["evidence"][role]]


def check_evidence(flags: list[dict], chunkings: dict) -> None:
    """Every quote must be in some chunk of its document in every chunking."""
    for name, chunks in chunkings.items():
        for flag in flags:
            for item in all_evidence(flag) + flag["avoid"]:
                if found_at(chunks, item) is None:
                    raise SystemExit(
                        f"{flag['id']}: {item.doc} has no {name} chunk with "
                        f"the quote {item.quote!r}"
                    )


def mean(values: list[float]) -> float | None:
    return round(statistics.mean(values), 4) if values else None


def share_found(chunks: list[Chunk], evidence: list[Evidence]) -> float:
    return recall_at(chunks, evidence, len(chunks)) if chunks else 0.0


def trap_first(chunks: list[Chunk], flag: dict) -> bool:
    """A trap passage ranks above every piece of the right evidence."""
    traps = [found_at(chunks, item) for item in flag["avoid"]]
    traps = [rank for rank in traps if rank is not None]
    if not traps:
        return False
    right = [found_at(chunks, item) for item in all_evidence(flag)]
    right = [rank for rank in right if rank is not None]
    return not right or min(traps) < min(right)


def one_list(flags: list[dict], retrievers: dict) -> tuple[dict, dict]:
    configs = [(c, mode, True) for c in retrievers for mode in MODES]
    configs.append(("structural", "hybrid_rerank", False))
    metrics, hits = {}, {}
    for chunking, mode, in_force in configs:
        name = f"{chunking} / {mode}" + ("" if in_force else " / all versions")
        filters = Filters() if in_force else NO_FILTERS
        recalls = {k: [] for k in KS}
        roles = {role: [] for role in SCORED_ROLES}
        rr, outdated, latencies, avoid, traps_first = [], 0, [], [], 0
        for flag in flags:
            query = build_query(flag["red_flag"])
            start = time.perf_counter()
            found = retrievers[chunking].search(query, mode, TOP, filters)
            latencies.append(time.perf_counter() - start)
            chunks = [hit.chunk for hit in found]
            evidence = all_evidence(flag)
            for k in KS:
                recalls[k].append(recall_at(chunks, evidence, k))
            for role in SCORED_ROLES:
                if flag["evidence"][role]:
                    roles[role].append(share_found(chunks, flag["evidence"][role]))
            rr.append(reciprocal_rank(chunks, evidence))
            outdated += sum(c.meta.get("status") == "outdated" for c in chunks[:5])
            if flag["avoid"]:
                avoid.append(share_found(chunks, flag["avoid"]))
                traps_first += trap_first(chunks, flag)
            hits.setdefault(name, {})[flag["id"]] = [
                [hit.chunk.id, round(hit.score, 4)] for hit in found
            ]
        metrics[name] = {
            **{f"recall@{k}": mean(recalls[k]) for k in KS},
            "mrr": mean(rr),
            "roles": {role: mean(roles[role]) for role in SCORED_ROLES},
            "outdated_in_top5": outdated,
            "avoid": mean(avoid),
            "trap_first": traps_first,
            "latency_p50_s": round(statistics.median(latencies), 3),
        }
        print(name, metrics[name][f"recall@{TOP}"])
    return metrics, hits


def cut(hits: dict[str, list[Hit]], threshold: float) -> dict[str, list[Chunk]]:
    return {
        role: [hit.chunk for hit in role_hits if hit.score >= threshold]
        for role, role_hits in hits.items()
    }


def role_scores(flags: list[dict], results: dict, threshold: float) -> dict:
    """Recall of every role, overall recall, and empty precedent slots."""
    roles = {role: [] for role in SCORED_ROLES}
    overall, empty, avoid = [], [], []
    for flag in flags:
        chunks = cut(results[flag["id"]], threshold)
        for role in SCORED_ROLES:
            if flag["evidence"][role]:
                roles[role].append(share_found(chunks[role], flag["evidence"][role]))
        found = [c for role in SCORED_ROLES for c in chunks[role]]
        overall.append(share_found(found, all_evidence(flag)))
        if not flag["evidence"]["precedent"]:
            empty.append(float(not chunks["precedent"]))
        if flag["avoid"]:
            avoid.append(share_found(found, flag["avoid"]))
    return {
        "roles": {role: mean(roles[role]) for role in SCORED_ROLES},
        "overall": mean(overall),
        "empty_precedent": mean(empty),
        "avoid": mean(avoid),
    }


def per_flag(flags: list[dict], results: dict) -> dict:
    """Evidence found / expected per role; for no precedent, whether it was empty;
    trap passages returned / listed."""
    table = {}
    for flag in flags:
        chunks = cut(results[flag["id"]], MIN_SCORE)
        cells = {}
        for role in SCORED_ROLES:
            evidence = flag["evidence"][role]
            if evidence:
                found = sum(found_at(chunks[role], e) is not None for e in evidence)
                cells[role] = f"{found}/{len(evidence)}"
            elif role == "precedent":
                cells[role] = "empty" if not chunks[role] else "not empty"
            else:
                cells[role] = None
        if flag["avoid"]:
            found = [c for role in SCORED_ROLES for c in chunks[role]]
            returned = sum(found_at(found, e) is not None for e in flag["avoid"])
            cells["avoid"] = f"{returned}/{len(flag['avoid'])}"
        else:
            cells["avoid"] = None
        table[flag["id"]] = {"type": flag["type"], "trap": flag.get("trap"), **cells}
    return table


def by_role(flags: list[dict], retriever: Retriever) -> tuple[dict, dict]:
    results, latencies = {}, {}
    for topic in QUERIES:
        search = RedlineSearch(retriever, min_score=0.0, topic=topic)
        results[topic], latencies[topic] = {}, []
        for flag in flags:
            start = time.perf_counter()
            results[topic][flag["id"]] = search.search(flag["red_flag"])
            latencies[topic].append(time.perf_counter() - start)

    metrics = {
        "by_role": {
            QUERIES[topic]: role_scores(flags, results[topic], MIN_SCORE)
            | {"latency_p50_s": round(statistics.median(latencies[topic]), 2)}
            for topic in QUERIES
        },
        "thresholds": {
            f"{t:g}": role_scores(flags, results[True], t) for t in THRESHOLDS
        },
        "per_flag": per_flag(flags, results[True]),
    }
    hits = {
        f"by role / {QUERIES[topic]}": {
            flag_id: {
                role: [[hit.chunk.id, round(hit.score, 4)] for hit in role_hits]
                for role, role_hits in roles.items()
            }
            for flag_id, roles in results[topic].items()
        }
        for topic in QUERIES
    }
    return metrics, hits


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def run_info(name: str, note: str, flags: list[dict]) -> dict:
    return {
        "name": name,
        "note": note,
        "date": datetime.datetime.now().isoformat(timespec="seconds"),
        "commit": git("rev-parse", "--short", "HEAD"),
        "uncommitted_changes": bool(git("status", "--porcelain")),
        "flag_set": {"path": str(FLAGS.relative_to(ROOT)), "hash": file_hash(FLAGS)},
        "flags": len(flags),
        "evidence": sum(len(all_evidence(flag)) for flag in flags),
        "trap_flags": sum(bool(flag["avoid"]) for flag in flags),
        "chunks": {"path": str(CHUNKS.relative_to(ROOT)), "hash": file_hash(CHUNKS)},
        "embedding_model": EMBEDDING_MODEL,
        "reranker": retrieve.RERANKER,
        "parameters": {
            "top": TOP,
            "rrf_k": retrieve.RRF_K,
            "candidates": retrieve.CANDIDATES,
            "rerank_candidates_one_list": retrieve.RERANK_CANDIDATES,
            "rerank_candidates_by_role": redline_search.RERANK_CANDIDATES,
            "min_score": MIN_SCORE,
            "roles": {role.name: role.k for role in ROLES},
        },
    }


def fmt(value) -> str:
    return "–" if value is None else f"{value:.2f}"


def report(info: dict, metrics: dict) -> str:
    roles = " | ".join(SCORED_ROLES)
    one_list_rows = [
        f"| {name} | "
        + " | ".join(fmt(m[f"recall@{k}"]) for k in KS)
        + f" | **{fmt(m['mrr'])}** | "
        + " | ".join(fmt(m["roles"][role]) for role in SCORED_ROLES)
        + f" | {m['outdated_in_top5']} | {fmt(m['avoid'])} | {m['trap_first']} | "
        f"{m['latency_p50_s'] * 1000:.0f} ms |"
        for name, m in metrics["one_list"].items()
    ]
    role_rows = [
        f"| {name} | "
        + " | ".join(fmt(m["roles"][role]) for role in SCORED_ROLES)
        + f" | **{fmt(m['overall'])}** | {fmt(m['empty_precedent'])} | "
        f"{fmt(m['avoid'])} | {m['latency_p50_s']:.1f} s |"
        for name, m in metrics["by_role"].items()
    ]
    threshold_rows = [
        f"| {t} | "
        + " | ".join(fmt(m["roles"][role]) for role in SCORED_ROLES)
        + f" | {fmt(m['overall'])} | {fmt(m['empty_precedent'])} | {fmt(m['avoid'])} |"
        for t, m in metrics["thresholds"].items()
    ]
    flag_rows = [
        f"| {flag_id} | {row['type']} | {row['trap'] or '–'} | "
        + " | ".join(row[role] or "–" for role in SCORED_ROLES)
        + f" | {row['avoid'] or '–'} |"
        for flag_id, row in metrics["per_flag"].items()
    ]
    p = info["parameters"]
    return "\n".join(
        [
            f"# Retrieval evaluation: {info['name']}",
            "",
            f"{info['note']}" if info["note"] else "",
            "",
            (
                f"{info['date']}, commit `{info['commit']}`"
                + (" with uncommitted changes" if info["uncommitted_changes"] else "")
                + f". {info['flags']} red flags ({info['trap_flags']} with trap "
                f"passages), {info['evidence']} pieces of evidence "
                f"(`{info['flag_set']['path']}` {info['flag_set']['hash']}, chunks "
                f"{info['chunks']['hash']}). Recall is the share of a flag's evidence "
                "found, averaged over flags; for a role, over the flags with evidence "
                "for it."
            ),
            "",
            "## One list",
            "",
            (
                f"The clause and its type description as one query, top {p['top']}, "
                "documents in force unless marked otherwise. The role columns are "
                f"recall@{p['top']} of that role's evidence. Avoid: share of the trap "
                f"passages in the top {p['top']}; trap first: flags where a trap "
                "passage ranks above all the right evidence."
            ),
            "",
            (
                "| Config | recall@1 | recall@3 | recall@5 | recall@10 | MRR "
                f"| {roles} | Outdated chunks in top 5 | Avoid | Trap first "
                "| Latency p50 |"
            ),
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
            *one_list_rows,
            "",
            "## By role",
            "",
            (
                f"Hybrid search with reranking, k per role {p['roles']}, reranker "
                f"threshold {p['min_score']}. Empty precedent: the share of flags with "
                "no precedent whose precedent slot comes back empty. Avoid: share of "
                "the trap passages returned by any role (should be 0)."
            ),
            "",
            f"| Query | {roles} | Overall | Empty precedent | Avoid | Latency p50 |",
            "|---|---|---|---|---|---|---|---|---|",
            *role_rows,
            "",
            "## Reranker threshold",
            "",
            "Search by role with the type description, cut at each threshold.",
            "",
            f"| Threshold | {roles} | Overall | Empty precedent | Avoid |",
            "|---|---|---|---|---|---|---|---|",
            *threshold_rows,
            "",
            "## Each red flag, by role",
            "",
            (
                f"Evidence found / expected at threshold {p['min_score']}; for a flag "
                "with no precedent, whether the precedent slot came back empty; trap "
                "passages returned / listed."
            ),
            "",
            f"| Flag | Type | Trap | {roles} | Avoid |",
            "|---|---|---|---|---|---|---|---|",
            *flag_rows,
            "",
        ]
    )


def history() -> str:
    rows = []
    for run in sorted(p for p in OUT.iterdir() if (p / "metrics.json").exists()):
        info = json.loads((run / "run.json").read_text(encoding="utf-8"))
        metrics = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
        m = metrics["by_role"][QUERIES[True]]
        one = metrics["one_list"]["structural / hybrid_rerank"]
        rows.append(
            f"| [{run.name}]({run.name}/report.md) | {info['note']} | "
            f"{info['flag_set']['hash'][:8]} | {info['chunks']['hash'][:8]} | "
            f"`{info['commit']}`{'*' if info['uncommitted_changes'] else ''} | "
            + " | ".join(fmt(m["roles"][role]) for role in SCORED_ROLES)
            + f" | **{fmt(m['overall'])}** | {fmt(m['empty_precedent'])} | "
            f"{fmt(m.get('avoid'))} | {fmt(one[f'recall@{TOP}'])} | "
            f"{m['latency_p50_s']:.1f} s |"
        )
    return "\n".join(
        [
            "# Retrieval runs",
            "",
            (
                "One row per run of `scripts/eval_retrieval.py`, rebuilt from the run "
                "folders. Runs compare only with the same flag set and chunks hashes. "
                "Role columns: search by role with the type description; one list: "
                f"structural chunks, hybrid with reranking, recall@{TOP}. "
                "\\* uncommitted changes."
            ),
            "",
            (
                "| Run | Note | Flag set | Chunks | Commit | "
                + " | ".join(SCORED_ROLES)
                + " | Overall | Empty precedent | Avoid | One list | Latency p50 |"
            ),
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
            *rows,
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", required=True, help="short name of the run")
    parser.add_argument("--note", default="", help="what changed since the last run")
    args = parser.parse_args()
    folder = OUT / f"{datetime.date.today().isoformat()}_{args.name}"
    if folder.exists():
        raise SystemExit(f"{folder.relative_to(ROOT)} exists; choose another --name")

    flags = load_flags()
    info = run_info(args.name, args.note, flags)
    documents = [Document.load(p) for p in sorted(DOCUMENTS.glob("*.json"))]
    chunkings = {
        "structural": load_chunks(),
        "fixed": [c for document in documents for c in chunk_fixed(document)],
    }
    check_evidence(flags, chunkings)
    retrievers = {
        name: Retriever(chunks, collection=f"chunks_{name}")
        for name, chunks in chunkings.items()
    }

    list_metrics, hits = one_list(flags, retrievers)
    role_metrics, role_hits = by_role(flags, retrievers["structural"])
    metrics = {"one_list": list_metrics, **role_metrics}

    folder.mkdir(parents=True)
    for file, data in [
        ("run.json", info),
        ("metrics.json", metrics),
        ("hits.json", hits | role_hits),
    ]:
        (folder / file).write_text(
            json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    (folder / "report.md").write_text(report(info, metrics), encoding="utf-8")
    (OUT / "history.md").write_text(history(), encoding="utf-8")
    print(
        f"Wrote {folder.relative_to(ROOT)} and {(OUT / 'history.md').relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
