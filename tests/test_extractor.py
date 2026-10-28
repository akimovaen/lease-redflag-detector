import json
from pathlib import Path

from lease_redflag_detector.extraction.extractor import (
    RunConfig,
    load_prompt,
    validate_output,
)

ROOT = Path(__file__).resolve().parents[1]

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
    "red_flags": [{"type": "tenant_break_option", "quote": "may terminate"}],
}


def test_valid_output_is_parsed():
    output, error = validate_output(json.dumps(VALID))
    assert error is None
    assert output.red_flags[0].type == "tenant_break_option"


def test_unknown_enum_value_fails():
    bad = {**VALID, "indexation": "sometimes"}
    output, error = validate_output(json.dumps(bad))
    assert output is None
    assert "indexation" in error


def test_broken_json_fails():
    output, error = validate_output('{"document_type": "lease"')
    assert output is None
    assert error


def test_configs_and_their_prompts_load():
    for path in (ROOT / "configs").glob("*.toml"):
        config = RunConfig.load(path)
        assert config.name == path.stem
        assert load_prompt(config.prompt)
