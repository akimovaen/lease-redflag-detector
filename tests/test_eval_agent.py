import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "eval_agent", ROOT / "scripts" / "eval_agent.py"
)
ea = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ea)


def test_the_run_folder_has_the_date_once():
    assert ea.folder_name("final-v5", "2026-11-27") == "2026-11-27_final-v5"
    assert ea.folder_name("2026-11-27_final-v5", "2026-11-27") == "2026-11-27_final-v5"
    assert ea.folder_name("v5-2026", "2026-11-27") == "2026-11-27_v5-2026"
