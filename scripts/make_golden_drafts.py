"""Create blank golden set files and annotation hints for manual labeling.

For each golden text:
- data/golden/<id>.json: a LeaseAbstract with every field empty, to be filled
  in by hand. Existing files are never overwritten.
- data/processed/golden_hints/<id>.md: spans the ALeaseBERT authors annotated
  for this lease, with line numbers in data/texts/<id>.txt. They are hints, not
  answers: most ALeaseBERT red flag spans protect the landlord.

Usage: uv run python scripts/make_golden_drafts.py
"""

import csv
import difflib
import json
import re
from pathlib import Path

from lease_redflag_detector.extraction.schema import LeaseAbstract, RedFlag

ROOT = Path(__file__).resolve().parent.parent
POOL = ROOT / "data/raw/aleasebert/annotated/pool"
TEXTS = ROOT / "data/texts"
GOLDEN = ROOT / "data/golden"
HINTS = ROOT / "data/processed/golden_hints"

GOLDEN_IDS = [
    "alb_lease_contract_201",
    "alb_lease_contract_259",
    "alb_lease_contract_30",
    "alb_lease_562",
    "alb_lease_contract_54",
    "ocr_lease_contract_199",
    "ocr_lease_contract_11",
]

# ALeaseBERT entity class -> schema field it helps to fill
ENTITY_HINTS = {
    "e_5": "document_type (type_lease)",
    "e_1": "lessor",
    "e_2": "lessee",
    "e_3": "premises_address, area (leased_space)",
    "e_25": "start_date",
    "e_26": "end_date",
    "e_8": "end_date (expiration_date_of_lease)",
    "e_9": "rent (term_of_payment)",
    "e_10": "indexation (indexation_rent)",
}
REDFLAG_CLASS = "e_23"


def blank_abstract() -> dict:
    fields = {name: None for name in LeaseAbstract.model_fields}
    fields["red_flags"] = []
    return fields


def ocr_line_number(span: str, lines: list[str]) -> int:
    """Line of the OCR text that best matches the start of an original span."""
    probe = span[:80]
    scores = [
        difflib.SequenceMatcher(None, probe, line[: len(probe)]).ratio()
        for line in lines
    ]
    return scores.index(max(scores)) + 1


def hint_lines(annotations: dict, group: str, text_lines: list[str]) -> list[str]:
    parts = annotations["annotatable"]["parts"]

    def located(entity: dict) -> str:
        span = " ".join(offset["text"] for offset in entity["offsets"])
        if group == "A":
            where = f"line {parts.index(entity['part']) + 1}"
        else:
            where = f"~line {ocr_line_number(span, text_lines)} (OCR text differs)"
        return f"- {where}: {span}"

    out = []
    for class_id, field in ENTITY_HINTS.items():
        spans = [
            located(e) for e in annotations["entities"] if e["classId"] == class_id
        ]
        if spans:
            out += [f"### {field}", "", *spans, ""]

    flags = [e for e in annotations["entities"] if e["classId"] == REDFLAG_CLASS]
    out += ["## ALeaseBERT red flags", ""]
    out += [
        "Check each one: is it risky for the landlord under the definitions above?",
        "",
    ]
    for entity in flags:
        flag_type = entity["fields"].get("f_24", {}).get("value", "?")
        out.append(f"{located(entity).replace('- ', f'- [{flag_type}] ', 1)}")
    return out


def main() -> None:
    with (TEXTS / "manifest.csv").open(encoding="utf-8") as f:
        manifest = {row["id"]: row for row in csv.DictReader(f)}
    GOLDEN.mkdir(parents=True, exist_ok=True)
    HINTS.mkdir(parents=True, exist_ok=True)
    # One bullet per red flag type: split before each "type_name:".
    definitions = re.sub(
        r"\. (?=[a-z_]+: )", ".\n- ", RedFlag.model_fields["type"].description
    )

    for text_id in GOLDEN_IDS:
        row = manifest[text_id]
        golden_path = GOLDEN / f"{text_id}.json"
        if golden_path.exists():
            print(f"{golden_path.relative_to(ROOT)} exists, left unchanged")
        else:
            golden_path.write_text(json.dumps(blank_abstract(), indent=2) + "\n")
            print(f"created {golden_path.relative_to(ROOT)}")

        ann_path = next(POOL.glob(f"*-{row['source_id']}.ann.json"))
        annotations = json.loads(ann_path.read_text(encoding="utf-8"))
        text_lines = (TEXTS / f"{text_id}.txt").read_text(encoding="utf-8").split("\n")
        hints = [
            f"# Hints for {text_id}",
            "",
            (
                f"Text: `data/texts/{text_id}.txt` ({row['words']} words, dirt: "
                f"{row['dirt'] or 'none'}). Golden file: `data/golden/{text_id}.json`."
            ),
            "",
            (
                "Spans annotated by the ALeaseBERT authors. Values must be normalized "
                "to the schema (ISO dates, numbers, enums); quotes must be copied from "
                "the text file, not from here."
            ),
            "",
            "Red flag definitions:",
            "",
            f"- {definitions}",
            "",
            "## ALeaseBERT entities",
            "",
            *hint_lines(annotations, row["group"], text_lines),
        ]
        (HINTS / f"{text_id}.md").write_text("\n".join(hints) + "\n", encoding="utf-8")
    print(f"hints written to {HINTS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
