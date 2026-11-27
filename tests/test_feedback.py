import tomllib

from lease_redflag_detector.agent.candidates import blocks, draft, promote
from lease_redflag_detector.agent.feedback import (
    NEW,
    PROMOTED,
    RATED,
    FeedbackStore,
    lease_of,
    take_feedback,
)
from lease_redflag_detector.agent.memory import ACTIVE, NoteStore, policy_version
from lease_redflag_detector.agent.queue import Request
from lease_redflag_detector.agent.review import decision_note
from lease_redflag_detector.agent.users import get_user

LAWYER = get_user("lawyer")
QUESTION = "Чи можна погодити орендарю офісу lease_55572 відмову через 18 місяців?"
WRONG = "Так, 18 місяців — допустима поступка."
CORRECTION = "За п. 4.2 для офісу — не раніше 24 місяців, тож ні."


def answers(*given):
    given = list(given)
    return lambda prompt: given.pop(0)


def stores(tmp_path):
    return FeedbackStore(tmp_path / "feedback.db"), NoteStore(tmp_path / "memory.db")


def test_a_plus_is_a_rating_and_a_minus_a_candidate(tmp_path):
    feedback, notes = stores(tmp_path)
    assert (
        take_feedback(feedback, notes, LAWYER, 1, QUESTION, "Ні.", read=answers(""))
        is None
    )
    plus = take_feedback(feedback, notes, LAWYER, 1, QUESTION, "Ні.", read=answers("+"))
    minus = take_feedback(
        feedback, notes, LAWYER, 2, QUESTION, WRONG, read=answers("-")
    )
    assert (plus.rating, plus.status) == (1, RATED)
    assert (minus.rating, minus.status, minus.correction) == (-1, NEW, None)
    assert notes.all() == []


def test_a_correction_becomes_a_note_only_if_the_lawyer_says_so(tmp_path):
    feedback, notes = stores(tmp_path)
    kept = take_feedback(
        feedback, notes, LAWYER, 1, QUESTION, WRONG, read=answers(CORRECTION, "так")
    )
    assert kept.correction == CORRECTION and kept.note_id == "N-0001"
    note = notes.get("N-0001")
    assert note.lease_id == "lease_55572" and CORRECTION in note.text
    not_kept = take_feedback(
        feedback, notes, LAWYER, 2, QUESTION, WRONG, read=answers(CORRECTION, "ні")
    )
    assert not_kept.note_id is None and len(notes.all()) == 1


def test_the_lease_of_a_correction_is_the_one_named():
    assert lease_of("про lease_55572", "так, lease_55572") == "lease_55572"
    assert lease_of("lease_1 і lease_2") is None and lease_of("без договору") is None


def test_a_rejected_request_becomes_a_note_that_replaces_nothing(tmp_path):
    notes = NoteStore(tmp_path / "memory.db")
    lawyers, _ = notes.add(
        "Моя нотатка про договір.",
        "lawyer",
        LAWYER.entity,
        policy_version(),
        "lease_55572",
    )
    request = Request(
        "R-0003", "lease_55572", "k", "відхилено", "", "", "lawyer", [], None
    )
    note = decision_note(
        notes, request, "відхилено", get_user("head"), "7 % лише для якірного"
    )
    assert note.lease_id == "lease_55572" and "R-0003 відхилено" in note.text
    assert "7 % лише для якірного" in note.text
    assert notes.get(lawyers.id).status == ACTIVE  # added, not replaced
    assert decision_note(notes, request, "погоджено", get_user("head"), "") is None


def candidate(tmp_path):
    feedback, notes = stores(tmp_path)
    take_feedback(
        feedback, notes, LAWYER, 1, QUESTION, WRONG, read=answers(CORRECTION, "ні")
    )
    tasks = tmp_path / "tasks.toml"
    tasks.write_text(
        '[[task]]\nid = "q03"\ngroup = "corpus"\nquestion = "?"\nwhy = "."\n'
    )
    drafts = tmp_path / "drafts.toml"
    return feedback, tasks, drafts


def test_a_draft_holds_the_question_and_the_correction(tmp_path):
    feedback, _, _ = candidate(tmp_path)
    task = tomllib.loads(draft(feedback.get("F-0001")))["task"][0]
    assert task["id"] == "F-0001" and task["question"] == QUESTION
    assert CORRECTION in task["why"] and task["user"] == "lawyer"
    assert not {"answer_has", "reviewed"} & task.keys()


def test_promote_moves_only_a_reviewed_draft_that_catches_the_wrong_answer(tmp_path):
    feedback, tasks, drafts = candidate(tmp_path)
    base = draft(feedback.get("F-0001"))
    assert promote("F-0001", feedback, drafts, tasks) == [
        "no draft F-0001 in drafts.toml"
    ]

    def attempt(extra: str) -> list[str]:
        drafts.write_text("# drafts\n" + base + extra)
        return promote("F-0001", feedback, drafts, tasks)

    stops = attempt("")
    assert "the draft has no checks" in stops
    assert any("has not reviewed" in s for s in stops)
    # a check the corrected answer passes catches nothing
    assert any(
        "passes the checks" in s
        for s in attempt('answer_has = ["18"]\nreviewed = "2026-11-25"\n')
    )
    assert attempt('answer_has = ["24 місяц"]\n') == [
        'the lawyer has not reviewed it (reviewed = "<date>")'
    ]
    assert attempt('answer_has = ["24 місяц"]\nreviewed = "2026-11-25"\n') == []
    moved = tomllib.loads(tasks.read_text())["task"]
    assert [t["id"] for t in moved] == ["q03", "F-0001"]
    assert (
        moved[1]["answer_has"] == ["24 місяц"] and moved[1]["reviewed"] == "2026-11-25"
    )
    assert blocks(drafts.read_text()) == []  # gone from the drafts
    assert feedback.get("F-0001").status == PROMOTED


def test_a_correction_about_no_lease_or_several_makes_no_note(tmp_path):
    feedback, notes = stores(tmp_path)
    said = []
    for question in ("Які умови NDA зі Світовидом?", "Порівняй lease_1 і lease_2."):
        result = take_feedback(
            feedback, notes, LAWYER, 1, question, "Відповідь.",
            read=answers(CORRECTION), say=said.append,
        )  # fmt: skip
        assert result.correction == CORRECTION and result.note_id is None
    assert notes.all() == [] and len(said) == 2 and "запам'ятай" in said[0]


def test_a_draft_keeps_the_answer_out_and_the_task_set_gets_no_instructions(tmp_path):
    feedback, tasks, drafts = candidate(tmp_path)
    text = draft(feedback.get("F-0001"))
    assert WRONG not in text  # the corrected answer stays in feedback.db
    drafts.write_text(text + 'answer_has = ["24 місяц"]\nreviewed = "2026-11-25"\n')
    assert promote("F-0001", feedback, drafts, tasks) == []
    assert "To complete" not in tasks.read_text()
