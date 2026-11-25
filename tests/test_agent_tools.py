import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from lease_redflag_detector.agent.confirm import ScriptedConfirmer
from lease_redflag_detector.agent.loop import AgentConfig, ToolCall
from lease_redflag_detector.agent.memory import NoteStore
from lease_redflag_detector.agent.queue import ApprovalQueue
from lease_redflag_detector.agent.registry import LeaseRegistry
from lease_redflag_detector.agent.registry_client import RegistryClient
from lease_redflag_detector.agent.registry_server import build_server
from lease_redflag_detector.agent.tools import Priced, Tool, Toolbox, ToolError
from lease_redflag_detector.agent.toolset import (
    DraftArgs,
    Drafts,
    build_toolbox,
    draft_redline,
    search_filters,
)
from lease_redflag_detector.agent.users import get_user
from lease_redflag_detector.rag.redline import Redline, Result
from lease_redflag_detector.rag.retrieve import RerankScores

ROOT = Path(__file__).resolve().parents[1]
CONFIG = AgentConfig.load(ROOT / "configs" / "agent-haiku-v1.toml")
LEASE = "lease_37032"
REGISTRY = RegistryClient(
    build_server(get_user("lawyer"))
)  # the MCP server, in this process


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


def toolbox_without_search(tmp_path, confirm=None):
    return build_toolbox(
        CONFIG,
        registry=REGISTRY,
        retriever=FakeRetriever(),
        warm=False,
        queue=ApprovalQueue(tmp_path / "queue.db"),
        confirm=confirm or ScriptedConfirmer(),
        memory=NoteStore(tmp_path / "memory.db"),
    )


def test_every_tool_has_a_description_and_a_schema(tmp_path):
    box = toolbox_without_search(tmp_path)
    names = [s["name"] for s in box.schemas()]
    assert names == [
        "search_corpus",
        "find_leases",
        "get_lease",
        "read_lease_section",
        "extract_red_flags",
        "draft_redline",
        "submit_for_review",
        "recall_notes",
        "remember",
        "forget",
    ]
    for schema in box.schemas():
        assert len(schema["description"]) > 100 and schema["input_schema"]["properties"]
    assert [n for n, tool in box.tools.items() if tool.side_effect] == [
        "submit_for_review",
        "remember",
        "forget",
    ]
    assert not box.retry_safe("submit_for_review")


def test_the_agent_toolbox_sends_the_servers_schema_and_checks_the_result(tmp_path):
    box = toolbox_without_search(tmp_path)
    schema = next(s for s in box.schemas() if s["name"] == "get_lease")
    assert schema == next(t for t in REGISTRY.tools() if t["name"] == "get_lease")
    result = box.execute(ToolCall("1", "get_lease", {"lease_id": LEASE}))
    assert not result.is_error and '"sections"' in result.content
    renamed = box.execute(
        ToolCall("2", "find_leases", {}),
        mutate=lambda raw: {"items": raw["leases"]},
    )
    assert renamed.error_kind == "schema"


def test_the_registry_and_the_queue_work_for_the_same_user(tmp_path):
    other = RegistryClient(build_server(get_user("litigator")), user="litigator")
    with pytest.raises(ValueError, match="works for litigator, the agent for lawyer"):
        build_toolbox(
            CONFIG,
            registry=other,
            retriever=FakeRetriever(),
            warm=False,
            queue=ApprovalQueue(tmp_path / "queue.db"),
            memory=NoteStore(tmp_path / "memory.db"),
        )


def test_search_never_returns_a_lease_of_the_registry():
    for role in (None, "position", "wording", "law", "precedent", "market"):
        for versions in ("current", "all"):
            filters = search_filters(role, versions)
            assert not filters.matches({"type": "lease", "status": "current"})
            assert filters.to_qdrant().must_not[-1].key == "type"
    assert search_filters("market", "current").matches(
        {"type": "research", "status": "current"}
    )


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


def test_lease_tools_refuse_unknown_ids(tmp_path):
    box = toolbox_without_search(tmp_path)
    result = run(box, {"lease_id": "lease_1"}, "get_lease")
    assert result.is_error and "No lease lease_1" in result.content
    assert run(box, {"lease_id": "../etc"}, "get_lease").content.startswith(
        "Invalid arguments"
    )


class FakeGenerator:
    config = CONFIG

    def __init__(self):
        self.calls = 0

    def generate(self, red_flag, exclude_docs=()):
        # the lease itself and a lease closed to some of the entity (A: a court dispute)
        assert exclude_docs == ["lease_35532", LEASE]
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
    generator = FakeGenerator()
    draft = draft_redline(
        REGISTRY, generator, Drafts(), {LEASE, "lease_35532", "lease_55572"}
    )
    with pytest.raises(ToolError, match="not in lease_37032 word for word"):
        draft(
            DraftArgs(
                lease_id=LEASE, type="sublease_permitted", quote="Вигадана умова."
            )
        )
    assert generator.calls == 0
    quote = LeaseRegistry().sections(LEASE)[1].text.splitlines()[0]
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


def test_a_conversation_keeps_its_redlines_from_one_question_to_the_next(tmp_path):
    per_question = toolbox_without_search(tmp_path)
    assert per_question.on_request  # the drafts are reset at every question
    conversation = build_toolbox(
        CONFIG,
        registry=REGISTRY,
        retriever=FakeRetriever(),
        warm=False,
        queue=ApprovalQueue(tmp_path / "q2.db"),
        confirm=ScriptedConfirmer(),
        session=True,
        memory=NoteStore(tmp_path / "m2.db"),
    )
    assert conversation.on_request == []


def test_the_eval_checks_know_every_tool_of_the_toolbox(tmp_path):
    from lease_redflag_detector.agent.evaluate import TOOLS

    assert set(toolbox_without_search(tmp_path).tools) == TOOLS
