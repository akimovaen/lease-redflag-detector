"""Redline proposals for red flags, built only from the chunks the role search found.

For a red flag of stage 1 (type and clause) the model gets the chunks of every source
role, numbered S1, S2, … and returns a `Redline`: where the clause stands against the
landlord's policy, the findings with the sources behind each, the points the sources do
not settle, the risk level, and the changed clause based on the approved wording.

Two parts of the policy apply to every red flag but share no words with the clause, so
the search never finds them: the risk criteria and levels (1.6–1.7) and who approves
deviations (section 10, as Amendment 1 restates it from 01.10.2026). They are always in
the context, from the latest document that holds them.

An answer with any gap, or with the verdict not_covered, needs the lawyer's further
analysis (`needs_decision`): the code marks every point the model names as open, so the
model does not have to choose between a verdict and not_covered. By point 10.5 of the
policy such a point still goes to the committee, marked, rather than waiting.

Who approves the clause follows from the verdict by section 10 of the policy (the
commercial committee since Amendment 1) and is computed here, not asked of the model. The risk level starts from a default per red flag
type (`DEFAULT_RISK`); the model may move it and must say why.

An answer is valid when it matches the schema, every source it cites is in the context,
every claim cites one, and a changed clause is given exactly when one is needed. If it
is not, the model gets the problems back and one chance to fix them, as in stage 1.

Prompts rag/v4 and rag/v5 tried marking each gap that changes the verdict and
requiring not_covered for it; neither was kept (REPORT.md, error 2). Their schema and
check are in commit 5c6bae2.
"""

import time
from collections.abc import Collection
from dataclasses import dataclass, field
from enum import StrEnum

import anthropic
from pydantic import BaseModel, Field, ValidationError

from lease_redflag_detector.extraction.extractor import (
    Completion,
    RunConfig,
    load_prompt,
)
from lease_redflag_detector.extraction.schema import RedFlag, RedFlagType
from lease_redflag_detector.markup import attr, neutral
from lease_redflag_detector.rag.chunking import Chunk
from lease_redflag_detector.rag.redline_search import RedlineSearch
from lease_redflag_detector.rag.retrieve import Hit

REPAIR_PROMPT = "rag/repair_v1"
# Policy points that are always in the context, found by how their text starts.
FIXED_POINTS = ("1.6.", "1.7.", "10.1.")
# Retrieved chunks over this many tokens are dropped, the lowest reranker score first;
# the fixed policy points are always kept.
CONTEXT_TOKENS = 6000


class Verdict(StrEnum):
    COMPLIANT = "compliant"
    CONCESSION = "concession"
    BEYOND_CONCESSIONS = "beyond_concessions"
    UNACCEPTABLE = "unacceptable"
    NOT_COVERED = "not_covered"


class Risk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# Agreed with the landlord's lawyer: every type changes payments or the term (high),
# except sublease, which shifts risks to third parties without changing payments.
DEFAULT_RISK = {
    RedFlagType.INDEXATION_LIMITED: Risk.HIGH,
    RedFlagType.TENANT_BREAK_OPTION: Risk.HIGH,
    RedFlagType.SERVICE_CHARGES_LIMITED: Risk.HIGH,
    RedFlagType.LANDLORD_REPAIRS: Risk.HIGH,
    RedFlagType.SUBLEASE_PERMITTED: Risk.MEDIUM,
}

# Section 10 of the policy as Amendment 1 (in force from 01.10.2026) restates it.
APPROVAL = {
    Verdict.COMPLIANT: "юрист (п. 10.1)",
    Verdict.CONCESSION: (
        "комерційний комітет за письмовим висновком юриста (п. 10.2 в редакції "
        "Змін № 1)"
    ),
    Verdict.BEYOND_CONCESSIONS: (
        "комерційний комітет — лише для якірного орендаря і в межах, які допускають "
        "Політика та бібліотека формулювань (п. 10.3 в редакції Змін № 1); інакше не "
        "погоджується"
    ),
    Verdict.UNACCEPTABLE: "не погоджується (п. 10.4)",
    Verdict.NOT_COVERED: (
        "Політика не визначає; подається до комерційного комітету з позначкою, що "
        "пункт потребує додаткового аналізу юриста (п. 10.5 в редакції Змін № 1)"
    ),
}
# Point 10.5: a point with open questions goes into the request too, marked; an
# unacceptable one, which the committee does not approve, only for its information.
FURTHER_ANALYSIS = (
    "потребує додаткового аналізу юриста — подається до комітету з цією позначкою "
    "(п. 10.5 в редакції Змін № 1); за вердиктом: "
)
FOR_INFORMATION = (
    "для відома комітету, з позначкою, що пункт потребує додаткового аналізу юриста "
    "(п. 10.5 в редакції Змін № 1); "
)


def approval(verdict: str, has_gaps: bool) -> str:
    """Who approves the clause. A point with open questions is not held back until the
    lawyer settles them: by point 10.5 it goes into the request to the committee,
    marked as needing the lawyer's further analysis, with the route of its verdict."""
    route = APPROVAL[Verdict(verdict)]
    if not has_gaps or verdict == Verdict.NOT_COVERED:
        return route
    if verdict == Verdict.UNACCEPTABLE:
        return FOR_INFORMATION + route
    return FURTHER_ANALYSIS + route


def needs_decision(verdict: str, gaps: list) -> bool:
    """Any gap marks the point as needing the lawyer's further analysis, whatever its
    verdict; so does not_covered, which the policy does not settle (point 10.5)."""
    return bool(gaps) or verdict == Verdict.NOT_COVERED


NEEDS_CLAUSE = {Verdict.BEYOND_CONCESSIONS, Verdict.UNACCEPTABLE}
NO_CLAUSE = {Verdict.COMPLIANT, Verdict.NOT_COVERED}


class Claim(BaseModel):
    text: str = Field(description="One statement, in Ukrainian.")
    sources: list[str] = Field(
        description="Ids of the context sources that support the statement, e.g. S3."
    )


def gap_line(gap: dict | str) -> str:
    """A saved gap as one line: a string, or in the runs of prompts rag/v4 and rag/v5
    (commit 5c6bae2) an object marked whether it changes the verdict."""
    if isinstance(gap, str):
        return gap
    return gap["text"] + (" (змінює вердикт)" if gap["changes_verdict"] else "")


class Redline(BaseModel):
    verdict: Verdict = Field(
        description=(
            "Where the clause stands against the policy in force: compliant (the base "
            "position), concession (within an allowed concession), beyond_concessions "
            "(beyond the allowed concessions but not on the unacceptable list), "
            "unacceptable (on the unacceptable list or against mandatory law), "
            "not_covered (the sources say nothing on the point)."
        )
    )
    findings: list[Claim] = Field(
        description=(
            "What the clause does, which terms of the policy (base position, "
            "concessions, unacceptable terms) and which rules of law it meets or "
            "breaks, and relevant committee decisions. Most important first."
        )
    )
    risk: Risk = Field(description="Risk level by policy point 1.7.")
    risk_reason: Claim = Field(
        description=(
            "Which criteria of policy point 1.6 the clause touches and why the level "
            "is what it is; if it differs from the default level, why."
        )
    )
    proposed_clause: str | None = Field(
        description=(
            "The changed clause in Ukrainian, based on the approved wording from the "
            "sources. Required for beyond_concessions and unacceptable, optional for "
            "concession, null for compliant and not_covered."
        )
    )
    proposed_sources: list[str] = Field(
        description="Sources the changed clause is based on; empty if there is none."
    )
    gaps: list[str] = Field(
        description=(
            "Points of the clause the sources do not settle, in Ukrainian, without "
            "sources. Empty if they settle all of them."
        )
    )
    conflicts: list[Claim] = Field(
        description=(
            "Where the sources disagree, which one prevails and why. Empty if they "
            "agree."
        )
    )


OUTPUT_FORMAT = {
    "type": "json_schema",
    "schema": anthropic.transform_schema(Redline.model_json_schema()),
}

ROLE_NAMES = {
    "position": "політика орендодавця",
    "wording": "бібліотека погоджених формулювань",
    "law": "закон",
    "precedent": "рішення комерційного комітету",
    "market": "ринкова практика (лише фон)",
}


@dataclass
class Source:
    id: str
    role: str
    chunk: Chunk
    score: float | None  # reranker score; None for the fixed policy points


def fixed_chunks(chunks: list[Chunk]) -> list[Chunk]:
    """The chunks of the policy in force that hold the `FIXED_POINTS`. When an
    amendment restates a point, only the latest document's chunk is kept, so that the
    model reads the route in force, not the one it replaced."""
    holders: dict[str, list[Chunk]] = {}
    for chunk in chunks:
        if chunk.meta.get("type") != "policy" or chunk.meta.get("status") != "current":
            continue
        lines = chunk.text.splitlines()
        for point in FIXED_POINTS:
            if any(line.startswith(point) for line in lines):
                holders.setdefault(point, []).append(chunk)
    keep = set()
    for found in holders.values():
        latest = max(str(chunk.meta.get("date", "")) for chunk in found)
        keep |= {c.id for c in found if str(c.meta.get("date", "")) == latest}
    return [chunk for chunk in chunks if chunk.id in keep]


def build_sources(
    hits: dict[str, list[Hit]], fixed: list[Chunk], budget: int = CONTEXT_TOKENS
) -> list[Source]:
    """Number the retrieved chunks by role, then the fixed policy points; a chunk is
    listed once. Retrieved chunks over the token budget are dropped, lowest score
    first."""
    retrieved = [(role, hit) for role, role_hits in hits.items() for hit in role_hits]
    fixed_ids = {chunk.id for chunk in fixed}
    used = sum(chunk.tokens for chunk in fixed)
    keep = set()
    for role, hit in sorted(retrieved, key=lambda item: -item[1].score):
        if hit.chunk.id in fixed_ids or used + hit.chunk.tokens > budget:
            continue
        keep.add((role, hit.chunk.id))
        used += hit.chunk.tokens
    sources, seen = [], set()
    for role, hit in retrieved:
        if (role, hit.chunk.id) in keep and hit.chunk.id not in seen:
            seen.add(hit.chunk.id)
            sources.append(Source("", role, hit.chunk, hit.score))
    sources += [Source("", "position", chunk, None) for chunk in fixed]
    for number, source in enumerate(sources, start=1):
        source.id = f"S{number}"
    return sources


def render_context(red_flag: RedFlag, sources: list[Source]) -> str:
    blocks = [
        f'<source id="{s.id}" role="{ROLE_NAMES[s.role]}" '
        f'document="{attr(s.chunk.meta.get("title", s.chunk.doc_id))}" '
        f'section="{attr(s.chunk.section)}">\n{neutral(s.chunk.text)}\n</source>'
        for s in sources
    ]
    return "\n\n".join(
        [
            "<sources>",
            *blocks,
            "</sources>",
            (
                f'<red_flag type="{red_flag.type}" '
                f'default_risk="{DEFAULT_RISK[red_flag.type]}">\n'
                f"{neutral(red_flag.quote)}\n</red_flag>"
            ),
        ]
    )


def validate(raw: str, ids: set[str]) -> tuple[Redline | None, str | None]:
    """Parse the answer, or return the problems found."""
    try:
        output = Redline.model_validate_json(raw)
    except ValidationError as e:
        return None, str(e)
    problems = []
    claims = [("findings", c) for c in output.findings] + [
        ("conflicts", c) for c in output.conflicts
    ]
    claims.append(("risk_reason", output.risk_reason))
    for name, claim in claims:
        if not claim.sources:
            problems.append(f"{name}: no source for {claim.text[:100]!r}")
        unknown = [s for s in claim.sources if s not in ids]
        if unknown:
            problems.append(
                f"{name}: unknown sources {unknown} for {claim.text[:100]!r}"
            )
    if not output.findings:
        problems.append("findings: empty")
    unknown = [s for s in output.proposed_sources if s not in ids]
    if unknown:
        problems.append(f"proposed_sources: unknown sources {unknown}")
    if output.verdict in NEEDS_CLAUSE and not output.proposed_clause:
        problems.append(f"proposed_clause: required for verdict {output.verdict}")
    if output.verdict in NO_CLAUSE and output.proposed_clause:
        problems.append(f"proposed_clause: must be null for verdict {output.verdict}")
    if output.proposed_clause and not output.proposed_sources:
        problems.append("proposed_sources: empty for a changed clause")
    return (None, "\n".join(problems)) if problems else (output, None)


@dataclass
class Result:
    status: str  # "ok" or "failed"
    sources: list[Source]
    raw: str
    output: Redline | None = None
    error: str | None = None
    approval: str | None = None
    latency_s: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    extra: dict = field(default_factory=dict)

    @property
    def needs_decision(self) -> bool:
        return bool(self.output) and needs_decision(
            self.output.verdict, self.output.gaps
        )


class RedlineGenerator:
    def __init__(self, config: RunConfig, search: RedlineSearch):
        self.config = config
        self.search = search
        self.system = load_prompt(config.prompt)
        self.repair = load_prompt(REPAIR_PROMPT)
        self.fixed = fixed_chunks(search.retriever.chunks)
        self.client = anthropic.Anthropic(
            timeout=config.timeout_s, max_retries=config.max_retries
        )

    def complete(self, messages: list[dict]) -> Completion:
        response = self.client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            system=self.system,
            messages=messages,
            output_config={"format": OUTPUT_FORMAT, **self.config.sampling},
        )
        return Completion(
            raw="".join(b.text for b in response.content if b.type == "text"),
            truncated=response.stop_reason == "max_tokens",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason,
        )

    def check(self, completion: Completion, ids: set[str]):
        if completion.truncated:
            return None, "the answer was cut off at the output token limit"
        return validate(completion.raw, ids)

    def generate(self, red_flag: RedFlag, exclude_docs: Collection[str] = ()) -> Result:
        """`exclude_docs`: documents kept out of the sources (`RedlineSearch.search`)."""
        start = time.perf_counter()
        sources = build_sources(self.search.search(red_flag, exclude_docs), self.fixed)
        search_s = time.perf_counter() - start
        ids = {source.id for source in sources}
        messages = [{"role": "user", "content": render_context(red_flag, sources)}]
        completions: list[Completion] = []
        first_error = None
        try:
            completions.append(self.complete(messages))
            output, error = self.check(completions[-1], ids)
            if error:
                first_error = error
                messages += [
                    {"role": "assistant", "content": completions[-1].raw},
                    {"role": "user", "content": self.repair.replace("{errors}", error)},
                ]
                completions.append(self.complete(messages))
                output, error = self.check(completions[-1], ids)
        except anthropic.APIError as e:
            output, error = None, f"{type(e).__name__}: {e}"
        return Result(
            status="ok" if output else "failed",
            sources=sources,
            raw=completions[-1].raw if completions else "",
            output=output,
            error=error,
            approval=approval(output.verdict, bool(output.gaps)) if output else None,
            latency_s=time.perf_counter() - start,
            input_tokens=sum(c.input_tokens for c in completions),
            output_tokens=sum(c.output_tokens for c in completions),
            extra={
                "search_s": round(search_s, 2),
                "attempts": len(completions),
                "first_error": first_error,
                "context_tokens": sum(s.chunk.tokens for s in sources),
            },
        )
