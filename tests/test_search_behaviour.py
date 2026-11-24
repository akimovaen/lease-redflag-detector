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
    point = fragment("10.2. Поступки погоджує комерційний директор.")
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
    q03, q06 = sb.ANSWERED["q03"], sb.ANSWERED["q06"]
    assert sb.has([fragment("Вступ.\n10.2. Поступки погоджує…")], q03)
    assert not sb.has([fragment("Відступи погоджуються за п. 10.2 Політики.")], q03)
    assert not sb.has([fragment("Ф-10.2.1 формулювання")], q03)
    assert sb.has([fragment(document="Протокол комітету № 3/2026")], q06)


def test_the_tasks_named_by_the_script_are_in_the_task_set():
    sb.check_tasks()
