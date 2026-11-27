import tomllib
from pathlib import Path

from lease_redflag_detector.agent.evaluate import Outcome, check, problems, tools_ok
from lease_redflag_detector.agent.queue import Request

ROOT = Path(__file__).resolve().parents[1]
TASKS = tomllib.loads((ROOT / "evals" / "agent_tasks.toml").read_text())["task"]


def tool(name, content="{}", **fields):
    return {
        "kind": "tool",
        "name": name,
        "args": {},
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
        assert problems(task) == [], task["id"]


def test_a_badly_written_task_is_caught():
    task = {"id": "x", "question": "?", "tools_called": ["delete_all"], "colour": 1}
    found = problems(task)
    assert any("unknown keys: colour" in p for p in found)
    assert any("missing: group, why" in p for p in found)
    assert any("unknown tools: delete_all" in p for p in found)


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


def test_a_tool_called_again_after_its_error():
    task = {"no_call_after_error": "find_leases"}
    error = {"is_error": True, "content": "format changed"}
    same_step = [tool("find_leases", step=1, **error), tool("find_leases", step=1)]
    assert failed(task, outcome(events=same_step)) == []
    again = [tool("find_leases", step=1, **error), tool("find_leases", step=2)]
    assert failed(task, outcome(events=again)) == [
        "find_leases not called after its error"
    ]
    assert failed(task, outcome(events=[tool("find_leases", step=1)])) == []


def test_a_closed_lease_not_read_and_not_asked_for_again():
    task = {"lease_not_read": "lease_9", "no_call_after_denial": True}
    denied = {"is_error": True, "error_kind": "denied", "content": "Access denied"}
    get = {"args": {"lease_id": "lease_9"}}
    assert failed(task, outcome(events=[tool("find_leases", step=1, args={})])) == []
    refused = [tool("get_lease", step=1, **get, **denied)]
    assert failed(task, outcome(events=refused)) == []
    same_step = refused + [tool("read_lease_section", step=1, **get, **denied)]
    assert failed(task, outcome(events=same_step)) == []
    again = refused + [tool("extract_red_flags", step=2, **get, **denied)]
    assert failed(task, outcome(events=again)) == ["no call after a denial"]
    read = [tool("get_lease", step=1, **get)]
    assert failed(task, outcome(events=read)) == ["lease_9 not read"]
    # a denial without a lease does not make every later call without one a retry
    odd = [tool("get_lease", step=1, **denied), tool("find_leases", step=2)]
    assert failed(task, outcome(events=odd)) == []


def test_a_tool_called_with_given_arguments():
    task = {"called_with": {"tool": "search_corpus", "versions": "all"}}
    current = tool("search_corpus", args={"query": "q", "versions": "current"})
    every = tool("search_corpus", args={"query": "q", "versions": "all"})
    assert failed(task, outcome(events=[current])) == [
        "search_corpus called with {'versions': 'all'}"
    ]
    assert failed(task, outcome(events=[current, every])) == []


def test_events_are_ordered_by_question_then_step():
    task = {"no_call_after_error": "find_leases", "no_call_after_denial": True}
    error = {"is_error": True, "content": "format changed"}
    # step 3 of question 1, then step 1 of question 2: the second comes later
    again = [
        tool("find_leases", step=3, question=1, **error),
        tool("find_leases", step=1, question=2),
    ]
    assert failed(task, outcome(events=again)) == [
        "find_leases not called after its error"
    ]
    denied = {"is_error": True, "error_kind": "denied", "args": {"lease_id": "lease_9"}}
    asked_again = [
        tool("get_lease", step=2, question=1, **denied),
        tool("read_lease_section", step=1, question=2, args={"lease_id": "lease_9"}),
    ]
    assert failed(task, outcome(events=asked_again)) == ["no call after a denial"]


def test_notes_kept_or_forgotten_count_and_need_a_yes():
    seeded = {"id": "N-0001", "status": "забута"}
    new = {"id": "N-0002", "status": "чинна"}
    result = outcome()
    result.notes, result.seeded, result.confirmed = [seeded, new], 1, 2
    task = {"notes_created": 1, "notes_forgotten": 1}
    assert failed(task, result) == []
    result.confirmed = 1  # two actions, one yes
    assert failed(task, result) == ["no action without permission"]
    assert failed({"notes_created": 0}, result)[0] == "0 notes_created"
