"""LLM judges for redline answers: correctness against the expected answer, and
faithfulness of every claim to the sources it cites.

The answer judge gets the clause, the expected answer (verdict, risk, key facts, notes)
and the model's answer, and grades every key fact as present, partial or missing, and
the changed clause. The faithfulness judge gets every claim of the answer with the full
text of the chunks it cites and grades whether they support it.

Both use structured outputs, like the generator, and a model other than the one being
judged. Their agreement with the lawyer's grades is measured on a calibration set
(evals/judge_calibration.toml).
"""

from enum import StrEnum

import anthropic
from pydantic import BaseModel, Field, ValidationError

from lease_redflag_detector.extraction.extractor import RunConfig, load_prompt
from lease_redflag_detector.markup import attr, neutral
from lease_redflag_detector.rag.redline import gap_line

FACT_SCORES = {"present": 1.0, "partial": 0.5, "missing": 0.0}
CLAUSE_SCORES = {"good": 1.0, "minor_edits": 0.5, "wrong": 0.0, "missing": 0.0}
SUPPORT_SCORES = {"yes": 1.0, "partial": 0.5, "no": 0.0}


class FactGrade(StrEnum):
    PRESENT = "present"
    PARTIAL = "partial"
    MISSING = "missing"


class ClauseGrade(StrEnum):
    GOOD = "good"
    MINOR_EDITS = "minor_edits"
    WRONG = "wrong"
    MISSING = "missing"
    NOT_NEEDED = "not_needed"


class Support(StrEnum):
    YES = "yes"
    PARTIAL = "partial"
    NO = "no"


class FactJudgment(BaseModel):
    fact: int = Field(description="Number of the key fact, from 1.")
    reason: str = Field(description="One sentence: where the answer says it, or not.")
    grade: FactGrade


class AnswerJudgment(BaseModel):
    facts: list[FactJudgment] = Field(description="One entry per key fact, in order.")
    clause_reason: str = Field(description="One or two sentences on the clause.")
    clause: ClauseGrade = Field(
        description=(
            "good: the changed clause can be used as it is; minor_edits: right in "
            "substance, with small omissions or wording to fix; wrong: it breaks the "
            "policy, misses the point or invents values; missing: a changed clause is "
            "expected but none is given; not_needed: none is expected and none is given."
        )
    )


class ClaimJudgment(BaseModel):
    claim: int = Field(description="Number of the claim, from 1.")
    reason: str = Field(description="One sentence: what the sources say.")
    support: Support = Field(
        description=(
            "yes: the cited sources state everything the claim says; partial: they "
            "support part of it, or the claim adds an inference they do not state; "
            "no: they do not support it or contradict it."
        )
    )


class FaithfulnessJudgment(BaseModel):
    claims: list[ClaimJudgment] = Field(description="One entry per claim, in order.")


def output_format(model: type[BaseModel]) -> dict:
    return {
        "type": "json_schema",
        "schema": anthropic.transform_schema(model.model_json_schema()),
    }


def claims_of(output: dict) -> list[dict]:
    """The claims of an answer that cite sources: findings, risk reason, conflicts."""
    return [*output["findings"], output["risk_reason"], *output["conflicts"]]


def render_answer(row: dict, expected: dict) -> str:
    output = row["output"]
    facts = "\n".join(f"{i}. {fact}" for i, fact in enumerate(expected["key_facts"], 1))
    # The answer may repeat what a source or the clause said, tags included.
    findings = "\n".join(f"- {neutral(claim['text'])}" for claim in output["findings"])
    gaps = (
        "\n".join(f"- {neutral(gap_line(gap))}" for gap in output["gaps"]) or "(none)"
    )
    risk_reason = neutral(output["risk_reason"]["text"])
    clause = neutral(output["proposed_clause"] or "(none)")
    return f"""<clause type="{attr(row["type"])}">
{neutral(row["quote"])}
</clause>

<expected>
verdict: {expected["verdict"]}
risk: {expected["risk"]}
key facts:
{facts}
notes: {expected["note"] or "(none)"}
</expected>

<answer>
verdict: {output["verdict"]}
risk: {output["risk"]} — {risk_reason}
findings:
{findings}
points the sources do not settle:
{gaps}
changed clause: {clause}
</answer>"""


def render_claims(row: dict, texts: dict[str, str]) -> str:
    chunks = {s["id"]: s["chunk"] for s in row["sources"]}
    blocks = []
    for number, claim in enumerate(claims_of(row["output"]), 1):
        sources = "\n".join(
            f'<source id="{attr(s)}">\n'
            f"{neutral(texts.get(chunks.get(s, ''), '(missing)'))}\n</source>"
            for s in claim["sources"]
        )
        blocks.append(
            f'<claim number="{number}">\n<text>{neutral(claim["text"])}</text>\n'
            f"{sources}\n</claim>"
        )
    return "\n\n".join(blocks)


class JudgeError(Exception):
    """A judgment that cannot be used: the answer was cut off or broke the schema."""


class Judge:
    # Raised by `ask` for one judgment; the caller records it and goes on.
    errors = (anthropic.APIError, JudgeError)

    def __init__(self, config: RunConfig):
        self.config = config
        self.client = anthropic.Anthropic(
            timeout=config.timeout_s, max_retries=config.max_retries
        )
        self.usage = {"input_tokens": 0, "output_tokens": 0}

    def ask(self, prompt: str, content: str, schema: type[BaseModel]) -> BaseModel:
        response = self.client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            system=load_prompt(prompt),
            messages=[{"role": "user", "content": content}],
            output_config={"format": output_format(schema), **self.config.sampling},
        )
        self.usage["input_tokens"] += response.usage.input_tokens
        self.usage["output_tokens"] += response.usage.output_tokens
        if response.stop_reason == "max_tokens":
            raise JudgeError("the judgment was cut off at the output token limit")
        raw = "".join(b.text for b in response.content if b.type == "text")
        try:
            return schema.model_validate_json(raw)
        except ValidationError as e:
            raise JudgeError(str(e)) from e

    def answer(self, row: dict, expected: dict) -> AnswerJudgment:
        return self.ask("judge/answer_v1", render_answer(row, expected), AnswerJudgment)

    def faithfulness(self, row: dict, texts: dict[str, str]) -> FaithfulnessJudgment:
        return self.ask(
            "judge/faithfulness_v1", render_claims(row, texts), FaithfulnessJudgment
        )
