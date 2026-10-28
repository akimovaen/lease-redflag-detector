"""Common interface of the extraction models.

Every provider turns a lease text into an `Extraction`: the parsed `LeaseAbstract`
when the output is valid, the raw output either way, and the numbers needed for
the metrics (latency and token usage).
"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ValidationError

from lease_redflag_detector.extraction.schema import LeaseAbstract

PROMPTS = Path(__file__).resolve().parents[3] / "prompts"


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


def validate_output(raw: str) -> tuple[LeaseAbstract | None, str | None]:
    """Parse raw model output into a `LeaseAbstract`, or return the validation error."""
    try:
        return LeaseAbstract.model_validate_json(raw), None
    except ValidationError as e:
        return None, str(e)


class Extractor(Protocol):
    config: RunConfig

    def extract(self, text: str) -> Extraction: ...
