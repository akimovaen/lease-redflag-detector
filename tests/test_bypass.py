"""No way around a denial: an agent that tries every tool on a closed lease never gets
its text (stage 3, step 2.4).

A scripted model asks, as the lawyer, for the NDA lease through every tool the agent
has, and for a redline of an open lease on the same subject; the real toolbox, the
registry MCP server (in this process) and the redline search run, over the real
chunks of the corpus: the real search with BM25 and an in-memory Qdrant, each with
its own filters. Only the model weights are stand-ins: a lexical embedder (a vector of
the words of a text) and a reranker by shared words, so that a phrase of the lease
would come first in either path if a filter let it through; and the redline model,
never reached for the closed lease. Then no phrase of the lease may be anywhere in
what the tools returned, decoded from JSON. The head of legal, who may read it, gets
every phrase back, which shows the check sees a leak.
"""

import hashlib
import json
import re
from pathlib import Path

import numpy as np

from lease_redflag_detector.agent.confirm import ScriptedConfirmer
from lease_redflag_detector.agent.loop import (
    Agent,
    AgentConfig,
    Limits,
    Reply,
    ToolCall,
)
from lease_redflag_detector.agent.memory import NoteStore
from lease_redflag_detector.agent.queue import ApprovalQueue
from lease_redflag_detector.agent.registry import LeaseRegistry
from lease_redflag_detector.agent.registry_client import RegistryClient
from lease_redflag_detector.agent.registry_server import build_server
from lease_redflag_detector.agent.toolset import build_toolbox
from lease_redflag_detector.agent.users import get_user
from lease_redflag_detector.rag.redline import Redline, RedlineGenerator, Result
from lease_redflag_detector.rag.retrieve import Filters, Retriever, load_chunks

ROOT = Path(__file__).resolve().parents[1]

NDA, LITIGATION, OPEN = "lease_92441", "lease_35532", "lease_37032"
CONFIG = AgentConfig.load(ROOT / "configs" / "agent-haiku-v1.toml")
CHUNKS = load_chunks()
WORD = re.compile(r"\w{4,}")


def flat(text: str) -> str:
    return " ".join(text.split())


def phrases(lease_id: str, n: int = 6) -> list[str]:
    """Long lines of the lease: what would show that its text got out."""
    lines = [flat(line) for line in LeaseRegistry().text(lease_id).splitlines()]
    return sorted((line for line in lines if len(line) > 60), key=len)[-n:]


def decoded(content: str) -> str:
    """Every string of a tool result, as the model would read it: JSON escapes
    quotes, which would hide a leaked phrase from a plain search."""

    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for item in value.values():
                yield from strings(item)
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)

    try:
        return flat(" ".join(strings(json.loads(content))))
    except json.JSONDecodeError:
        return flat(content)


class LexicalEmbedder:
    """Hashed bag of words: similar texts get similar vectors, as with a model."""

    def vector(self, text: str) -> np.ndarray:
        v = np.zeros(512)
        for word in WORD.findall(text.casefold()):
            v[int(hashlib.md5(word.encode()).hexdigest(), 16) % 512] += 1
        return v / (np.linalg.norm(v) or 1)

    def passages(self, texts: list[str]) -> np.ndarray:
        return np.array([self.vector(t) for t in texts])

    def query(self, text: str) -> np.ndarray:
        return self.vector(text)


class OverlapReranker:
    def predict(self, pairs):
        return [
            0.5 + len(set(WORD.findall(q.casefold())) & set(WORD.findall(t.casefold())))
            for q, t in pairs
        ]


RETRIEVER = Retriever(
    CHUNKS,
    collection="bypass",
    embedder=LexicalEmbedder(),
    qdrant_path=None,
    reranker=OverlapReranker(),
)


def search_only(sources: set[str], excluded: set[str]):
    """RedlineGenerator.generate up to its model: the real search of its sources,
    recorded with what it was told to leave out, and a fixed answer instead of a model
    call."""

    def generate(self, red_flag, exclude_docs=()):
        excluded.update(exclude_docs)
        hits = self.search.search(red_flag, exclude_docs)
        sources.update(h.chunk.doc_id for role in hits.values() for h in role)
        output = Redline(
            verdict="concession",
            findings=[],
            risk="medium",
            risk_reason={"text": "—", "sources": []},
            proposed_clause=None,
            proposed_sources=[],
            gaps=[],
            conflicts=[],
        )
        return Result("ok", [], "", output, approval="юрист")

    return generate


class AllTools:
    """A model that asks for every tool at once, then answers."""

    name = "fake"
    errors = ()

    def __init__(self, calls: list[ToolCall]):
        self.calls = calls
        self.step = 0

    def call(self, system, messages, tools, final_only, timeout):
        self.step += 1
        if self.step == 1:
            return Reply(
                "", self.calls, [{"type": "tool_use", "id": c.id} for c in self.calls]
            )
        return Reply("Готово.", [], [{"type": "text", "text": "Готово."}])


def attempt(
    user: str,
    tmp_path,
    monkeypatch,
    extra: tuple[ToolCall, ...] = (),
    memory: NoteStore | None = None,
):
    """Every way to the NDA lease, as `user`, and `extra` calls: the tool events by
    call id, the documents the redline searches found and those it left out."""
    nda_text = phrases(NDA)
    open_quote = next(
        line.strip()
        for line in LeaseRegistry().text(OPEN).splitlines()
        if len(line.strip()) > 40
    )
    calls = [
        ToolCall("1", "find_leases", {}),
        ToolCall("2", "get_lease", {"lease_id": NDA}),
        ToolCall("3", "read_lease_section", {"lease_id": NDA, "section": 2}),
        ToolCall(
            "4", "search_corpus", {"query": nda_text[-1][:400], "versions": "all"}
        ),
        ToolCall("5", "search_corpus", {"query": nda_text[-2][:400], "role": "market"}),
        ToolCall("6", "extract_red_flags", {"lease_id": NDA}),
        ToolCall(
            "7",
            "draft_redline",
            {"lease_id": NDA, "type": "tenant_break_option", "quote": nda_text[-1]},
        ),
        ToolCall(
            "8",
            "draft_redline",
            {"lease_id": OPEN, "type": "tenant_break_option", "quote": open_quote},
        ),
        ToolCall("9", "submit_for_review", {"lease_id": NDA}),
        *extra,
    ]
    sources: set[str] = set()
    excluded: set[str] = set()
    monkeypatch.setattr(RedlineGenerator, "generate", search_only(sources, excluded))
    tools = build_toolbox(
        CONFIG.model_copy(update={"user": user}),
        registry=RegistryClient(build_server(get_user(user)), user=user),
        retriever=RETRIEVER,
        warm=False,
        queue=ApprovalQueue(tmp_path / "queue.db"),
        confirm=ScriptedConfirmer(True),
        memory=memory or NoteStore(tmp_path / "memory.db"),
    )
    agent = Agent(AllTools(calls), tools, "system", Limits(max_usd=1.0), "{reason}")
    events = agent.run("Покажи договір").trace.tool_calls()
    by_call = {c.id: e for c, e in zip(calls, events, strict=True)}
    return by_call, sources, excluded


def test_the_lawyer_gets_no_text_of_the_nda_lease_by_any_tool(tmp_path, monkeypatch):
    events, sources, excluded = attempt("lawyer", tmp_path, monkeypatch)
    for call in ("2", "3", "6", "7", "9"):  # every read of the lease, direct or not
        assert events[call]["error_kind"] == "denied", events[call]["name"]
    listed = events["1"]["content"]
    assert NDA in listed and "NDA" in listed  # listed as restricted, nothing more
    for call in ("4", "5"):
        assert events[call]["error_kind"] is None and NDA not in events[call]["content"]
    assert events["8"]["error_kind"] is None and sources  # the open lease's redline ran
    assert not {NDA, LITIGATION} & sources  # closed leases are no market practice
    assert {NDA, LITIGATION, OPEN} <= excluded
    everything = " ".join(decoded(e["content"]) for e in events.values())
    for phrase in phrases(NDA):
        assert phrase not in everything


def test_the_head_of_legal_reads_it_but_not_as_market_practice(tmp_path, monkeypatch):
    sections = len(LeaseRegistry().sections(NDA))
    every_section = tuple(
        ToolCall(f"s{n}", "read_lease_section", {"lease_id": NDA, "section": n})
        for n in range(1, sections + 1)
    )
    events, sources, excluded = attempt("head", tmp_path, monkeypatch, every_section)
    assert events["2"]["error_kind"] is None
    # the check finds every phrase in what the head may read: it would see a leak
    read = " ".join(decoded(events[c.id]["content"]) for c in every_section)
    assert all(phrase in read for phrase in phrases(NDA))
    # a redline goes to the approval queue, where others read it
    assert sources and NDA not in sources
    assert {NDA, LITIGATION} <= excluded
    for call in ("4", "5"):
        assert NDA not in events[call]["content"]


def test_without_the_filters_both_search_paths_bring_the_lease_first():
    query = phrases(NDA)[-1]
    for mode in ("bm25", "vector"):
        hits = RETRIEVER.search(query, mode, 1, Filters(status=None))
        assert hits[0].chunk.doc_id == NDA, mode


def test_the_lawyer_gets_no_note_about_the_nda_lease(tmp_path, monkeypatch):
    from lease_redflag_detector.agent.memory import policy_version

    store = NoteStore(tmp_path / "notes.db")
    secret = "Орендар просить знижку 40 % на перші два роки, не розголошувати."
    store.add(secret, "head", "ТОВ «Орендодавець»", policy_version(), NDA)
    calls = (
        ToolCall("n1", "recall_notes", {}),
        ToolCall("n2", "recall_notes", {"lease_id": NDA}),
        ToolCall("n3", "forget", {"note_id": "N-0001"}),
    )
    events, _, _ = attempt("lawyer", tmp_path, monkeypatch, calls, store)
    assert json.loads(events["n1"]["content"])["notes"] == []
    assert json.loads(events["n2"]["content"])["notes"] == []
    assert events["n3"]["is_error"]
    assert store.get("N-0001").status == "чинна"  # not forgotten
    everything = " ".join(decoded(e["content"]) for e in events.values())
    assert secret not in everything
    # the head of legal, who may read the lease, gets the note
    head_events, _, _ = attempt("head", tmp_path, monkeypatch, calls[:2], store)
    assert secret in decoded(head_events["n2"]["content"])
