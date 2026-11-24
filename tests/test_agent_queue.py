import sqlite3
import threading

import pytest

from lease_redflag_detector.agent.confirm import ScriptedConfirmer
from lease_redflag_detector.agent.faults import FaultyToolbox
from lease_redflag_detector.agent.loop import Agent, Limits, Reply, ToolCall
from lease_redflag_detector.agent.queue import PENDING, REPLACED, ApprovalQueue
from lease_redflag_detector.agent.registry import LeaseRegistry
from lease_redflag_detector.agent.tools import Tool, Toolbox, ToolError
from lease_redflag_detector.agent.toolset import (
    Draft,
    DraftArgs,
    Drafts,
    Submission,
    SubmitArgs,
    draft_redline,
    submit_for_review,
)
from lease_redflag_detector.rag.redline import Redline, Result

LEASE = "lease_37032"
REGISTRY = LeaseRegistry()
QUOTES = [
    line for line in REGISTRY.sections(LEASE)[2].text.splitlines() if len(line) > 40
]


def draft(verdict: str, needs_decision: bool = False) -> Draft:
    claim = {"text": "Висновок.", "sources": ["S1"]}
    return Draft(
        lease_id=LEASE,
        verdict=verdict,
        risk="high",
        risk_reason=claim,
        findings=[claim],
        proposed_clause=None if verdict == "compliant" else "Нова редакція.",
        proposed_sources=[] if verdict == "compliant" else ["S1"],
        gaps=["Відкрите питання."] if needs_decision else [],
        conflicts=[],
        approval="юрист",
        needs_decision=needs_decision,
        sources=[
            {"id": "S1", "role": "position", "document": "Політика", "section": "4"}
        ],
    )


def drafts_of(*verdicts) -> Drafts:
    drafts = Drafts()
    for quote, verdict in zip(QUOTES, verdicts, strict=False):
        args = DraftArgs(lease_id=LEASE, type="tenant_break_option", quote=quote)
        drafts.add(
            args, draft(*verdict) if isinstance(verdict, tuple) else draft(verdict)
        )
    return drafts


def submit(tmp_path, drafts, *answers):
    queue = ApprovalQueue(tmp_path / "queue.db")
    confirm = ScriptedConfirmer(*answers)
    run = submit_for_review(REGISTRY, drafts, queue, confirm, "lawyer")
    return run, queue, confirm


def test_nothing_is_created_without_the_lawyers_yes(tmp_path):
    run, queue, confirm = submit(tmp_path, drafts_of("concession"), False)
    result = run(SubmitArgs(lease_id=LEASE))
    assert not result.created and result.status == "not confirmed"
    assert result.points == 1
    assert queue.all() == [] and len(confirm.asked) == 1


def test_a_confirmed_request_lists_the_contested_points_only(tmp_path):
    drafts = drafts_of("concession", "compliant", "unacceptable", ("compliant", True))
    run, queue, confirm = submit(tmp_path, drafts, True)
    result = run(SubmitArgs(lease_id=LEASE))
    assert result.created and result.request_id == "R-0001" and result.status == PENDING
    request = queue.get("R-0001")
    sections = sorted((i["section"], i["verdict"]) for i in request.items)
    # compliant left out, unless the lawyer must decide; unacceptable for information
    assert sections == [
        ("до відома", "unacceptable"),
        ("погодження", "compliant"),
        ("погодження", "concession"),
    ]
    assert "Кому: юрист → комерційний комітет" in confirm.asked[0]
    # each list numbered from 1
    assert confirm.asked[0].count("   1. ") == 2 and "   3. " not in confirm.asked[0]
    assert queue.history("R-0001")[0]["status"] == PENDING


def test_the_same_request_again_is_not_a_duplicate_and_not_asked_again(tmp_path):
    run, queue, confirm = submit(tmp_path, drafts_of("concession"), True, True)
    first = run(SubmitArgs(lease_id=LEASE))
    second = run(SubmitArgs(lease_id=LEASE))
    assert second.request_id == first.request_id and not second.created
    assert len(queue.all()) == 1 and len(confirm.asked) == 1


def test_changed_points_replace_the_pending_request(tmp_path):
    run, queue, _ = submit(tmp_path, drafts_of("concession"), True, True)
    run(SubmitArgs(lease_id=LEASE))
    changed = drafts_of("beyond_concessions")
    run2 = submit_for_review(
        REGISTRY, changed, queue, ScriptedConfirmer(True), "lawyer"
    )
    result = run2(SubmitArgs(lease_id=LEASE))
    assert result.request_id == "R-0002" and result.replaces == "R-0001"
    assert queue.get("R-0001").status == REPLACED


def test_no_request_without_redlines_or_without_anything_to_approve(tmp_path):
    run, queue, confirm = submit(tmp_path, Drafts(), True)
    with pytest.raises(ToolError, match="run draft_redline"):
        run(SubmitArgs(lease_id=LEASE))
    run, queue, confirm = submit(tmp_path, drafts_of("compliant", "unacceptable"), True)
    with pytest.raises(ToolError, match="Nothing in lease_37032 needs approval"):
        run(SubmitArgs(lease_id=LEASE))
    assert confirm.asked == [] and queue.all() == []


def test_two_calls_at_once_create_one_request(tmp_path):
    queue = ApprovalQueue(tmp_path / "queue.db")
    results = []

    def create():
        results.append(
            queue.create(LEASE, "key", [{"section": "погодження"}], "lawyer")
        )

    threads = [threading.Thread(target=create) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(queue.all()) == 1 and sum(created for _, created in results) == 1


def test_only_a_person_decides_and_only_on_a_pending_request(tmp_path):
    queue = ApprovalQueue(tmp_path / "queue.db")
    queue.create(LEASE, "key", [], "lawyer")
    with pytest.raises(ValueError, match="status must be one of"):
        queue.decide("R-0001", "замінено", "lawyer")
    queue.decide("R-0001", "відхилено", "head", "Не погоджуємо 30 днів.")
    with pytest.raises(ValueError, match="is відхилено"):
        queue.decide("R-0001", "погоджено", "head")
    assert queue.history("R-0001")[-1]["comment"] == "Не погоджуємо 30 днів."


class Generator:
    config = type("C", (), {"model": "fake"})()

    def generate(self, red_flag, exclude_doc=None):
        output = Redline(
            verdict="concession",
            findings=[{"text": "Поступка.", "sources": ["S1"]}],
            risk="high",
            risk_reason={"text": "Строк.", "sources": ["S1"]},
            proposed_clause="Нова редакція.",
            proposed_sources=["S1"],
            gaps=[],
            conflicts=[],
        )
        return Result("ok", [], "", output, approval="юрист")


class Model:
    """Drafts one redline, submits, and submits again if the answer did not arrive."""

    name = "fake"
    errors = ()

    def call(self, system, messages, tools, final_only, timeout):
        turn = len(messages)
        if turn == 1:
            args = {
                "lease_id": LEASE,
                "type": "tenant_break_option",
                "quote": QUOTES[0],
            }
            call = ToolCall("d", "draft_redline", args)
        elif turn in (3, 5):
            call = ToolCall(f"s{turn}", "submit_for_review", {"lease_id": LEASE})
        else:
            return Reply("Готово.", [], [{"type": "text", "text": "Готово."}])
        return Reply("", [call], [{"type": "tool_use", "id": call.id}])


def test_a_lost_answer_and_a_second_call_create_one_request(tmp_path):
    queue = ApprovalQueue(tmp_path / "queue.db")
    confirm = ScriptedConfirmer(True, True)
    drafts = Drafts()
    threads = []

    def submit_in(args):
        threads.append(threading.current_thread())
        return submit_for_review(REGISTRY, drafts, queue, confirm, "lawyer")(args)

    tools = Toolbox(
        [
            Tool("draft_redline", "tools/draft_redline_v1", DraftArgs, Draft,
                 draft_redline(REGISTRY, Generator(), drafts)),
            Tool("submit_for_review", "tools/submit_for_review_v1", SubmitArgs,
                 Submission, submit_in, side_effect=True, retry_safe=False),
        ],
        on_request=[drafts.reset],
    )  # fmt: skip
    faulty = FaultyToolbox(tools, "submit_for_review:lost*1")
    agent = Agent(
        Model(), faulty, "system", Limits(), "STOP {reason}", sleep=lambda s: None
    )
    answer = agent.run("Передай договір на погодження")
    submits = [e for e in answer.trace.tool_calls() if e["name"] == "submit_for_review"]
    assert [e["attempts"] for e in submits] == [1, 1]  # a side effect is not retried
    assert submits[0]["error_kind"] == "transient"
    assert (
        '"created":false' in submits[1]["content"] and "R-0001" in submits[1]["content"]
    )
    assert len(queue.all()) == 1 and len(confirm.asked) == 1
    assert all(t is threading.main_thread() for t in threads)


def test_the_same_points_may_be_submitted_again_after_a_decision(tmp_path):
    run, queue, confirm = submit(tmp_path, drafts_of("concession"), True, True)
    first = run(SubmitArgs(lease_id=LEASE))
    queue.decide(first.request_id, "повернуто", "head", "Уточнити з орендарем.")
    again = run(SubmitArgs(lease_id=LEASE))
    assert again.created and again.request_id == "R-0002" and again.replaces is None
    assert len(confirm.asked) == 2


def test_the_database_keeps_one_pending_request_per_lease(tmp_path):
    queue = ApprovalQueue(tmp_path / "queue.db")
    queue.create(LEASE, "key-1", [], "lawyer")
    with queue.connect() as db, pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO requests VALUES ('R-9', ?, 'key-2', ?, '', '', '', '[]', NULL)",
            (LEASE, PENDING),
        )


def test_the_result_says_what_the_lawyer_was_asked_and_answered(tmp_path):
    run, _, confirm = submit(tmp_path, drafts_of("concession"), False, True)
    declined = run(SubmitArgs(lease_id=LEASE))
    assert declined.confirmed is False and declined.confirmation == confirm.asked[0]
    created = run(SubmitArgs(lease_id=LEASE))
    assert created.confirmed is True and created.confirmation.startswith("Створити")
    repeated = run(SubmitArgs(lease_id=LEASE))
    assert repeated.confirmed is None and repeated.confirmation is None


def test_red_flags_without_a_redline_are_shown_before_the_lawyer_confirms(tmp_path):
    drafts = drafts_of("concession")
    drafts.flags[LEASE] = [
        ("tenant_break_option", QUOTES[0] + " і далі"),  # drafted, quoted shorter
        ("indexation_limited", QUOTES[1]),
        ("sublease_permitted", QUOTES[2]),
    ]
    run, _, confirm = submit(tmp_path, drafts, True)
    result = run(SubmitArgs(lease_id=LEASE))
    assert result.without_redline == 2
    assert "Червоних прапорців без redline: 2" in confirm.asked[0]


def test_an_old_queue_moves_to_the_new_schema_with_its_requests(tmp_path):
    path = tmp_path / "queue.db"
    db = sqlite3.connect(path)
    db.executescript(
        OLD_SCHEMA
        + "INSERT INTO requests VALUES ('R-0001', 'lease_1', 'k', 'відхилено', '',"
        " '', '', '[]', NULL);"
    )
    db.close()
    queue = ApprovalQueue(path)
    assert queue.get("R-0001").status == "відхилено"
    request, created = queue.create("lease_1", "k", [], "lawyer")  # same key again
    assert created and request.id == "R-0002"


OLD_SCHEMA = """
CREATE TABLE requests (
    id TEXT PRIMARY KEY,
    lease_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    addressee TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    items TEXT NOT NULL,
    replaces TEXT
);
"""
