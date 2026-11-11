import json

from lease_redflag_detector.extraction.schema import RedFlagType
from lease_redflag_detector.rag.chunking import Chunk
from lease_redflag_detector.rag.redline import (
    APPROVAL,
    DEFAULT_RISK,
    Verdict,
    build_sources,
    fixed_chunks,
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
