"""Check the evals against the thresholds in evals/thresholds.toml; exit 1 if any fails.

    uv run python scripts/check_evals.py retrieval          # runs the role search
    uv run python scripts/check_evals.py generation         # the production run
    uv run python scripts/check_evals.py generation <run>   # another run folder
    uv run python scripts/check_evals.py fresh <run>        # a new unjudged run

retrieval searches every red flag of evals/redflag_retrieval.toml by role with the
production settings and scores it like scripts/eval_retrieval.py, without writing a
run folder. generation rescores a saved run against evals/redline_expected.toml like
scripts/eval_redline.py and adds the judge's faithfulness if the run was judged. No
API calls: CI runs this on every push. fresh scores a run CI has just generated on a
pull request against the looser [fresh] thresholds: one new run is noisier than the
saved one.
"""

import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THRESHOLDS = ROOT / "evals" / "thresholds.toml"


def retrieval() -> dict[str, float | None]:
    import eval_retrieval

    from lease_redflag_detector.rag.redline_search import MIN_SCORE, RedlineSearch
    from lease_redflag_detector.rag.retrieve import Retriever, load_chunks

    flags = eval_retrieval.load_flags()
    search = RedlineSearch(Retriever(load_chunks()), min_score=0.0)
    results = {flag["id"]: search.search(flag["red_flag"]) for flag in flags}
    scores = eval_retrieval.role_scores(flags, results, MIN_SCORE)
    return {"overall": scores["overall"], "avoid": scores["avoid"], **scores["roles"]}


def generation(run: str) -> dict[str, float | None]:
    import eval_redline

    folder = eval_redline.OUT / run
    scores = eval_redline.score_run(folder, eval_redline.load_expected())["totals"]
    judged = folder / "judge.json"
    if judged.exists():
        scores["faithfulness"] = json.loads(judged.read_text(encoding="utf-8"))[
            "faithfulness"
        ]
    return scores


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("retrieval", "generation", "fresh"):
        raise SystemExit(__doc__)
    if sys.argv[1] == "fresh" and len(sys.argv) < 3:
        raise SystemExit("fresh needs the run folder name")
    stage = sys.argv[1]
    limits = tomllib.loads(THRESHOLDS.read_text(encoding="utf-8"))[stage]
    if stage == "retrieval":
        scores = retrieval()
    else:
        run = sys.argv[2] if len(sys.argv) > 2 else limits["run"]
        print(f"run {run}")
        scores = generation(run)

    failed = False
    for name, limit in limits.items():
        if name == "run":
            continue
        metric, upper = name.removesuffix("_max"), name.endswith("_max")
        value = scores.get(metric)
        if value is None:
            print(f"  {metric:<13} –      (not measured)")
            continue
        ok = value <= limit if upper else value >= limit
        failed |= not ok
        sign = "≤" if upper else "≥"
        print(
            f"  {metric:<13} {value:.2f}   {sign} {limit:.2f}   {'ok' if ok else 'FAIL'}"
        )
    if failed:
        raise SystemExit(f"{stage}: below the thresholds in {THRESHOLDS.name}")


if __name__ == "__main__":
    main()
