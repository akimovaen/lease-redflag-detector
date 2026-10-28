"""Validate the golden set.

Every data/golden/<id>.json must match the LeaseAbstract schema and every red
flag quote must appear verbatim in data/texts/<id>.txt.

Usage: uv run python scripts/check_golden.py
"""

import sys
from pathlib import Path

from pydantic import ValidationError

from lease_redflag_detector.extraction.quotes import quote_in_text
from lease_redflag_detector.extraction.schema import LeaseAbstract

ROOT = Path(__file__).resolve().parent.parent
TEXTS = ROOT / "data/texts"
GOLDEN = ROOT / "data/golden"


def check(path: Path) -> list[str]:
    text_path = TEXTS / f"{path.stem}.txt"
    if not text_path.exists():
        return [f"no text file {text_path.relative_to(ROOT)}"]
    try:
        abstract = LeaseAbstract.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as error:
        return [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors()]
    text = text_path.read_text(encoding="utf-8")
    return [
        f"red_flags.{i}: quote not found in text: {flag.quote[:80]!r}"
        for i, flag in enumerate(abstract.red_flags)
        if not quote_in_text(flag.quote, text)
    ]


def main() -> None:
    paths = sorted(GOLDEN.glob("*.json"))
    failed = 0
    for path in paths:
        problems = check(path)
        status = "ok" if not problems else f"{len(problems)} problem(s)"
        print(f"{path.stem}: {status}")
        for problem in problems:
            print(f"    {problem}")
        failed += bool(problems)
    print(f"{len(paths) - failed} of {len(paths)} golden files valid")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
