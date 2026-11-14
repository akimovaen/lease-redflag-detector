"""Score generation runs against the expected answers in evals/redline_expected.toml.

    uv run python scripts/eval_redline.py                    # every run
    uv run python scripts/eval_redline.py 2026-11-11_haiku-v3

Deterministic scores, per red flag and averaged over the run:

- valid: the answer passed validation (sources in the context, a changed clause
  exactly when the verdict needs one);
- verdict and risk: equal to the expected ones;
- cite: share of the expected documents among the documents the answer cites;
- gaps: the answer names points the sources do not settle exactly when expected.

Routing, over the run: an answer with any gap is shown to the lawyer as needing a
decision (`needs_decision` in the run report), whatever its verdict. The model does
not have to choose between a verdict and not_covered; the code refers every point it
names as open.

- referred: share of the flags with expected gaps that were referred;
- no_answer: share of the flags expected not_covered that were referred, the "I don't
  know" of generation;
- referred_extra: share of the other flags that were referred (lower is better).

Scoring is separate from generation, so every run is rescored when the expected
answers change. Each run folder gets scores.json and scores.md, and
results/rag/generation/history.md compares the full runs. Runs on different flag sets
are marked by the hash of the flag set.
"""

import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = ROOT / "evals" / "redline_expected.toml"
OUT = ROOT / "results" / "rag" / "generation"
SCORES = ("valid", "verdict", "risk", "cite", "gaps")
ROUTING = ("referred", "no_answer", "referred_extra")
# Averages of the LLM judges (scripts/judge_redline.py), if the run was judged.
JUDGED = ("facts", "clause", "faithfulness")


def load_expected() -> dict[str, dict]:
    answers = tomllib.loads(EXPECTED.read_text(encoding="utf-8"))["answer"]
    return {answer["id"]: answer for answer in answers}


def cited_documents(row: dict) -> set[str]:
    """Documents of every source the answer cites."""
    output = row["output"]
    documents = {s["id"]: s["chunk"].split("#")[0] for s in row["sources"]}
    claims = output["findings"] + output["conflicts"] + [output["risk_reason"]]
    ids = {s for claim in claims for s in claim["sources"]}
    ids |= set(output["proposed_sources"])
    return {documents[i] for i in ids if i in documents}


def score(row: dict, expected: dict) -> dict:
    output = row["output"]
    if not output:
        return {"valid": 0.0, "verdict": 0.0, "risk": 0.0, "cite": 0.0, "gaps": 0.0}
    cited = cited_documents(row)
    return {
        "valid": 1.0,
        "verdict": float(output["verdict"] == expected["verdict"]),
        "risk": float(output["risk"] == expected["risk"]),
        "cite": sum(doc in cited for doc in expected["cite"]) / len(expected["cite"]),
        "gaps": float(bool(output["gaps"]) == expected["gaps"]),
    }


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def fmt(value: float | None) -> str:
    return "–" if value is None else f"{value:.2f}"


def score_run(folder: Path, expected: dict[str, dict]) -> dict:
    rows = [
        json.loads(line)
        for line in (folder / "outputs.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    per_flag = {}
    for row in rows:
        answer = expected[row["id"]]
        per_flag[row["id"]] = score(row, answer) | {
            "got": (
                f"{row['output']['verdict']} / {row['output']['risk']}"
                if row["output"]
                else "failed"
            ),
            "expected": f"{answer['verdict']} / {answer['risk']}",
        }
    totals = {name: mean([s[name] for s in per_flag.values()]) for name in SCORES}
    return {"totals": totals | routing(rows, expected), "per_flag": per_flag}


def routing(rows: list[dict], expected: dict[str, dict]) -> dict[str, float | None]:
    referred = {
        row["id"]: bool(row["output"] and row["output"]["gaps"]) for row in rows
    }

    def share(ids: list[str]) -> float | None:
        return mean([float(referred[i]) for i in ids]) if ids else None

    return {
        "referred": share([i for i in referred if expected[i]["gaps"]]),
        "no_answer": share(
            [i for i in referred if expected[i]["verdict"] == "not_covered"]
        ),
        "referred_extra": share([i for i in referred if not expected[i]["gaps"]]),
    }


def scores_md(info: dict, scores: dict) -> str:
    rows = [
        f"| {flag_id} | {s['got']} | {s['expected']} | "
        + " | ".join(fmt(s[name]) for name in SCORES)
        + " |"
        for flag_id, s in scores["per_flag"].items()
    ]
    return "\n".join(
        [
            f"# Scores: {info['name']}",
            "",
            (
                f"Expected answers `{EXPECTED.relative_to(ROOT)}`. "
                + " · ".join(
                    f"{name} {fmt(value)}" for name, value in scores["totals"].items()
                )
            ),
            "",
            "| Flag | Verdict / risk | Expected | " + " | ".join(SCORES) + " |",
            "|---|---|---|" + "---|" * len(SCORES),
            *rows,
            "",
        ]
    )


def judged(folder: Path) -> str:
    """The judges' averages of a run, or dashes if it was not judged."""
    path = folder / "judge.json"
    if not path.exists():
        return "– | – | –"
    totals = json.loads(path.read_text(encoding="utf-8"))
    return " | ".join(fmt(totals[name]) for name in JUDGED)


def history(runs: list[tuple[dict, dict]]) -> str:
    rows = [
        f"| [{info['folder']}]({info['folder']}/report.md) | {info['note']} | "
        f"{info['model']} | `{info['prompt']}` | {info['flag_set']['hash'][:8]} | "
        + " | ".join(fmt(scores["totals"][name]) for name in SCORES + ROUTING)
        + f" | {judged(OUT / info['folder'])}"
        + f" | {info['cost_per_1000_usd']:.2f} | {info['latency_p50_s']:.0f} s |"
        for info, scores in runs
    ]
    return "\n".join(
        [
            "# Generation runs",
            "",
            (
                "One row per full run of `scripts/run_redline.py`, scored by "
                "`scripts/eval_redline.py` against the current expected answers; "
                "facts, clause and faithfulness from the LLM judges "
                "(`scripts/judge_redline.py`). Routing: referred, no_answer and "
                "referred_extra, the shares of flags an answer with gaps sends to "
                "the lawyer (see the script). Runs compare only on the same flag "
                "set (its hash)."
            ),
            "",
            "| Run | Note | Model | Prompt | Flag set | "
            + " | ".join(SCORES + ROUTING)
            + " | "
            + " | ".join(JUDGED)
            + " | $ / 1000 | Latency p50 |",
            "|---|---|---|---|---|"
            + "---|" * (len(SCORES) + len(ROUTING) + len(JUDGED))
            + "---|---|",
            *rows,
            "",
        ]
    )


def main() -> None:
    expected = load_expected()
    names = sys.argv[1:]
    folders = sorted(p for p in OUT.iterdir() if (p / "outputs.jsonl").exists())
    runs = []
    for folder in folders:
        info = json.loads((folder / "run.json").read_text(encoding="utf-8"))
        info["folder"] = folder.name
        scores = score_run(folder, expected)
        if not names or folder.name in names:
            (folder / "scores.json").write_text(
                json.dumps(scores, ensure_ascii=False, indent=1), encoding="utf-8"
            )
            (folder / "scores.md").write_text(scores_md(info, scores), encoding="utf-8")
            print(folder.name, scores["totals"])
        if not info["partial"]:
            runs.append((info, scores))
    runs.sort(key=lambda item: item[0]["date"])
    (OUT / "history.md").write_text(history(runs), encoding="utf-8")


if __name__ == "__main__":
    main()
