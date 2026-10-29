import json
from pathlib import Path

from lease_redflag_detector.extraction.extractor import (
    BaseExtractor,
    Completion,
    RunConfig,
    load_prompt,
    validate_output,
)

ROOT = Path(__file__).resolve().parents[1]

TEXT = "Article 5. The Tenant may terminate this lease\nupon three months' notice."

VALID = {
    "document_type": "lease",
    "lessor": "A Ltd",
    "lessee": None,
    "premises_address": None,
    "area": {"value": 100, "unit": "sqm"},
    "start_date": "2020-01-01",
    "end_date": None,
    "rent": None,
    "indexation": "none",
    "red_flags": [
        {
            "type": "tenant_break_option",
            "quote": "The Tenant may terminate this lease upon three months' notice.",
        }
    ],
}


def with_quote(quote: str) -> dict:
    return {**VALID, "red_flags": [{"type": "tenant_break_option", "quote": quote}]}


def test_valid_output_is_parsed():
    output, error = validate_output(json.dumps(VALID), TEXT)
    assert error is None
    assert output.red_flags[0].type == "tenant_break_option"


def test_unknown_enum_value_fails():
    bad = {**VALID, "indexation": "sometimes"}
    output, error = validate_output(json.dumps(bad), TEXT)
    assert output is None
    assert "indexation" in error


def test_broken_json_fails():
    output, error = validate_output('{"document_type": "lease"', TEXT)
    assert output is None
    assert error


def test_paraphrased_quote_fails():
    raw = json.dumps(with_quote("The Tenant can end the lease with 3 months' notice."))
    output, error = validate_output(raw, TEXT)
    assert output is None
    assert "red_flags.0" in error


def test_end_before_start_fails():
    bad = {**VALID, "end_date": "2019-12-31"}
    output, error = validate_output(json.dumps(bad), TEXT)
    assert output is None
    assert "end_date" in error


def test_configs_and_their_prompts_load():
    for path in (ROOT / "configs").glob("*.toml"):
        config = RunConfig.load(path)
        assert config.name == path.stem
        assert load_prompt(config.prompt)


class FakeExtractor(BaseExtractor):
    """Returns the prepared answers in order and records the requests."""

    def __init__(self, answers: list[dict]) -> None:
        super().__init__(RunConfig.load(ROOT / "configs" / "claude-haiku-medium.toml"))
        self.answers = [json.dumps(a) for a in answers]
        self.requests: list[list[dict]] = []

    def _complete(self, messages: list[dict]) -> Completion:
        self.requests.append(list(messages))
        return Completion(self.answers.pop(0), False, 10, 5, "end_turn")


def test_valid_answer_needs_no_repair():
    extractor = FakeExtractor([VALID])
    result = extractor.extract(TEXT)
    assert result.status == "ok"
    assert result.extra["attempts"] == 1


def test_invalid_answer_is_repaired():
    extractor = FakeExtractor([with_quote("made up"), VALID])
    result = extractor.extract(TEXT)
    assert result.status == "ok"
    assert result.extra["attempts"] == 2
    assert "red_flags.0" in result.extra["first_error"]
    assert result.input_tokens == 20
    repair_request = extractor.requests[1][-1]["content"]
    assert "quote not found" in repair_request


def test_failed_repair_marks_result_failed():
    extractor = FakeExtractor([with_quote("made up"), with_quote("still made up")])
    result = extractor.extract(TEXT)
    assert result.status == "failed"
    assert result.output is None
    assert result.extra["attempts"] == 2
