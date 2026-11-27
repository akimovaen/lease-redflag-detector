import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "count_phrases", ROOT / "scripts" / "count_phrases.py"
)
cp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cp)


def test_every_count_names_saved_runs_and_a_valid_pattern():
    for count in cp.COUNTS:
        re.compile(count["pattern"])
        for names in count["groups"].values():
            assert names, count["what"]  # the runs it counts are saved
            assert all((cp.RUNS / name / "results.jsonl").exists() for name in names)


def test_a_run_and_its_repeats_only():
    names = cp.runs("2026-11-25_prompt-v4")
    assert names == [
        "2026-11-25_prompt-v4",
        "2026-11-25_prompt-v4-r2",
        "2026-11-25_prompt-v4-r3",
    ]
