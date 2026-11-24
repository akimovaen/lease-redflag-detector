import re
import tomllib
from pathlib import Path

from lease_redflag_detector.agent.evaluate import Outcome, check, tools_ok
from lease_redflag_detector.agent.faults import parse
from lease_redflag_detector.agent.loop import Limits, StopReason
from lease_redflag_detector.agent.queue import Request

ROOT = Path(__file__).resolve().parents[1]
TASKS = tomllib.loads((ROOT / "evals" / "agent_tasks.toml").read_text())["task"]
TOOLS = {
    "search_corpus",
    "find_leases",
    "get_lease",
    "read_lease_section",
    "extract_red_flags",
    "draft_redline",
    "submit_for_review",
}
KEYS = {
    "id",
    "group",
    "question",
    "why",
    "tools_called",
    "tools_not_called",
    "max_calls",
    "answer_has",
    "answer_lacks",
    "no_citations",
    "stop_reason",
    "requests_created",
    "confirm",
    "confirm_asked",
    "confirm_asked_times",
    "trace",
    "faults",
    "limits",
}


def tool(name, content="{}", **fields):
    return {
        "kind": "tool",
        "name": name,
        "content": content,
        "is_error": False,
    } | fields


def request(request_id):
    return Request(request_id, "lease_1", "k", "очікує", "", "", "", [], None)


def outcome(answer="", events=(), requests=(), asked=(), stop="final"):
    return Outcome(answer, stop, list(events), list(requests), list(asked))


def failed(task, result):
    return [c.name for c in check(task, result) if not c.passed]


def test_the_task_set_is_well_formed():
    assert len(TASKS) >= 15
    assert len({t["id"] for t in TASKS}) == len(TASKS)
    for task in TASKS:
        assert task.keys() <= KEYS, task["id"]
        assert {"id", "group", "question", "why"} <= task.keys(), task["id"]
        named = (
            set(task.get("tools_called", []))
            | (set(task.get("tools_not_called", [])) - {"*"})
            | set(task.get("max_calls", {}))
        )
        assert named <= TOOLS, task["id"]
        for pattern in task.get("answer_has", []) + task.get("answer_lacks", []):
            re.compile(pattern)
        if "faults" in task:
            assert {f.tool for f in parse(task["faults"])} - {None} <= TOOLS
        Limits(**task.get("limits", {}))
        assert task.get("stop_reason", "final") in set(StopReason)


def test_tool_checks():
    events = [tool("find_leases"), tool("find_leases"), tool("get_lease")]
    task = {
        "tools_called": ["find_leases", "extract_red_flags"],
        "tools_not_called": ["get_lease"],
        "max_calls": {"find_leases": 1},
    }
    checks = check(task, outcome(events=events))
    assert [c.name for c in checks if not c.passed] == [
        "called extract_red_flags",
        "not called get_lease",
        "find_leases ≤ 1 calls",
    ]
    assert tools_ok(checks) is False
    assert failed({"tools_not_called": ["*"]}, outcome(events=events)) == ["no tool"]
    assert failed({"tools_not_called": ["*"]}, outcome()) == []
    assert tools_ok(check({"answer_has": ["x"]}, outcome("x"))) is None


def test_answer_checks_ignore_case_and_find_citations():
    task = {"answer_has": ["комерційн\\w* директор"], "answer_lacks": ["грн"]}
    assert failed(task, outcome("Погоджує Комерційний директор.")) == []
    assert failed(task, outcome("Штраф 500 грн.")) == [
        "answer has /комерційн\\w* директор/",
        "answer lacks /грн/",
    ]
    assert failed({"no_citations": True}, outcome("Пошук недоступний.")) == []
    for cited in ("за п. 10.2", "ст. 762 ЦК", "формулювання Ф-2.1"):
        assert failed({"no_citations": True}, outcome(cited)) == ["no citations"]


def test_how_many_times_the_lawyer_was_asked():
    task = {"confirm_asked_times": 1}
    assert failed(task, outcome(asked=["?"])) == []
    assert failed(task, outcome(asked=["?", "?"])) == ["confirmation asked 1 times"]


def test_stop_queue_and_trace_checks():
    events = [tool("search_corpus", error_kind="transient", attempts=3)]
    task = {
        "stop_reason": "budget",
        "requests_created": 0,
        "confirm_asked": True,
        "trace": {"tool": "search_corpus", "error_kind": "transient", "attempts": 3},
    }
    assert failed(task, outcome(events=events, asked=["?"], stop="budget")) == []
    result = outcome(events=[tool("search_corpus", attempts=1)])
    assert failed(task, result) == [
        "stop budget",
        "confirmation asked",
        f"trace {task['trace']}",
    ]


def test_a_request_beyond_the_lawyers_yes_answers_is_an_action_without_permission():
    one = outcome(requests=[request("R-0001")], asked=["?"])
    one.confirmed = 1
    assert failed({}, one) == []
    # a lost answer leaves no trace of the confirmation, the confirmer has it
    one.events = [tool("submit_for_review", '"connection lost"', is_error=True)]
    assert failed({}, one) == []
    one.confirmed = 0
    assert failed({}, one) == ["no action without permission"]
