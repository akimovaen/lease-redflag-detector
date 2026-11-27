"""Sum up the final runs of the agent tasks and compare them with step 1.6 (no API calls).

    uv run python scripts/summarize_agent_runs.py

The final runs (`FINAL`) are the whole reviewed task set on the production prompt;
the baseline (`BASELINE`) is the task set of step 1.6 on prompt agent/v2. Both are
read from their saved folders in results/agent/runs/, so every number here can be
counted again. The comparison takes the tasks both sets hold and names those whose
definition changed between the two task sets (read from git at `BASELINE_TASKS`): a
changed check can move a result as much as a changed prompt. Writes
results/agent/final_summary.md.
"""

import json
import statistics
import subprocess
import tomllib
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results" / "agent" / "runs"
OUT = ROOT / "results" / "agent" / "final_summary.md"
TASKS = ROOT / "evals" / "agent_tasks.toml"

FINAL = ["2026-11-27_final-v5", "2026-11-27_final-v5-r2", "2026-11-27_final-v5-r3"]
BASELINE = ["2026-11-23_reviewed", "2026-11-23_reviewed-r2", "2026-11-23_reviewed-r3"]
# The commit whose task set the baseline ran (its hash is in the runs' run.json).
BASELINE_TASKS = "141eb83"
# Failures where the agent did right and the check missed it; the lawyer widened
# these checks after the final runs (step 3.8).
CHECK_MISSES = {
    ("2026-11-27_final-v5-r3", "l10"): 'the agent asked "який із них"',
    (
        "2026-11-27_final-v5-r3",
        "c13",
    ): 'the agent offered to "надіслати" it to the committee',
}
ANSWER_CHARS = 600


def rows(name: str) -> list[dict]:
    return [json.loads(line) for line in (RUNS / name / "results.jsonl").open()]


def run_json(name: str) -> dict:
    return json.loads((RUNS / name / "run.json").read_text())


def p95(values: list[float]) -> float:
    return statistics.quantiles(values, n=20)[-1]


def totals(names: list[str], ids: set[str] | None = None) -> list[list]:
    table = []
    for name in names:
        got = [r for r in rows(name) if ids is None or r["id"] in ids]
        with_tools = [r for r in got if r["tools_ok"] is not None]
        latency = [r["latency_s"] for r in got]
        cost = sum(r["cost_usd"] for r in got)
        table.append(
            [
                name,
                run_json(name)["prompt"],
                f"{sum(r['passed'] for r in got)} / {len(got)}",
                f"{sum(r['tools_ok'] for r in with_tools) / len(with_tools):.2f}",
                sum(r["unauthorized"] for r in got),
                f"{statistics.mean(r['steps'] for r in got):.1f}",
                f"{1000 * cost / len(got):.2f}",
                f"{statistics.median(latency):.0f} s",
                f"{p95(latency):.0f} s",
            ]
        )
    return table


def table(head: list[str], body: list[list]) -> list[str]:
    return [
        "| " + " | ".join(head) + " |",
        "|" + "---|" * len(head),
        *("| " + " | ".join(str(c) for c in row) + " |" for row in body),
    ]


def changed_tasks(ids: set[str]) -> list[str]:
    old = subprocess.run(
        ["git", "show", f"{BASELINE_TASKS}:evals/agent_tasks.toml"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    before = {t["id"]: t for t in tomllib.loads(old)["task"]}
    now = {t["id"]: t for t in tomllib.loads(TASKS.read_text())["task"]}
    return sorted(i for i in ids if before[i] != now[i])


def main() -> None:
    head = ["Run", "Prompt", "Passed", "Tool choice right", "Without permission",
            "Steps (mean)", "$ per 1000", "Latency p50", "Latency p95"]  # fmt: skip
    final = {name: rows(name) for name in FINAL}
    n_runs = len(FINAL)
    lines = [
        "# The agent tasks: final runs",
        "",
        "Counted by `scripts/summarize_agent_runs.py` from saved runs; no API calls.",
        (
            f"Final runs: the whole task set ({len(final[FINAL[0]])} tasks, reviewed by the "
            f"lawyer on 2026-11-27) on prompt `{run_json(FINAL[0])['prompt']}`, "
            f"{n_runs} runs."
        ),
        "",
        "## Totals",
        "",
        *table(head, totals(FINAL)),
        "",
        (
            "Tool choice right counts the tasks that check tools. Without permission counts "
            "approval requests created without the lawyer's yes. $ per 1000 is the cost of "
            "1000 such requests."
        ),
        "",
        "## By group",
        "",
    ]
    by_group: dict[str, list[dict]] = defaultdict(list)
    for got in final.values():
        for r in got:
            by_group[r["group"]].append(r)
    body = []
    for group, got in sorted(by_group.items(), key=lambda kv: -len(kv[1])):
        failed = Counter(r["id"] for r in got if not r["passed"])
        body.append(
            [
                group,
                len(got) // n_runs,
                f"{sum(r['passed'] for r in got)} / {len(got)}",
                ", ".join(f"{i} ×{n}" for i, n in sorted(failed.items())),
            ]
        )
    lines += table(["Group", "Tasks", "Passed (all runs)", "Failed"], body)

    tools = Counter(t for got in final.values() for r in got for t in set(r["tools"]))
    lines += [
        "",
        "## Tools",
        "",
        f"Tasks that called each tool, over the {n_runs} runs:",
        "",
        *table(["Tool", "Tasks"], sorted(tools.items(), key=lambda kv: -kv[1])),
        "",
        "## Failures",
        "",
    ]
    for name, got in final.items():
        for r in got:
            if r["passed"]:
                continue
            miss = CHECK_MISSES.get((name, r["id"]))
            kind = f"check miss: {miss}" if miss else "the agent's failure"
            answer = r["answer"][:ANSWER_CHARS].replace("\n", " ")
            lines += [
                f"### {r['id']} ({r['group']}), {name}: {kind}",
                "",
                f"Question: «{r['question']}»",
                "",
                "Failed: " + "; ".join(f"`{f}`" for f in r["failed"]),
                "",
                f"Tools: {', '.join(r['tools']) or 'none'}",
                "",
                f"> {answer}{'…' if len(r['answer']) > ANSWER_CHARS else ''}",
                "",
            ]

    common = {r["id"] for r in rows(BASELINE[0])} & {r["id"] for r in rows(FINAL[0])}
    changed = changed_tasks(common)
    widened = " and ".join(sorted({task for _, task in CHECK_MISSES}))
    lines += [
        f"## Against step 1.6 on the {len(common)} tasks both sets hold",
        "",
        *table(head, totals(BASELINE, common) + totals(FINAL, common)),
        "",
        (
            f"Changed between the baseline task set ({BASELINE_TASKS}) and the current "
            f"evals/agent_tasks.toml: {', '.join(changed) or 'none'} (its header says "
            f"why). Of these, {widened} were widened after the final runs, which still "
            "had the narrower checks. The final runs also have tools the baseline had "
            "not: the lawyer's notes (recall_notes), and the registry is an MCP server."
        ),
    ]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)} written")


if __name__ == "__main__":
    main()
