import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "search_behaviour", ROOT / "scripts" / "search_behaviour.py"
)
sb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sb)


def fragment(text="", document="Політика", section=""):
    return {"document": document, "section": section, "text": text}


def search(step, *fragments, error=False):
    return {
        "kind": "tool",
        "name": "search_corpus",
        "step": step,
        "args": {"query": f"q{step}"},
        "is_error": error,
        "content": "503" if error else json.dumps({"fragments": list(fragments)}),
        "latency_s": 1.0,
    }


def run(tmp_path, traces: dict[str, list[dict]]) -> Path:
    folder = tmp_path / "run"
    (folder / "traces").mkdir(parents=True)
    rows = [
        {"id": task, "cost_usd": 0.001, "latency_s": 5.0, "passed": True}
        for task in traces
    ]
    (folder / "results.jsonl").write_text("\n".join(map(json.dumps, rows)))
    for task, events in traces.items():
        (folder / "traces" / f"{task}.jsonl").write_text(
            "\n".join(map(json.dumps, events))
        )
    return folder


def test_only_a_search_after_the_results_counts_as_searching_again(tmp_path):
    point = fragment("10.2. Поступки погоджує комітет.", document="Зміни № 1")
    traces = {
        "q03": [search(1, point), search(1, point)],  # asked for together
        "x07": [search(1), search(2)],  # the second after seeing the first
        "f21": [search(1, error=True), search(2, point)],  # a failure is no search
    }
    tasks = {t["task"]: t for t in sb.analyse([run(tmp_path, traces)])}
    assert (tasks["q03"]["same_step"], tasks["q03"]["later"]) == (1, 0)
    assert (tasks["x07"]["same_step"], tasks["x07"]["later"]) == (0, 1)
    assert len(tasks["f21"]["searches"]) == 1 and tasks["f21"]["later"] == 0


def test_the_source_is_the_point_itself_or_the_minute_in_the_title():
    q04, q06 = sb.ANSWERED["q04"], sb.ANSWERED["q06"]
    assert sb.has([fragment("Вступ.\n4.2. Орендар повідомляє…")], q04)
    assert not sb.has([fragment("Строк повідомлення — за п. 4.2 Політики.")], q04)
    assert not sb.has([fragment("Ф-4.2.1 формулювання")], q04)
    assert sb.has([fragment(document="Протокол комітету № 3/2026")], q06)


def test_point_10_2_counts_from_the_policy_or_the_amendment():
    q03 = sb.ANSWERED["q03"]
    amended = fragment("10.1. Юрист.\n10.2. Комітет.", document="Зміни № 1 до Політики")
    assert sb.has([amended], q03)
    assert sb.has([fragment("10.2. Комерційний директор.")], q03)  # runs before 3.2
    assert not sb.has([fragment("Див. п. 10.2 Політики.")], q03)


def test_the_tasks_named_by_the_script_are_in_the_task_set():
    sb.check_tasks()


def test_runs_of_different_prompts_are_counted_apart(tmp_path):
    runs = []
    for name, prompt in [("a", "agent/v2"), ("b", "agent/v5"), ("c", "agent/v2")]:
        folder = tmp_path / name
        folder.mkdir()
        info = {"prompt": prompt, "tasks": {"hash": "h"}, "commit": "c"}
        (folder / "run.json").write_text(json.dumps(info))
        runs.append(folder)
    groups = sb.by_prompt(runs)
    assert [[r.name for r in g] for g in groups.values()] == [["a", "c"], ["b"]]
