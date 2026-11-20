import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from lease_redflag_detector.agent.loop import AgentConfig, ToolCall
from lease_redflag_detector.agent.registry import LeaseRegistry
from lease_redflag_detector.agent.tools import Priced, Tool, Toolbox, ToolError
from lease_redflag_detector.agent.toolset import (
    DraftArgs,
    build_toolbox,
    draft_redline,
    search_filters,
)
from lease_redflag_detector.rag.redline import Redline, Result
from lease_redflag_detector.rag.retrieve import RerankScores

ROOT = Path(__file__).resolve().parents[1]
CONFIG = AgentConfig.load(ROOT / "configs" / "agent-haiku-v1.toml")
LEASE = "lease_37032"


class Args(BaseModel):
    n: int


class Out(BaseModel):
    value: int


def toolbox(fn) -> Toolbox:
    return Toolbox([Tool("t", "tools/get_lease_v1", Args, Out, fn)])


def run(box: Toolbox, args: dict, name: str = "t"):
    return box.execute(ToolCall("id", name, args))


def test_a_valid_call_returns_the_result_as_json():
    result = run(toolbox(lambda a: Out(value=a.n * 2)), {"n": 2})
    assert not result.is_error and json.loads(result.content) == {"value": 4}


def test_unknown_tools_and_invalid_arguments_go_back_to_the_model():
    box = toolbox(lambda a: Out(value=1))
    assert "Unknown tool 'x'" in run(box, {}, "x").content
    result = run(box, {"n": "two"})
    assert result.is_error and result.content.startswith("Invalid arguments for t: n:")


def test_a_result_that_changed_shape_is_an_error_not_a_silent_none():
    result = run(toolbox(lambda a: {"amount": 1}), {"n": 1})
    assert (
        result.is_error and "unexpected format: value: Field required" in result.content
    )


def test_the_cost_of_a_tool_counts_even_when_it_fails():
    assert (
        run(toolbox(lambda a: Priced(Out(value=1), 0.002)), {"n": 1}).cost_usd == 0.002
    )

    def fails(args):
        raise ToolError("Extraction failed", cost_usd=0.003)

    result = run(toolbox(fails), {"n": 1})
    assert result.is_error and result.cost_usd == 0.003


class FakeRetriever:
    def __init__(self):
        self.chunks = []

    def search(self, *args, **kwargs):
        return []


def test_every_tool_has_a_description_and_a_schema():
    box = build_toolbox(CONFIG, retriever=FakeRetriever(), warm=False)
    names = [s["name"] for s in box.schemas()]
    assert names == [
        "search_corpus",
        "find_leases",
        "get_lease",
        "read_lease_section",
        "extract_red_flags",
        "draft_redline",
    ]
    for schema in box.schemas():
        assert len(schema["description"]) > 100 and schema["input_schema"]["properties"]
    assert not any(tool.side_effect for tool in box.tools.values())


def test_search_filters_by_role_and_version():
    assert search_filters("law", "current").types == ["law"]
    assert search_filters("law", "current").status == ["current"]
    assert search_filters("law", "all").status is None
    assert search_filters(None, "current").exclude_regimes == ["law_157_ix"]


def test_the_registry_finds_and_reads_leases():
    registry = LeaseRegistry()
    found = registry.find(party="нова пошта")
    assert [lease["lease_id"] for lease in found] == [LEASE]
    assert registry.find(party="пошта", city="Київ")[0]["lease_id"] == LEASE
    sections = registry.sections(LEASE)
    assert sections[1].number == 2 and sections[1].title.startswith("1.")


def test_lease_tools_refuse_unknown_ids():
    box = build_toolbox(CONFIG, retriever=FakeRetriever(), warm=False)
    result = run(box, {"lease_id": "lease_1"}, "get_lease")
    assert result.is_error and "No lease lease_1" in result.content
    assert run(box, {"lease_id": "../etc"}, "get_lease").content.startswith(
        "Invalid arguments"
    )


class FakeGenerator:
    config = CONFIG

    def __init__(self):
        self.calls = 0

    def generate(self, red_flag, exclude_doc=None):
        assert exclude_doc == LEASE
        self.calls += 1
        output = Redline(
            verdict="not_covered",
            findings=[{"text": "Політика мовчить.", "sources": ["S1"]}],
            risk="high",
            risk_reason={"text": "Платежі.", "sources": ["S1"]},
            proposed_clause=None,
            proposed_sources=[],
            gaps=[],
            conflicts=[],
        )
        return Result("ok", [], "", output, approval="юрист", input_tokens=10_000)


def test_draft_redline_needs_a_verbatim_quote_and_reports_stage_2_routing():
    registry = LeaseRegistry()
    generator = FakeGenerator()
    draft = draft_redline(registry, generator)
    with pytest.raises(ToolError, match="not in lease_37032 word for word"):
        draft(
            DraftArgs(
                lease_id=LEASE, type="sublease_permitted", quote="Вигадана умова."
            )
        )
    assert generator.calls == 0
    quote = registry.sections(LEASE)[1].text.splitlines()[0]
    priced = draft(DraftArgs(lease_id=LEASE, type="sublease_permitted", quote=quote))
    assert priced.output.needs_decision and priced.output.approval == "юрист"
    assert priced.output.proposed_sources == []
    assert priced.cost_usd == pytest.approx(0.001)


def test_new_reranker_scores_go_to_the_local_cache_only(tmp_path):
    committed, local = tmp_path / "committed", tmp_path / "local"
    committed.mkdir()
    name = "m.json"
    scores = RerankScores("m", committed)
    key = scores.key("q", "old")
    (committed / name).write_text(json.dumps({key: 0.5}))
    scores = RerankScores("m", committed, local_dir=local)
    scores.__dict__["model"] = type(
        "M", (), {"predict": lambda self, p: [0.9] * len(p)}
    )()
    assert scores.predict([("q", "old"), ("q", "new")]) == [0.5, 0.9]
    assert json.loads((committed / name).read_text()) == {key: 0.5}
    assert list(json.loads((local / name).read_text()).values()) == [0.9]


def test_model_calls_inside_tools_fit_in_the_tool_time_limit():
    from lease_redflag_detector.agent.toolset import (
        DRAFT_TIMEOUT_S,
        EXTRACT_TIMEOUT_S,
        tool_client,
    )
    from lease_redflag_detector.extraction.extractor import RunConfig

    for path, limit in [
        ("configs/claude-haiku-medium-v3.toml", EXTRACT_TIMEOUT_S),
        ("configs/rag-haiku-v3.toml", DRAFT_TIMEOUT_S),
    ]:
        config = tool_client(RunConfig.load(ROOT / path), limit)
        # an answer and one repair, no client retries
        assert config.max_retries == 0 and 2 * config.timeout_s < limit
