import json

from lease_redflag_detector.extraction.schema import RedFlagType
from lease_redflag_detector.rag.chunking import Chunk
from lease_redflag_detector.rag.redline import (
    APPROVAL,
    DEFAULT_RISK,
    Result,
    Verdict,
    approval,
    build_sources,
    fixed_chunks,
    gap_line,
    needs_decision,
    validate,
)
from lease_redflag_detector.rag.retrieve import Hit

POLICY = {"type": "policy", "status": "current"}


def chunk(chunk_id: str, text: str = "", tokens: int = 100, meta=None) -> Chunk:
    return Chunk(chunk_id, chunk_id.split("#")[0], text, [], tokens, meta or {})


def answer(**changes) -> str:
    base = {
        "verdict": "unacceptable",
        "findings": [{"text": "Порушує п. 4.3.", "sources": ["S1"]}],
        "risk": "high",
        "risk_reason": {"text": "Строк договору.", "sources": ["S2"]},
        "proposed_clause": "Орендар не має права відмовитися від Договору.",
        "proposed_sources": ["S2"],
        "gaps": [],
        "conflicts": [],
    }
    return json.dumps(base | changes, ensure_ascii=False)


def test_valid_answer_passes():
    output, error = validate(answer(), {"S1", "S2"})
    assert error is None and output.verdict == Verdict.UNACCEPTABLE


def test_sources_must_be_in_the_context_and_every_claim_needs_one():
    _, error = validate(answer(), {"S1"})
    assert "unknown sources ['S2']" in error
    findings = [{"text": "Без джерела.", "sources": []}]
    _, error = validate(answer(findings=findings), {"S1", "S2"})
    assert "findings: no source" in error


def test_saved_gaps_of_both_formats_render():
    assert gap_line("Стара прогалина.") == "Стара прогалина."
    gap = {"text": "Нова.", "changes_verdict": True}
    assert gap_line(gap) == "Нова. (змінює вердикт)"


def test_changed_clause_is_required_or_forbidden_by_verdict():
    _, error = validate(answer(proposed_clause=None), {"S1", "S2"})
    assert "required for verdict unacceptable" in error
    _, error = validate(answer(verdict="not_covered"), {"S1", "S2"})
    assert "must be null for verdict not_covered" in error
    output, _ = validate(
        answer(verdict="concession", proposed_clause=None, proposed_sources=[]),
        {"S1", "S2"},
    )
    assert output is not None


def test_fixed_points_are_found_in_the_policy_in_force_only():
    chunks = [
        chunk("policy_2026#002", "1.5. Терміни\n1.6. Оцінка змін", meta=POLICY),
        chunk("policy_2026#004", "2.1. Базова позиція", meta=POLICY),
        chunk("policy_2026#012", "10.1. Договір погоджує юрист", meta=POLICY),
        chunk(
            "policy_2024#008",
            "1.6. Стара",
            meta={"type": "policy", "status": "outdated"},
        ),
    ]
    assert [c.id for c in fixed_chunks(chunks)] == [
        "policy_2026#002",
        "policy_2026#012",
    ]


def test_an_amendment_that_restates_a_point_replaces_the_old_one():
    amendment = {"type": "policy", "status": "current", "date": "2026-10-01"}
    chunks = [
        chunk("policy_2026#002", "1.6. Оцінка змін", meta=POLICY),
        chunk(
            "policy_2026#012", "10.1. Юрист\n10.2. Комерційний директор", meta=POLICY
        ),
        chunk(
            "amendment#002", "10.1. Юрист\n10.2. Комерційний комітет", meta=amendment
        ),
    ]
    assert [c.id for c in fixed_chunks(chunks)] == ["policy_2026#002", "amendment#002"]


def test_the_committee_approves_what_may_be_approved():
    for verdict in (Verdict.CONCESSION, Verdict.BEYOND_CONCESSIONS):
        assert "комерційний комітет" in APPROVAL[verdict]
        assert "Змін № 1" in APPROVAL[verdict]
        assert "директор" not in APPROVAL[verdict]


def test_sources_are_numbered_once_and_cut_to_the_budget_by_score():
    fixed = [chunk("policy_2026#012", tokens=100)]
    hits = {
        "position": [Hit(chunk("policy_2026#006", tokens=300), 0.9)],
        "wording": [Hit(chunk("clause_library_2026#012", tokens=300), 0.5)],
        "law": [
            Hit(chunk("civil_code#026", tokens=300), 0.02),
            Hit(chunk("policy_2026#012", tokens=100), 0.4),
        ],
    }
    sources = build_sources(hits, fixed, budget=800)
    assert [(s.id, s.chunk.id) for s in sources] == [
        ("S1", "policy_2026#006"),
        ("S2", "clause_library_2026#012"),
        ("S3", "policy_2026#012"),
    ]
    assert sources[-1].score is None


def test_every_type_and_verdict_has_a_default():
    assert set(DEFAULT_RISK) == set(RedFlagType)
    assert set(APPROVAL) == set(Verdict)


def test_any_gap_needs_the_lawyers_decision():
    output, _ = validate(answer(), {"S1", "S2"})
    assert not Result("ok", [], "", output).needs_decision
    output, _ = validate(answer(gaps=["Хто несе витрати на пальне?"]), {"S1", "S2"})
    assert Result("ok", [], "", output).needs_decision
    assert not Result("failed", [], "").needs_decision


def test_open_points_go_to_the_committee_marked_not_held_back():
    assert approval("unacceptable", False) == APPROVAL[Verdict.UNACCEPTABLE]
    marked = approval("beyond_concessions", True)
    assert marked.startswith(
        "потребує додаткового аналізу юриста — подається до комітету"
    )
    assert "10.5" in marked and "спершу" not in marked
    assert marked.endswith(APPROVAL[Verdict.BEYOND_CONCESSIONS])
    assert approval("not_covered", True) == APPROVAL[Verdict.NOT_COVERED]
    assert "комерційного комітету" in APPROVAL[Verdict.NOT_COVERED]


def test_any_gap_or_not_covered_needs_the_lawyer():
    assert needs_decision("compliant", ["Чи діє ліміт для ритейлу?"])
    assert needs_decision("not_covered", [])
    assert not needs_decision("unacceptable", [])


def test_the_corpus_gives_the_redline_section_10_as_amended():
    from lease_redflag_detector.rag.retrieve import load_chunks

    fixed = fixed_chunks(load_chunks())
    section_10 = [c for c in fixed if "10.2." in c.text]
    assert [c.doc_id for c in section_10] == ["policy_2026_amendment_1"]
    # the amendment's own points 1.1-1.3 must not stand in for the policy's 1.6-1.7
    risk = [c for c in fixed if "1.6." in c.text or "1.7." in c.text]
    assert risk and {c.doc_id for c in risk} == {"policy_2026"}
    assert section_10[0].meta["amends"] == "policy_2026"
    assert "комерційний комітет" in section_10[0].text
