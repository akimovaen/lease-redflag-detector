import importlib.util
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "check_evals", ROOT / "scripts" / "check_evals.py"
)
ce = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ce)


def test_a_metric_fails_below_its_minimum_or_above_its_maximum():
    limits = {"runs": ["x"], "passed": 0.9, "unauthorized_max": 0}
    assert not ce.check(limits, {"passed": 0.9, "unauthorized": 0})
    assert ce.check(limits, {"passed": 0.89, "unauthorized": 0})
    assert ce.check(limits, {"passed": 1.0, "unauthorized": 1})
    assert not ce.check(limits, {"passed": None, "unauthorized": 0})  # not measured


def test_the_agent_thresholds_name_saved_runs_and_measured_metrics():
    limits = tomllib.loads(ce.THRESHOLDS.read_text(encoding="utf-8"))["agent"]
    for run in limits["runs"]:
        scores = ce.agent(run)
        assert {k.removesuffix("_max") for k in limits} - {"runs"} <= scores.keys()
