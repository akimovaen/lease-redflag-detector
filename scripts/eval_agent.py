"""Run the agent on the tasks of evals/agent_tasks.toml and check every outcome.

    uv run python scripts/eval_agent.py --name first --note "what changed"
    make agent-evals NAME=first [ONLY="n01 q03"] [REPEAT=3]

Every task runs with a fresh approval queue, its own scripted answers to confirmation
questions and its own injected faults, so that tasks do not affect each other. A task
is a conversation (`agent/chat.py`): its question, then its follow-ups, if any; the
checks read the last answer and the trace of every question. The
checks are deterministic (`agent/evaluate.py`). Each run goes to its own folder,
results/agent/runs/<date>_<name>/, and is never overwritten:

- run.json: what was run (commit, config, prompts, hash of the task set) and the
  metrics: tasks passed, tool choice right, actions without permission, steps, cost
  (also per 1000 requests) and latency;
- results.jsonl: one line per task with every check;
- traces/<task>.jsonl: the trace of each task;
- report.md: the tables of this run.

With --repeat N the runs are <name>, <name>-r2, …, since results vary between runs.
results/agent/runs/history.md compares all full runs.
"""

import argparse
import datetime
import hashlib
import json
import os
import statistics
import subprocess
import sys
import tempfile
import threading
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "evals" / "agent_tasks.toml"
CONFIG = ROOT / "configs" / "agent-haiku-v2.toml"
OUT = ROOT / "results" / "agent" / "runs"


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def load_tasks() -> list[dict]:
    return tomllib.loads(TASKS.read_text(encoding="utf-8"))["task"]


def seed_notes(store, notes: list[dict]):
    """The notes a task starts with: written by `author` (lawyer by default) under
    the policy in force, or under the policy before Amendment 1 (`policy = "previous"`)."""
    from lease_redflag_detector.agent.memory import policy_version
    from lease_redflag_detector.agent.users import get_user

    for note in notes:
        author = get_user(note.get("author", "lawyer"))
        version = (
            "policy_2026" if note.get("policy") == "previous" else policy_version()
        )
        store.add(
            note["text"],
            author.id,
            author.entity,
            version,
            note.get("lease_id"),
            note.get("topic"),
        )
    return store


def run_task(task: dict, config, registries, retriever, folder: Path) -> dict:
    """`registries`: the registry client of a user, by user id."""
    from lease_redflag_detector.agent.chat import ModelSummarizer, Session
    from lease_redflag_detector.agent.confirm import ScriptedConfirmer
    from lease_redflag_detector.agent.evaluate import (
        Outcome,
        check,
        tools_ok,
        unauthorized,
    )
    from lease_redflag_detector.agent.faults import FaultyToolbox
    from lease_redflag_detector.agent.loop import Agent
    from lease_redflag_detector.agent.memory import NoteStore
    from lease_redflag_detector.agent.queue import ApprovalQueue
    from lease_redflag_detector.agent.toolset import build_toolbox

    record = {
        "id": task["id"],
        "group": task["group"],
        "user": task.get("user", config.user),
        "question": task["question"],
    }
    with tempfile.TemporaryDirectory() as tmp:
        queue = ApprovalQueue(Path(tmp) / "queue.db")
        memory = seed_notes(NoteStore(Path(tmp) / "memory.db"), task.get("notes", []))
        confirm = ScriptedConfirmer(*task.get("confirm", []))
        task_config = config.model_copy(deep=True)
        task_config.user = task.get("user", config.user)
        for name, value in task.get("limits", {}).items():
            setattr(task_config.limits, name, value)
        try:
            tools = build_toolbox(
                task_config,
                registry=registries(task_config.user),
                retriever=retriever,
                warm=False,
                queue=queue,
                confirm=confirm,
                session=True,
                memory=memory,
            )
            if task.get("faults"):
                tools = FaultyToolbox(tools, task["faults"])
            # A task is a conversation: its question, then its follow-ups, if any.
            session = Session(
                Agent.from_config(task_config, tools),
                ModelSummarizer(task_config),
                folder / "traces" / f"{task['id']}.jsonl",
            )
            answers = [
                session.ask(q) for q in [task["question"], *task.get("follow_up", [])]
            ]
            answer = answers[-1]
        except Exception as e:  # noqa: BLE001 - one broken task must not end the run
            # What it did before it broke still counts toward actions without permission.
            left = Outcome(
                "",
                "",
                [],
                queue.all(),
                confirm.asked,
                confirm.given.count(True),
                [n.as_dict() for n in memory.all()],
                len(task.get("notes", [])),
            )
            return record | {
                "passed": False,
                "error": f"{type(e).__name__}: {e}",
                "unauthorized": unauthorized(left),
            }
        outcome = Outcome(
            answer.text,
            answer.stop_reason,
            session.events,
            queue.all(),
            confirm.asked,
            confirm.given.count(True),
            [n.as_dict() for n in memory.all()],
            len(task.get("notes", [])),
        )
        checks = check(task, outcome)
    failed = [c for c in checks if not c.passed]
    return record | {
        "passed": not failed,
        "failed": [f"{c.name}: {c.detail}" for c in failed],
        "checks": len(checks),
        "tools_ok": tools_ok(checks),
        "unauthorized": sum(c.kind == "permission" and not c.passed for c in checks),
        "stop_reason": str(answer.stop_reason),
        "steps": sum(a.steps for a in answers),
        "cost_usd": round(session.cost_usd, 6),
        "latency_s": round(sum(a.latency_s for a in answers), 1),
        "tools": outcome.called(),
        "answer": answer.text,
        **({"answers": [a.text for a in answers]} if len(answers) > 1 else {}),
    }


def totals(rows: list[dict]) -> dict:
    done = [r for r in rows if "error" not in r]
    with_tools = [r for r in done if r["tools_ok"] is not None]
    mean_cost = statistics.mean(r["cost_usd"] for r in done) if done else 0.0
    return {
        "tasks": len(rows),
        "passed": sum(r["passed"] for r in rows),
        "pass_rate": sum(r["passed"] for r in rows) / len(rows),
        "tools_ok_rate": (
            sum(r["tools_ok"] for r in with_tools) / len(with_tools)
            if with_tools
            else None
        ),
        "unauthorized": sum(r.get("unauthorized", 0) for r in rows),
        "errors": len(rows) - len(done),
        "steps_mean": statistics.mean(r["steps"] for r in done) if done else None,
        "cost_usd": sum(r["cost_usd"] for r in done),
        "cost_mean_usd": mean_cost,
        "cost_per_1000_usd": 1000 * mean_cost,
        "latency_p50_s": statistics.median(r["latency_s"] for r in done)
        if done
        else None,
    }


def report(info: dict, rows: list[dict]) -> str:
    t = info["totals"]
    tools_rate = "–" if t["tools_ok_rate"] is None else f"{t['tools_ok_rate']:.2f}"
    lines = [
        f"# Agent tasks: {info['name']}",
        "",
        info["note"],
        "",
        f"{info['date']}, commit `{info['commit']}`"
        + (" with uncommitted changes" if info["uncommitted_changes"] else "")
        + f". {info['model']}, prompt `{info['prompt']}`, tasks `{info['tasks']['hash']}`.",
        "",
        (
            "| Passed | Tool choice right | Actions without permission | Steps (mean) "
            "| $ per task | $ per 1000 | Latency p50 |"
        ),
        "|---|---|---|---|---|---|---|",
        (
            f"| {t['passed']} / {t['tasks']} ({t['pass_rate']:.2f}) | {tools_rate} | "
            f"{t['unauthorized']} | {t['steps_mean'] or 0:.1f} | "
            f"{t['cost_mean_usd']:.4f} | {t['cost_per_1000_usd']:.2f} | "
            f"{t['latency_p50_s'] or 0:.0f} s |"
        ),
        "",
        "| Task | Group | User | Result | Stop | Steps | $ | Tools | Failed checks |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        if "error" in r:
            lines.append(
                f"| {r['id']} | {r['group']} | {r.get('user', '')} | error | | | | | "
                f"{r['error']} |"
            )
            continue
        failed = "<br>".join(r["failed"]).replace("|", "\\|")
        tools = ", ".join(r["tools"]) or "–"
        lines.append(
            f"| {r['id']} | {r['group']} | {r.get('user', '')} | "
            f"{'pass' if r['passed'] else 'FAIL'} | "
            f"{r['stop_reason']} | {r['steps']} | {r['cost_usd']:.4f} | {tools} | "
            f"{failed} |"
        )
    failures = [r for r in rows if not r["passed"] and "answer" in r]
    if failures:
        lines += ["", "## Answers of failed tasks", ""]
        for r in failures:
            lines += [f"### {r['id']}: {r['question']}", "", r["answer"], ""]
    return "\n".join(lines) + "\n"


def history() -> str:
    lines = [
        "# Agent task runs",
        "",
        (
            "One row per full run of `scripts/eval_agent.py`. Runs compare only on "
            "the same task set (its hash)."
        ),
        "",
        (
            "| Run | Note | Tasks | Passed | Tool choice | Without permission | Steps "
            "| $ per 1000 | Latency p50 |"
        ),
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for path in sorted(OUT.glob("*/run.json")):
        info = json.loads(path.read_text(encoding="utf-8"))
        if info["partial"]:
            continue
        t = info["totals"]
        tools_rate = "–" if t["tools_ok_rate"] is None else f"{t['tools_ok_rate']:.2f}"
        lines.append(
            f"| [{path.parent.name}]({path.parent.name}/report.md) | {info['note']} | "
            f"{info['tasks']['hash']} | {t['pass_rate']:.2f} | {tools_rate} | "
            f"{t['unauthorized']} | {t['steps_mean'] or 0:.1f} | "
            f"{t['cost_per_1000_usd']:.2f} | {t['latency_p50_s'] or 0:.0f} s |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", required=True)
    parser.add_argument("--note", default="")
    parser.add_argument("--only", nargs="+", help="task ids to run")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--workers", type=int, default=4, help="tasks run at once")
    parser.add_argument("--config", type=Path, default=CONFIG)
    args = parser.parse_args()
    os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    load_dotenv(ROOT / ".env")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is not set: add it to .env")

    from lease_redflag_detector.agent.loop import AgentConfig
    from lease_redflag_detector.agent.registry_client import RegistryClient
    from lease_redflag_detector.agent.toolset import LOCAL_RERANK
    from lease_redflag_detector.agent.users import get_user
    from lease_redflag_detector.rag.retrieve import RerankScores, Retriever, load_chunks

    tasks = load_tasks()
    if args.only:
        if unknown := set(args.only) - {t["id"] for t in tasks}:
            raise SystemExit(f"No such tasks: {', '.join(sorted(unknown))}")
        tasks = [t for t in tasks if t["id"] in args.only]
    names = [args.name] + [f"{args.name}-r{i}" for i in range(2, args.repeat + 1)]
    date = datetime.date.today().isoformat()
    folders = [OUT / f"{date}_{name}" for name in names]
    if existing := [f for f in folders if f.exists()]:
        raise SystemExit(
            f"{existing[0].relative_to(ROOT)} exists; choose another --name"
        )

    config = AgentConfig.load(args.config)
    # One registry server per user, shared by the tasks of that user.
    clients: dict[str, RegistryClient] = {}
    lock = threading.Lock()

    def registries(user: str) -> RegistryClient:
        with lock:
            if user not in clients:
                clients[user] = RegistryClient(user=get_user(user).id)
            return clients[user]

    print("Loading the search models…", file=sys.stderr)
    retriever = Retriever(
        load_chunks(),
        collection="agent",
        qdrant_path=None,
        reranker=RerankScores(local_dir=LOCAL_RERANK),
    )
    retriever.search("орендна плата", k=1)

    for name, folder in zip(names, folders, strict=True):
        (folder / "traces").mkdir(parents=True)

        def run(task: dict, folder: Path = folder) -> dict:
            row = run_task(task, config, registries, retriever, folder)
            mark = "pass" if row["passed"] else "FAIL"
            print(f"{row['id']} {mark} {'; '.join(row.get('failed', []))}"[:200],
                  file=sys.stderr)  # fmt: skip
            return row

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            rows = list(pool.map(run, tasks))
        info = {
            "name": name,
            "note": args.note,
            "date": datetime.datetime.now().isoformat(timespec="seconds"),
            "commit": git("rev-parse", "--short", "HEAD"),
            "uncommitted_changes": bool(git("status", "--porcelain")),
            "config": config.model_dump(),
            "model": config.model,
            "prompt": config.prompt,
            "partial": bool(args.only),
            "tasks": {
                "path": str(TASKS.relative_to(ROOT)),
                "hash": hashlib.sha256(TASKS.read_bytes()).hexdigest()[:12],
                "ids": [t["id"] for t in tasks],
            },
            "totals": totals(rows),
        }
        (folder / "run.json").write_text(
            json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        (folder / "results.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
            encoding="utf-8",
        )
        (folder / "report.md").write_text(report(info, rows), encoding="utf-8")
        t = info["totals"]
        print(
            f"{folder.relative_to(ROOT)}: {t['passed']}/{t['tasks']} passed, "
            f"{t['unauthorized']} without permission, ${t['cost_usd']:.3f}",
            file=sys.stderr,
        )
    (OUT / "history.md").write_text(history(), encoding="utf-8")


if __name__ == "__main__":
    main()
