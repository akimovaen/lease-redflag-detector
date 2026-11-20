"""The tools of the lawyer's agent, each doing one thing.

- search_corpus: the stage 2 search, by source role, over the documents in force or
  over every version;
- find_leases, get_lease, read_lease_section: the lease registry (`registry.py`);
- extract_red_flags: the stage 1 extractor on a lease from the registry;
- draft_redline: the stage 2 redline for one red flag of a lease. The verdict, risk,
  approval route and whether the lawyer must decide come from stage 2 and its code,
  not from the agent's own wording, so that later steps can rely on them.

The search runs in memory (`qdrant_path=None`) and writes new reranker scores to a
local cache, not to the committed one. Loading the embedding model and the reranker
takes longer than a tool call may, so `build_toolbox` warms them up first.
"""

import dataclasses
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from lease_redflag_detector.agent.loop import AgentConfig
from lease_redflag_detector.agent.registry import LeaseNotFound, LeaseRegistry
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
SEARCH_MARGIN_S = 10


def tool_client(config: RunConfig, tool_timeout_s: float) -> RunConfig:
    """The stage 1 or 2 config with API requests that fit in the tool's time limit."""
    timeout = (tool_timeout_s - SEARCH_MARGIN_S) / 2
    return config.model_copy(update={"timeout_s": timeout, "max_retries": 0})


LEASE_ID = r"^lease_\d+$"

RoleName = Literal["position", "wording", "law", "precedent", "market"]


# search_corpus


class SearchArgs(BaseModel):
    query: str = Field(
        min_length=3, max_length=500, description="Search query in Ukrainian."
    )
    role: RoleName | None = Field(
        None,
        description=(
            "Kind of source: position (the landlord's policy), wording (approved "
            "clauses), law, precedent (commercial committee decisions), market "
            "(research and signed leases). Omit to search every kind."
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
    filters = (
        next(r.filters for r in ROLES if r.name == role)
        if role
        else Filters(exclude_regimes=STATE_PROPERTY)
    )
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


# The lease registry


class FindArgs(BaseModel):
    party: str | None = Field(
        None, max_length=100, description="Part of the landlord's or tenant's name."
    )
    city: str | None = Field(None, max_length=100, description="Part of the city name.")


class LeaseSummary(BaseModel):
    lease_id: str
    title: str
    landlord: str
    tenant: str
    city: str
    date: str


class FindResult(BaseModel):
    leases: list[LeaseSummary]


class LeaseArgs(BaseModel):
    lease_id: str = Field(pattern=LEASE_ID, description="Lease id, e.g. lease_37032.")


class SectionTitle(BaseModel):
    number: int
    title: str


class LeaseInfo(LeaseSummary):
    sections: list[SectionTitle]


class SectionArgs(LeaseArgs):
    section: int = Field(ge=1, description="Section number from get_lease.")


class SectionText(BaseModel):
    lease_id: str
    number: int
    title: str
    text: str


def not_found(lease_id: str) -> ToolError:
    return ToolError(f"No lease {lease_id} in the registry; find_leases lists them.")


def find_leases(registry: LeaseRegistry):
    def run(args: FindArgs) -> FindResult:
        return FindResult(leases=registry.find(args.party, args.city))

    return run


def get_lease(registry: LeaseRegistry):
    def run(args: LeaseArgs) -> LeaseInfo:
        try:
            summary = registry.summary(args.lease_id)
            sections = registry.sections(args.lease_id)
        except LeaseNotFound:
            raise not_found(args.lease_id) from None
        return LeaseInfo(
            **summary,
            sections=[SectionTitle(number=s.number, title=s.title) for s in sections],
        )

    return run


def read_lease_section(registry: LeaseRegistry):
    def run(args: SectionArgs) -> SectionText:
        try:
            sections = registry.sections(args.lease_id)
        except LeaseNotFound:
            raise not_found(args.lease_id) from None
        if args.section > len(sections):
            raise ToolError(f"{args.lease_id} has {len(sections)} sections.")
        section = sections[args.section - 1]
        return SectionText(
            lease_id=args.lease_id,
            number=section.number,
            title=section.title,
            text=section.text,
        )

    return run


def lease_text(registry: LeaseRegistry, lease_id: str) -> str:
    try:
        return registry.text(lease_id)
    except LeaseNotFound:
        raise not_found(lease_id) from None


# extract_red_flags


class RedFlags(BaseModel):
    lease_id: str
    red_flags: list[RedFlag]
    terms: dict = Field(description="Parties, premises, term, rent and indexation.")


def extract_red_flags(registry: LeaseRegistry, config: RunConfig):
    extractor = make_extractor(config)

    def run(args: LeaseArgs) -> Priced:
        extraction = extractor.extract(lease_text(registry, args.lease_id))
        cost = cost_usd(config.model, extraction.input_tokens, extraction.output_tokens)
        if extraction.output is None:
            raise api_failure("Extraction failed", extraction.error, cost or 0.0)
        output = extraction.output.model_dump(mode="json")
        flags = output.pop("red_flags")
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


def draft_redline(registry: LeaseRegistry, generator: RedlineGenerator):
    def run(args: DraftArgs) -> Priced:
        if not quote_in_text(args.quote, lease_text(registry, args.lease_id)):
            raise ToolError(
                f"The quote is not in {args.lease_id} word for word; copy it from "
                "extract_red_flags or read_lease_section."
            )
        red_flag = RedFlag(type=args.type, quote=args.quote)
        result = generator.generate(red_flag, exclude_doc=args.lease_id)
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
        return Priced(draft, cost or 0.0)

    return run


def build_toolbox(
    config: AgentConfig,
    registry: LeaseRegistry | None = None,
    retriever: Retriever | None = None,
    warm: bool = True,
) -> Toolbox:
    registry = registry or LeaseRegistry()
    retriever = retriever or Retriever(
        load_chunks(),
        collection="agent",
        qdrant_path=None,
        reranker=RerankScores(local_dir=LOCAL_RERANK),
    )
    if warm:
        retriever.search("орендна плата", k=1)  # loads both models
    generator = RedlineGenerator(
        tool_client(RunConfig.load(ROOT / config.redline), DRAFT_TIMEOUT_S),
        RedlineSearch(retriever),
    )
    extraction = tool_client(
        RunConfig.load(ROOT / config.extraction), EXTRACT_TIMEOUT_S
    )
    return Toolbox(
        [
            Tool(
                "search_corpus",
                "tools/search_corpus_v1",
                SearchArgs,
                SearchResult,
                search_corpus(retriever),
            ),
            Tool(
                "find_leases",
                "tools/find_leases_v1",
                FindArgs,
                FindResult,
                find_leases(registry),
            ),
            Tool(
                "get_lease",
                "tools/get_lease_v1",
                LeaseArgs,
                LeaseInfo,
                get_lease(registry),
            ),
            Tool(
                "read_lease_section",
                "tools/read_lease_section_v1",
                SectionArgs,
                SectionText,
                read_lease_section(registry),
            ),
            Tool(
                "extract_red_flags",
                "tools/extract_red_flags_v1",
                LeaseArgs,
                RedFlags,
                extract_red_flags(registry, extraction),
                timeout_s=EXTRACT_TIMEOUT_S,
            ),
            Tool(
                "draft_redline",
                "tools/draft_redline_v1",
                DraftArgs,
                Draft,
                draft_redline(registry, generator),
                timeout_s=DRAFT_TIMEOUT_S,
            ),
        ]
    )
