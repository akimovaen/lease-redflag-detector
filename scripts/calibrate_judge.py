"""Agreement of the answer judge with the lawyer's grades in evals/judge_calibration.toml.

    uv run python scripts/calibrate_judge.py

For the key facts and for the changed clause: the share of exact agreement, Cohen's
kappa (agreement beyond chance), and the confusion matrix (rows: lawyer, columns:
judge). Writes results/rag/judge_calibration.md.
"""

import json
import tomllib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORM = ROOT / "evals" / "judge_calibration.toml"
OUT = ROOT / "results" / "rag" / "judge_calibration.md"
FACT_GRADES = ["present", "partial", "missing"]
CLAUSE_GRADES = ["good", "minor_edits", "wrong", "missing", "not_needed"]


def kappa(pairs: list[tuple[str, str]], labels: list[str]) -> float | None:
    n = len(pairs)
    observed = sum(a == b for a, b in pairs) / n
    lawyer = Counter(a for a, _ in pairs)
    judge = Counter(b for _, b in pairs)
    expected = sum(lawyer[label] * judge[label] for label in labels) / n**2
    return None if expected == 1 else (observed - expected) / (1 - expected)


def table(name: str, pairs: list[tuple[str, str]], labels: list[str]) -> list[str]:
    labels = [label for label in labels if any(label in pair for pair in pairs)]
    counts = Counter(pairs)
    agreement = sum(a == b for a, b in pairs) / len(pairs)
    k = kappa(pairs, labels)
    return [
        f"## {name}",
        "",
        f"{len(pairs)} grades, exact agreement {agreement:.2f}, Cohen's kappa "
        + ("–" if k is None else f"{k:.2f}")
        + ".",
        "",
        "| Lawyer \\ judge | " + " | ".join(labels) + " |",
        "|---|" + "---|" * len(labels),
        *[
            f"| {a} | " + " | ".join(str(counts[(a, b)]) for b in labels) + " |"
            for a in labels
        ],
        "",
    ]


def main() -> None:
    form = tomllib.loads(FORM.read_text(encoding="utf-8"))
    folder = ROOT / "results" / "rag" / "generation" / form["run"]
    judged = {
        line["id"]: line
        for line in map(
            json.loads,
            (folder / "judge.jsonl").read_text(encoding="utf-8").splitlines(),
        )
    }
    facts, clauses, disagreements = [], [], []
    for answer in form["answer"]:
        judge = judged[answer["id"]]
        if "facts" not in judge:
            raise SystemExit(f"{answer['id']}: the run has no judgment for this answer")
        if not answer["clause"] or any(not f["grade"] for f in answer["facts"]):
            raise SystemExit(f"{answer['id']}: not every grade is filled in")
        for number, (fact, verdict) in enumerate(
            zip(answer["facts"], judge["facts"], strict=True), 1
        ):
            facts.append((fact["grade"], verdict["grade"]))
            if fact["grade"] != verdict["grade"]:
                disagreements.append(
                    f"| {answer['id']} | fact {number}: {fact['fact']} | "
                    f"{fact['grade']} | {verdict['grade']} | {verdict['reason']} |"
                )
        clauses.append((answer["clause"], judge["clause"]))
        if answer["clause"] != judge["clause"]:
            disagreements.append(
                f"| {answer['id']} | changed clause | {answer['clause']} | "
                f"{judge['clause']} | {judge['clause_reason']} |"
            )
    lines = [
        "# Judge calibration",
        "",
        (
            f"The answer judge (`prompts/judge/answer_v1.md`) against the lawyer's "
            f"grades of {len(form['answer'])} answers of `{form['run']}` "
            f"(`{FORM.relative_to(ROOT)}`)."
        ),
        "",
        *table("Key facts", facts, FACT_GRADES),
        *table("Changed clause", clauses, CLAUSE_GRADES),
        "## Disagreements",
        "",
        "| Flag | What | Lawyer | Judge | Judge's reason |",
        "|---|---|---|---|---|",
        *disagreements,
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:12]))


if __name__ == "__main__":
    main()
