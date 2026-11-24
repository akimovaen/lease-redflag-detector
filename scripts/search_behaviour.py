"""How the agent uses the corpus search, from the traces of saved runs (no API calls).

    uv run python scripts/search_behaviour.py                    # the full runs
    uv run python scripts/search_behaviour.py --runs 2026-11-23_reviewed

The search is a tool the agent calls when it decides, with a query it writes (stage 3,
step 3.1). This measures how it decides: how often it searches, which source roles and
versions it asks for, and whether it searches again when the answer is not in what it
found, rather than out of habit.

A search asked for in the same step as the first one was chosen before its results were
seen; only a search in a later step can be a reaction to them, so the two are counted
apart. The tasks fall in two groups: those whose answer is in the corpus (`ANSWERED`,
with the point or minute that holds it) and those whose answer is not (`NO_ANSWER`: x07
has nothing on the subject, x08 has the rule but not the amount asked for). A later
search should follow in the second group, not in the first. Writes
results/agent/search_behaviour.md.
"""

import argparse
import json
import re
import statistics
import tomllib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results" / "agent" / "runs"
TASKS = ROOT / "evals" / "agent_tasks.toml"
OUT = ROOT / "results" / "agent" / "search_behaviour.md"

# Tasks whose answer is in the corpus, with the source that holds it (the facts in the
# header of evals/agent_tasks.toml): a point as the line it starts, so that a fragment
# that only refers to the point does not count; a minute by its number, which is in the
# document title. f21 and f22 ask q03's question with failures first. Update this when
# the expected answers change (step 3.2 moves q03, f21, f22 to the policy amendment).
ANSWERED = {
    "q03": r"(?m)^\s*10\.2\.?\s",
    "q04": r"(?m)^\s*4\.2\.?\s",
    "q05": r"(?m)^\s*2\.5\.?\s",
    "q06": r"№\s*3/2026",
    "f21": r"(?m)^\s*10\.2\.?\s",
    "f22": r"(?m)^\s*10\.2\.?\s",
}
# Tasks whose answer is not in the corpus: x07 nothing on pets, x08 insurance required
# by p. 9.5 but no amount.
NO_ANSWER = ["x07", "x08"]


def check_tasks(path: Path = TASKS) -> None:
    """The tasks named here exist in the task set: a renamed task fails loudly."""
    ids = {t["id"] for t in tomllib.loads(path.read_text(encoding="utf-8"))["task"]}
    if unknown := (set(ANSWERED) | set(NO_ANSWER)) - ids:
        raise SystemExit(f"not in {path.name}: {', '.join(sorted(unknown))}")


def full_runs() -> list[Path]:
    return [
        path.parent
        for path in sorted(RUNS.glob("*/run.json"))
        if not json.loads(path.read_text(encoding="utf-8"))["partial"]
    ]


def searches(trace: Path) -> list[dict]:
    """The successful searches of a task: step, query, role, versions, fragments."""
    found = []
    for line in trace.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event["kind"] != "tool" or event["name"] != "search_corpus":
            continue
        if event["is_error"]:
            continue
        found.append(
            {
                "step": event["step"],
                "query": event["args"].get("query", ""),
                "role": event["args"].get("role") or "any",
                "versions": event["args"].get("versions", "current"),
                "fragments": json.loads(event["content"])["fragments"],
                "latency_s": event["latency_s"],
            }
        )
    return found


def has(fragments: list[dict], pattern: str) -> bool:
    """Whether a fragment holds the source: in its document title (a minute's number),
    its section or its text."""
    return any(
        re.search(pattern, "\n".join((f["document"], f["section"], f["text"])))
        for f in fragments
    )


def analyse(runs: list[Path]) -> list[dict]:
    tasks = []
    for run in runs:
        lines = (run / "results.jsonl").read_text(encoding="utf-8").splitlines()
        results = {row["id"]: row for row in map(json.loads, lines)}
        for trace in sorted((run / "traces").glob("*.jsonl")):
            found = searches(trace)
            if not found:
                continue
            row = results[trace.stem]
            first_step = found[0]["step"]
            tasks.append(
                {
                    "run": run.name,
                    "task": trace.stem,
                    "searches": found,
                    "same_step": sum(s["step"] == first_step for s in found) - 1,
                    "later": sum(s["step"] > first_step for s in found),
                    "cost_usd": row["cost_usd"],
                    "latency_s": row["latency_s"],
                    "passed": row["passed"],
                }
            )
    return tasks


def table(header: list[str], rows: list[list]) -> list[str]:
    return [
        "| " + " | ".join(header) + " |",
        "|" + "---|" * len(header),
        *("| " + " | ".join(str(c) for c in row) + " |" for row in rows),
    ]


def queries(task: dict) -> str:
    return "; ".join(
        f"«{s['query']}» ({s['role']}, step {s['step']})" for s in task["searches"]
    )


def run_info(run: Path) -> list:
    info = json.loads((run / "run.json").read_text(encoding="utf-8"))
    return [run.name, info["prompt"], info["tasks"]["hash"], info["commit"]]


def report(runs: list[Path], tasks: list[dict]) -> str:
    lines = [
        "# How the agent uses the corpus search",
        "",
        (
            f"From the traces of {len(runs)} runs, {len(tasks)} task runs with at least "
            "one successful search. Written by `scripts/search_behaviour.py`; no API "
            "calls. Compare runs only of the same prompt and task set:"
        ),
        "",
        *table(["Run", "Prompt", "Tasks", "Commit"], [run_info(r) for r in runs]),
        "",
        "## How often it searches",
        "",
    ]
    by_count = Counter(len(t["searches"]) for t in tasks)
    lines += table(
        ["Searches in the task", "Task runs"],
        [[n, by_count[n]] for n in sorted(by_count)],
    )
    same = sum(t["same_step"] > 0 for t in tasks)
    later = sum(t["later"] > 0 for t in tasks)
    roles = Counter(s["role"] for t in tasks for s in t["searches"])
    versions = Counter(s["versions"] for t in tasks for s in t["searches"])
    lines += [
        "",
        (
            f"Task runs with a second search in the same step as the first (chosen "
            f"before seeing its results): {same}. With a search in a later step, after "
            f"seeing them: {later}."
        ),
        "",
        (
            "Source roles asked for: "
            + ", ".join(f"{r} {n}" for r, n in roles.most_common())
            + ". Versions: "
            + ", ".join(f"{v} {n}" for v, n in versions.most_common())
            + "."
        ),
        "",
        "## Does it search again when the answer is not there?",
        "",
    ]
    groups = [
        ("answer in the corpus", [t for t in tasks if t["task"] in ANSWERED]),
        ("no answer in the corpus", [t for t in tasks if t["task"] in NO_ANSWER]),
    ]
    lines += table(
        ["Tasks", "Task runs", "With a later search", "Searches (mean)", "Passed"],
        [
            [
                f"{label} ({', '.join(sorted({t['task'] for t in group}))})",
                len(group),
                sum(t["later"] > 0 for t in group),
                f"{statistics.mean(len(t['searches']) for t in group):.1f}",
                sum(t["passed"] for t in group),
            ]
            for label, group in groups
            if group
        ],
    )
    answered = groups[0][1]
    missed = [
        t
        for t in answered
        if not has(t["searches"][0]["fragments"], ANSWERED[t["task"]])
    ]
    found_later = [
        t
        for t in missed
        if has([f for s in t["searches"] for f in s["fragments"]], ANSWERED[t["task"]])
    ]
    lines += [
        "",
        (
            f"In the first group the first search returned the source in "
            f"{len(answered) - len(missed)} of {len(answered)} task runs"
            + (
                f"; in the other {len(missed)} another search of the task found it in "
                f"{len(found_later)}."
                if missed
                else "."
            )
        ),
        "",
        "Per task run:",
        "",
    ]
    lines += table(
        ["Run", "Task", "Searches", "Same step", "Later", "Queries", "Passed"],
        [
            [
                t["run"],
                t["task"],
                len(t["searches"]),
                t["same_step"],
                t["later"],
                queries(t),
                "yes" if t["passed"] else "no",
            ]
            for _, group in groups
            for t in group
        ],
    )
    lines += ["", "## What a search costs", ""]
    rows = []
    for n in sorted(by_count):
        group = [t for t in tasks if len(t["searches"]) == n]
        rows.append(
            [
                n,
                len(group),
                f"{statistics.mean(t['cost_usd'] for t in group):.4f}",
                f"{statistics.median(t['latency_s'] for t in group):.0f} s",
            ]
        )
    lines += table(["Searches", "Task runs", "Mean $ per task", "Latency p50"], rows)
    search_s = [s["latency_s"] for t in tasks for s in t["searches"]]
    lines += [
        "",
        (
            "The rows hold different tasks: those without an answer search more and "
            "also write longer answers, so the table does not give the price of one "
            f"search. A search itself takes {statistics.median(search_s):.1f} s "
            "(median); one in a later step also adds a model call."
        ),
        "",
        (
            f"Few cases ({sum(len(g) for _, g in groups)} task runs in the two groups), "
            "so this describes the behaviour; it is not a statistical result."
        ),
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--runs", nargs="+", help="run folders (default: the full runs)"
    )
    args = parser.parse_args()
    check_tasks()
    runs = [RUNS / name for name in args.runs] if args.runs else full_runs()
    OUT.write_text(report(runs, analyse(runs)), encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)} written from {len(runs)} runs")


if __name__ == "__main__":
    main()
