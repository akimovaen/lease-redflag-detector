"""Common interface of the extraction models.

Every provider turns a lease text into an `Extraction`: the parsed `LeaseAbstract`
when the output is valid, the raw output either way, and the numbers needed for
the metrics (latency and token usage).

`BaseExtractor` holds the pipeline shared by all providers: request, validation
and one repair attempt. An output is valid when it matches the schema, every red
flag quote appears verbatim in the text, and the end date is not before the start
date. If it is not, the model gets its answer back with the list of problems and
one chance to fix it; if the second answer is still invalid, the result is failed.
"""

import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ValidationError

from lease_redflag_detector.extraction.quotes import quote_in_text
from lease_redflag_detector.extraction.schema import LeaseAbstract

PROMPTS = Path(__file__).resolve().parents[3] / "prompts"
REPAIR_PROMPT = "repair/v1"


class RunConfig(BaseModel):
    """One model × prompt × sampling combination, loaded from `configs/*.toml`."""

    name: str
    provider: Literal["anthropic", "ollama"]
    model: str
    prompt: str
    max_tokens: int = 8000
    timeout_s: float = 180
    max_retries: int = 3
    context_tokens: int | None = None  # context window of a local model
    max_red_flags: int | None = None  # cap on the list in the decoding grammar
    sampling: dict[str, str | float | int] = {}

    @classmethod
    def load(cls, path: Path) -> "RunConfig":
        return cls.model_validate(tomllib.loads(path.read_text()))


def load_prompt(prompt: str) -> str:
    """Read a prompt by its version name, e.g. `extraction/v1`."""
    return (PROMPTS / f"{prompt}.md").read_text().strip()


@dataclass
class Extraction:
    status: Literal["ok", "failed"]
    raw: str
    output: LeaseAbstract | None = None
    error: str | None = None
    latency_s: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    extra: dict = field(default_factory=dict)


@dataclass
class Completion:
    """One answer of a model, as returned by a provider."""

    raw: str
    truncated: bool
    input_tokens: int
    output_tokens: int
    stop_reason: str | None


def validate_output(raw: str, text: str) -> tuple[LeaseAbstract | None, str | None]:
    """Parse raw model output into a `LeaseAbstract`, or return the problems found."""
    try:
        output = LeaseAbstract.model_validate_json(raw)
    except ValidationError as e:
        return None, str(e)

    problems = [
        f"red_flags.{i}: quote not found verbatim in the text: {flag.quote[:200]!r}"
        for i, flag in enumerate(output.red_flags)
        if not quote_in_text(flag.quote, text)
    ]
    if output.start_date and output.end_date and output.end_date < output.start_date:
        problems.append(
            f"end_date {output.end_date} is before start_date {output.start_date}"
        )
    if problems:
        return None, "\n".join(problems)
    return output, None


def check(completion: Completion, text: str) -> tuple[LeaseAbstract | None, str]:
    if completion.truncated:
        return None, "the answer was cut off at the output token limit"
    output, error = validate_output(completion.raw, text)
    return output, error or ""


class Extractor(Protocol):
    config: RunConfig

    def extract(self, text: str) -> Extraction: ...


class BaseExtractor:
    """Request, validation and one repair attempt; providers implement `_complete`."""

    # Exceptions of the provider client that end the extraction as failed.
    errors: tuple[type[Exception], ...] = ()

    def __init__(self, config: RunConfig) -> None:
        self.config = config
        self.system = load_prompt(config.prompt)
        self.repair = load_prompt(REPAIR_PROMPT)

    def _complete(self, messages: list[dict]) -> Completion:
        raise NotImplementedError

    def extract(self, text: str) -> Extraction:
        messages = [{"role": "user", "content": f"<lease>\n{text}\n</lease>"}]
        completions: list[Completion] = []
        first_error = None
        start = time.perf_counter()
        try:
            completions.append(self._complete(messages))
            output, error = check(completions[-1], text)
            if error:
                first_error = error
                messages += [
                    {"role": "assistant", "content": completions[-1].raw},
                    {"role": "user", "content": self.repair.replace("{errors}", error)},
                ]
                completions.append(self._complete(messages))
                output, error = check(completions[-1], text)
        except self.errors as e:
            output, error = None, f"{type(e).__name__}: {e}"

        return Extraction(
            status="ok" if output else "failed",
            raw=completions[-1].raw if completions else "",
            output=output,
            error=error or None,
            latency_s=time.perf_counter() - start,
            input_tokens=sum(c.input_tokens for c in completions),
            output_tokens=sum(c.output_tokens for c in completions),
            extra={
                "stop_reason": completions[-1].stop_reason if completions else None,
                "attempts": len(completions),
                "first_error": first_error,
            },
        )
