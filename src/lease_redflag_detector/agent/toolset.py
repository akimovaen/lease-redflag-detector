"""The tools of the lawyer's agent, each doing one thing.

- search_corpus: the stage 2 search, by source role, over the documents in force or
  over every version. It never returns a lease of the registry, so that a lease is
  read only through the registry and its access rights;
- find_leases, get_lease, read_lease_section: the lease registry, tools of its MCP
  server (`registry_server.py`) with the descriptions and schemas the server gives;
- extract_red_flags: the stage 1 extractor on a lease the registry server gives;
- draft_redline: the stage 2 redline for one red flag of a lease, with signed leases
  as market practice: only those every user of the lawyer's entity may read, as the
  registry says, and never the lease itself. The verdict, risk,
  approval route and whether the lawyer must decide come from stage 2 and its code,
  not from the agent's own wording, so that later steps can rely on them;
- submit_for_review: the one tool with a side effect. It puts a lease's contested
  points on the approval queue (`queue.py`) after the lawyer confirms (`confirm.py`).
  The model names only the lease: the points are the redlines drafted in this
  request, so the model cannot soften a verdict on its way to the committee.

The search runs in memory (`qdrant_path=None`) and writes new reranker scores to a
local cache, not to the committed one. Loading the embedding model and the reranker
takes longer than a tool call may, so `build_toolbox` warms them up first.
"""

import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from lease_redflag_detector.agent.confirm import Confirmer, TerminalConfirmer
from lease_redflag_detector.agent.loop import AgentConfig, require_price
from lease_redflag_detector.agent.queue import (
    ADDRESSEE,
    RISKS,
    VERDICTS,
    ApprovalQueue,
)
from lease_redflag_detector.agent.registry import (
    FindArgs,
    FindResult,
    LeaseArgs,
    LeaseInfo,
    SectionArgs,
    SectionText,
)
from lease_redflag_detector.agent.registry_client import RegistryClient
from lease_redflag_detector.agent.registry_server import NAME
from lease_redflag_detector.agent.tools import (
    Priced,
    Tool,
    Toolbox,
    ToolError,
    api_failure,
)
from lease_redflag_detector.extraction.extractor import RunConfig
from lease_redflag_detector.extraction.metrics import cost_usd
from lease_redflag_detector.extraction.quotes import quote_in_text
from lease_redflag_detector.extraction.run import make_extractor
from lease_redflag_detector.extraction.schema import RedFlag, RedFlagType
from lease_redflag_detector.rag.redline import RedlineGenerator
from lease_redflag_detector.rag.redline_search import (
    MIN_SCORE,
    ROLES,
    STATE_PROPERTY,
    RedlineSearch,
)
from lease_redflag_detector.rag.retrieve import (
    Filters,
    RerankScores,
    Retriever,
    load_chunks,
)

ROOT = Path(__file__).resolve().parents[3]
LOCAL_RERANK = ROOT / "data" / "processed" / "rerank_local"
# Time limits of the tools that call a model. Both may make two calls (an answer and
# one repair), so each API request gets less than half, with no retries by the client:
# a request that outlived its tool would still be paid for, unseen by the budget.
# Retrying is the loop's decision, not the client's.
EXTRACT_TIMEOUT_S = 120
DRAFT_TIMEOUT_S = 90
# The registry client gives up after its own timeout (registry_client.TIMEOUT_S), first.
REGISTRY_TIMEOUT_S = 20
SEARCH_MARGIN_S = 10


def tool_client(config: RunConfig, tool_timeout_s: float) -> RunConfig:
    """The stage 1 or 2 config with API requests that fit in the tool's time limit."""
    timeout = (tool_timeout_s - SEARCH_MARGIN_S) / 2
    return config.model_copy(update={"timeout_s": timeout, "max_retries": 0})


RoleName = Literal["position", "wording", "law", "precedent", "market"]


# search_corpus

# Document types that only the lease registry gives (corpus documents of type lease).
REGISTRY_TYPES = ["lease"]


class SearchArgs(BaseModel):
    query: str = Field(
        min_length=3, max_length=500, description="Search query in Ukrainian."
    )
    role: RoleName | None = Field(
        None,
        description=(
            "Kind of source: position (the landlord's policy), wording (approved "
            "clauses), law, precedent (commercial committee decisions), market "
            "(market research). Omit to search every kind."
        ),
    )
    versions: Literal["current", "all"] = Field(
        "current",
        description="current: documents in force only; all: outdated versions too.",
    )
    k: int = Field(5, ge=1, le=8, description="How many fragments to return.")


class Fragment(BaseModel):
    chunk_id: str
    document: str
    section: str
    type: str
    status: str
    date: str
    text: str


class SearchResult(BaseModel):
    fragments: list[Fragment]


def search_filters(role: str | None, versions: str) -> Filters:
    """The leases of the registry are never found: a lease is read only through the
    registry, which checks who may read it."""
    filters = (
        next(r.filters for r in ROLES if r.name == role)
        if role
        else Filters(exclude_regimes=STATE_PROPERTY)
    )
    filters = dataclasses.replace(filters, exclude_types=REGISTRY_TYPES)
    return dataclasses.replace(filters, status=None) if versions == "all" else filters


def search_corpus(retriever: Retriever):
    def run(args: SearchArgs) -> SearchResult:
        hits = retriever.search(
            args.query, k=args.k, filters=search_filters(args.role, args.versions)
        )
        return SearchResult(
            fragments=[
                Fragment(
                    chunk_id=hit.chunk.id,
                    document=hit.chunk.meta.get("title", hit.chunk.doc_id),
                    section=hit.chunk.section,
                    type=hit.chunk.meta.get("type", ""),
                    status=hit.chunk.meta.get("status", ""),
                    date=str(hit.chunk.meta.get("date", "")),
                    text=hit.chunk.text,
                )
                for hit in hits
                if hit.score >= MIN_SCORE
            ]
        )

    return run


# The lease registry: tools of its MCP server


def registry_tool(registry: RegistryClient, name: str, args: type[BaseModel], result):
    """A registry tool as the server describes it; the call goes to the server."""
    spec = next((t for t in registry.tools() if t["name"] == name), None)
    if spec is None:
        raise RuntimeError(f"The lease registry server has no tool {name}.")

    def run(validated: BaseModel) -> dict:
        return registry.call(name, validated.model_dump(exclude_none=True))

    return Tool(name, NAME, args, result, run, spec=spec, timeout_s=REGISTRY_TIMEOUT_S)


# extract_red_flags


class RedFlags(BaseModel):
    lease_id: str
    red_flags: list[RedFlag]
    terms: dict = Field(description="Parties, premises, term, rent and indexation.")


def extract_red_flags(registry: RegistryClient, config: RunConfig, drafts: "Drafts"):
    extractor = make_extractor(config)

    def run(args: LeaseArgs) -> Priced:
        extraction = extractor.extract(registry.text(args.lease_id))
        cost = cost_usd(config.model, extraction.input_tokens, extraction.output_tokens)
        if extraction.output is None:
            raise api_failure("Extraction failed", extraction.error, cost or 0.0)
        output = extraction.output.model_dump(mode="json")
        flags = output.pop("red_flags")
        drafts.flags[args.lease_id] = [(f["type"], f["quote"]) for f in flags]
        return Priced(
            RedFlags(lease_id=args.lease_id, red_flags=flags, terms=output), cost or 0.0
        )

    return run


# draft_redline


class DraftArgs(LeaseArgs):
    type: RedFlagType
    quote: str = Field(
        min_length=10, description="The clause, copied verbatim from the lease."
    )


class Claim(BaseModel):
    text: str
    sources: list[str]


class SourceRef(BaseModel):
    id: str
    role: str
    document: str
    section: str


class Draft(BaseModel):
    lease_id: str
    verdict: str
    risk: str
    risk_reason: Claim
    findings: list[Claim]
    proposed_clause: str | None
    proposed_sources: list[str]
    gaps: list[str]
    conflicts: list[Claim]
    approval: str
    needs_decision: bool
    sources: list[SourceRef]


class Drafts:
    """What the current request found for each lease: its red flags (if extracted)
    and the redlines drafted, by clause."""

    def __init__(self):
        self.by_lease: dict[str, dict[tuple[str, str], Draft]] = {}
        self.flags: dict[str, list[tuple[str, str]]] = {}

    def reset(self) -> None:
        self.by_lease.clear()
        self.flags.clear()

    def add(self, args: DraftArgs, draft: Draft) -> None:
        self.by_lease.setdefault(args.lease_id, {})[(args.type, args.quote)] = draft

    def without_redline(self, lease_id: str) -> int:
        """Red flags extracted from the lease that have no redline; a redline counts
        for a flag of its type whose quote holds its quote or is held in it."""
        drafted = self.by_lease.get(lease_id, {})
        return sum(
            not any(t == flag_type and (q in quote or quote in q) for t, q in drafted)
            for flag_type, quote in self.flags.get(lease_id, [])
        )


def draft_redline(
    registry: RegistryClient,
    generator: RedlineGenerator,
    drafts: Drafts,
    corpus_leases: set[str],
):
    """`corpus_leases`: the registry leases in the search corpus. A redline uses
    one as market practice only if every user of the lawyer's entity may read it:
    the redline goes to the approval queue, where others read it."""

    def run(args: DraftArgs) -> Priced:
        if not quote_in_text(args.quote, registry.text(args.lease_id)):
            raise ToolError(
                f"The quote is not in {args.lease_id} word for word; copy it from "
                "extract_red_flags or read_lease_section."
            )
        red_flag = RedFlag(type=args.type, quote=args.quote)
        # Never the lease itself, nor a lease closed to anyone of the entity.
        excluded = corpus_leases - (registry.shared() - {args.lease_id})
        result = generator.generate(red_flag, exclude_docs=sorted(excluded))
        cost = cost_usd(
            generator.config.model, result.input_tokens, result.output_tokens
        )
        if result.output is None:
            raise api_failure("No valid redline", result.error, cost or 0.0)
        output = result.output.model_dump(mode="json")
        draft = Draft(
            lease_id=args.lease_id,
            **output,
            approval=result.approval,
            needs_decision=result.needs_decision,
            sources=[
                SourceRef(
                    id=s.id,
                    role=s.role,
                    document=s.chunk.meta.get("title", s.chunk.doc_id),
                    section=s.chunk.section,
                )
                for s in result.sources
            ],
        )
        drafts.add(args, draft)
        return Priced(draft, cost or 0.0)

    return run


# submit_for_review

TO_APPROVE = {"concession", "beyond_concessions"}


class SubmitArgs(LeaseArgs):
    pass


class Submission(BaseModel):
    lease_id: str
    created: bool
    request_id: str | None
    status: str
    replaces: str | None = None
    points: int = 0
    # Red flags of the lease left out because they have no redline.
    without_redline: int = 0
    # Whether the lawyer confirmed; None when not asked (the request existed).
    confirmed: bool | None = None
    confirmation: str | None = None  # what the lawyer was shown
    message: str


def queue_items(drafts: dict[tuple[str, str], Draft]) -> list[dict]:
    """The points of a request: those to approve (a concession, beyond concessions,
    or anything the lawyer must decide) and the unacceptable ones for information.
    Compliant points are left out."""
    items = []
    for (flag_type, quote), draft in drafts.items():
        if draft.needs_decision or draft.verdict in TO_APPROVE:
            section = "погодження"
        elif draft.verdict == "unacceptable":
            section = "до відома"
        else:
            continue
        cited = set(draft.proposed_sources) | {
            s for claim in draft.findings for s in claim.sources
        }
        items.append(
            {
                "section": section,
                "type": flag_type,
                "quote": quote,
                "verdict": draft.verdict,
                "risk": draft.risk,
                "needs_decision": draft.needs_decision,
                "gaps": draft.gaps,
                "proposed_clause": draft.proposed_clause,
                "approval": draft.approval,
                "sources": [
                    f"{s.document}, {s.section}" for s in draft.sources if s.id in cited
                ],
            }
        )
    return sorted(items, key=lambda i: (i["section"], i["type"], i["quote"]))


def idempotency_key(lease_id: str, items: list[dict]) -> str:
    """The same lease with the same points and verdicts is the same request, even if
    a rerun words the changed clauses differently."""
    points = [(i["type"], i["quote"], i["verdict"]) for i in items]
    data = json.dumps([lease_id, points], ensure_ascii=False)
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def confirmation(
    title: str, lease_id: str, items: list[dict], replaces, without_redline: int
) -> str:
    def line(n: int, item: dict) -> str:
        # The wording of point 10.5 of the policy (Amendment 1).
        decision = (
            " · потребує додаткового аналізу юриста" if item["needs_decision"] else ""
        )
        quote = item["quote"][:90] + ("…" if len(item["quote"]) > 90 else "")
        return (
            f"   {n}. {item['type']} · {VERDICTS[item['verdict']]} · ризик "
            f"{RISKS.get(item['risk'], item['risk'])}{decision}\n      «{quote}»"
        )

    lines = [
        "Створити заявку на погодження?",
        f"  Договір: {lease_id} · {title}",
        f"  Кому: {ADDRESSEE}",
        "  Пункти на погодження:",
    ]
    to_approve = [i for i in items if i["section"] == "погодження"]
    lines += [line(n, i) for n, i in enumerate(to_approve, 1)]
    info = [i for i in items if i["section"] == "до відома"]
    if info:
        lines.append("  До відома (неприйнятні умови, не погоджуються):")
        lines += [line(n, i) for n, i in enumerate(info, 1)]
    if replaces:
        lines.append(f"  Замінить заявку {replaces.id}, яка ще очікує.")
    if without_redline:
        lines.append(
            f"  ⚠ Червоних прапорців без redline: {without_redline}; "
            "у заявку вони не потрапили."
        )
    return "\n".join(lines)


def submit_for_review(
    registry: RegistryClient,
    drafts: Drafts,
    queue: ApprovalQueue,
    confirm: Confirmer,
    user: str,
):
    def run(args: SubmitArgs) -> Submission:
        title = registry.summary(args.lease_id)["title"]
        lease_drafts = drafts.by_lease.get(args.lease_id)
        if not lease_drafts:
            raise ToolError(
                f"No redlines of {args.lease_id} in this request: run draft_redline "
                "for its red flags first."
            )
        items = queue_items(lease_drafts)
        if not any(i["section"] == "погодження" for i in items):
            raise ToolError(
                f"Nothing in {args.lease_id} needs approval: its points comply with "
                "the policy or are unacceptable, which the committee does not approve."
            )
        key = idempotency_key(args.lease_id, items)
        missing = drafts.without_redline(args.lease_id)
        existing = queue.pending_with_key(key)
        if existing:
            return Submission(
                lease_id=args.lease_id,
                created=False,
                request_id=existing.id,
                status=existing.status,
                points=len(existing.items),
                without_redline=missing,
                message="This request is already pending; nothing new was created.",
            )
        question = confirmation(
            title, args.lease_id, items, queue.pending(args.lease_id), missing
        )
        if not confirm(question):
            return Submission(
                lease_id=args.lease_id,
                created=False,
                request_id=None,
                status="not confirmed",
                points=len(items),
                without_redline=missing,
                confirmed=False,
                confirmation=question,
                message="The lawyer did not confirm; nothing was created.",
            )
        request, created = queue.create(args.lease_id, key, items, user)
        return Submission(
            lease_id=args.lease_id,
            created=created,
            request_id=request.id,
            status=request.status,
            replaces=request.replaces,
            points=len(items),
            without_redline=missing,
            confirmed=True,
            confirmation=question,
            message="Created." if created else "This request is already pending.",
        )

    return run


def build_toolbox(
    config: AgentConfig,
    registry: RegistryClient | None = None,
    retriever: Retriever | None = None,
    warm: bool = True,
    queue: ApprovalQueue | None = None,
    confirm: Confirmer | None = None,
) -> Toolbox:
    registry = registry or RegistryClient(user=config.user)
    # The registry reads as one user and the queue records another: never.
    if registry.user != config.user:
        raise ValueError(
            f"The registry works for {registry.user}, the agent for {config.user}."
        )
    queue = queue or ApprovalQueue()
    confirm = confirm or TerminalConfirmer()
    drafts = Drafts()
    retriever = retriever or Retriever(
        load_chunks(),
        collection="agent",
        qdrant_path=None,
        reranker=RerankScores(local_dir=LOCAL_RERANK),
    )
    corpus_leases = {
        chunk.doc_id
        for chunk in retriever.chunks
        if chunk.meta.get("type") in REGISTRY_TYPES
    }
    if warm:
        retriever.search("орендна плата", k=1)  # loads both models
    redline = tool_client(RunConfig.load(ROOT / config.redline), DRAFT_TIMEOUT_S)
    extraction = tool_client(
        RunConfig.load(ROOT / config.extraction), EXTRACT_TIMEOUT_S
    )
    require_price(redline.model)
    require_price(extraction.model)
    generator = RedlineGenerator(redline, RedlineSearch(retriever))
    return Toolbox(
        [
            Tool(
                "search_corpus",
                "tools/search_corpus_v2",
                SearchArgs,
                SearchResult,
                search_corpus(retriever),
            ),
            registry_tool(registry, "find_leases", FindArgs, FindResult),
            registry_tool(registry, "get_lease", LeaseArgs, LeaseInfo),
            registry_tool(registry, "read_lease_section", SectionArgs, SectionText),
            Tool(
                "extract_red_flags",
                "tools/extract_red_flags_v1",
                LeaseArgs,
                RedFlags,
                extract_red_flags(registry, extraction, drafts),
                timeout_s=EXTRACT_TIMEOUT_S,
            ),
            Tool(
                "draft_redline",
                "tools/draft_redline_v1",
                DraftArgs,
                Draft,
                draft_redline(registry, generator, drafts, corpus_leases),
                timeout_s=DRAFT_TIMEOUT_S,
            ),
            Tool(
                "submit_for_review",
                "tools/submit_for_review_v1",
                SubmitArgs,
                Submission,
                submit_for_review(registry, drafts, queue, confirm, config.user),
                side_effect=True,
                retry_safe=False,
            ),
        ],
        on_request=[drafts.reset],
    )
