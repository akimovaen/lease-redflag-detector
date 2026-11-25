"""Count what the agent says in its answers, across saved runs (no API calls).

    uv run python scripts/count_phrases.py

Some behaviours are not checks of a task but are counted for the report, from the
answers of saved runs: a check that would fail a task on them was not wanted. Each
count names its tasks, its pattern and its runs (`COUNTS`), so that the number in the
report comes from a file and can be counted again. Writes
results/agent/phrase_counts.md.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results" / "agent" / "runs"
OUT = ROOT / "results" / "agent" / "phrase_counts.md"


def runs(name: str) -> list[str]:
    """A run and its repeats: name, name-r2, name-r3, …"""
    return sorted(
        p.name
        for p in RUNS.glob(f"{name}*")
        if re.fullmatch(rf"{name}(-r\d+)?", p.name)
    )


COUNTS = [
    {
        "what": (
            "After a denial the agent offers what it cannot do: to read the lease once "
            "the lawyer confirms being the head of legal or the litigation team "
            "(step 3.7; the lawyer judged it a prompt fix, not a failure of the task)"
        ),
        "tasks": ["a26", "a31", "a34"],
        "pattern": r"підтверд\w*[^.]{0,60}(керівник|судов)|якщо ви (керівник|належите|з судов)",
        "groups": {
            "agent/v3": runs("2026-11-25_prompt-v3"),
            "agent/v4": runs("2026-11-25_prompt-v4"),
        },
    },
    {
        "what": (
            "Asked who approves 7 % for an anchor tenant, the agent names the clause "
            "library's discrepancy (Ф-2.3 still names the general director; step 3.4, "
            "counted, not required)"
        ),
        "tasks": ["v42"],
        "pattern": r"Ф-2\.3|[Бб]ібліотек",
        "groups": {"agent/v3": runs("2026-11-24_versions")},
    },
]


def count(spec: dict) -> list[list]:
    rows = []
    pattern = re.compile(spec["pattern"], re.IGNORECASE)
    for group, names in spec["groups"].items():
        answers = [
            row
            for name in names
            for row in map(json.loads, (RUNS / name / "results.jsonl").open())
            if row["id"] in spec["tasks"]
        ]
        found = [row["id"] for row in answers if pattern.search(row["answer"])]
        rows.append(
            [group, ", ".join(names), len(found), len(answers), ", ".join(found)]
        )
    return rows


def main() -> None:
    lines = [
        "# Phrases in the agent's answers",
        "",
        "Counted by `scripts/count_phrases.py` from saved runs; no API calls.",
    ]
    for spec in COUNTS:
        lines += [
            "",
            f"## {spec['what']}",
            "",
            f"Tasks {', '.join(spec['tasks'])}; pattern `{spec['pattern']}`.",
            "",
            "| Prompt | Runs | Answers with it | Answers | Tasks |",
            "|---|---|---|---|---|",
        ]
        lines += [
            "| " + " | ".join(str(cell) for cell in row) + " |" for row in count(spec)
        ]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)} written")


if __name__ == "__main__":
    main()
