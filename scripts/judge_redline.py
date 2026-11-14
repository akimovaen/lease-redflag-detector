"""Run the LLM judges on a generation run.

    uv run python scripts/judge_redline.py 2026-11-11_haiku-v3

Writes judge.jsonl (one line per red flag: the grade of every key fact, of the changed
clause and of every claim) and judge.json (averages, judge model, usage and cost) into
the run folder. scripts/eval_redline.py adds the averages to its history.

- facts: share of the key facts the answer states (partial counts as half);
- clause: grade of the changed clause where one is expected or given;
- faithfulness: share of the claims their cited sources support (partial as half).
"""

import argparse
import json
import sys
import tomllib
from pathlib import Path

from dotenv import load_dotenv

from lease_redflag_detector.extraction.extractor import RunConfig
from lease_redflag_detector.extraction.metrics import PRICES
from lease_redflag_detector.rag.judge import (
    CLAUSE_SCORES,
    FACT_SCORES,
    SUPPORT_SCORES,
    Judge,
)
from lease_redflag_detector.rag.retrieve import load_chunks

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = ROOT / "evals" / "redline_expected.toml"
OUT = ROOT / "results" / "rag" / "generation"
CONFIG = ROOT / "configs" / "judge-sonnet-v1.toml"


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run", help="folder name under results/rag/generation/")
    parser.add_argument("--config", type=Path, default=CONFIG)
    args = parser.parse_args()
    folder = OUT / args.run
    if (folder / "judge.json").exists():
        raise SystemExit(f"{folder.name} is already judged; delete judge.json to redo")

    load_dotenv(ROOT / ".env")
    config = RunConfig.load(args.config)
    judge = Judge(config)
    expected = {
        a["id"]: a
        for a in tomllib.loads(EXPECTED.read_text(encoding="utf-8"))["answer"]
    }
    texts = {chunk.id: chunk.text for chunk in load_chunks()}
    rows = [
        json.loads(line)
        for line in (folder / "outputs.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    lines = []
    for row in rows:
        if not row["output"]:
            lines.append({"id": row["id"], "failed": True})
            continue
        answer = judge.answer(row, expected[row["id"]])
        faithful = judge.faithfulness(row, texts)
        lines.append(
            {
                "id": row["id"],
                "facts": [f.model_dump(mode="json") for f in answer.facts],
                "clause": answer.clause.value,
                "clause_reason": answer.clause_reason,
                "claims": [c.model_dump(mode="json") for c in faithful.claims],
            }
        )
        print(row["id"], answer.clause.value, file=sys.stderr)

    judged = [line for line in lines if not line.get("failed")]
    facts = [FACT_SCORES[f["grade"]] for line in judged for f in line["facts"]]
    clauses = [
        CLAUSE_SCORES[line["clause"]]
        for line in judged
        if line["clause"] != "not_needed"
    ]
    claims = [SUPPORT_SCORES[c["support"]] for line in judged for c in line["claims"]]
    price_in, price_out = PRICES[config.model]
    cost = (
        judge.usage["input_tokens"] * price_in
        + judge.usage["output_tokens"] * price_out
    ) / 1e6
    totals = {
        "facts": mean(facts),
        "clause": mean(clauses),
        "faithfulness": mean(claims),
        "unsupported_claims": sum(
            c["support"] == "no" for l in judged for c in l["claims"]
        ),
        "claims": len(claims),
        "judge": config.model_dump(),
        "prompts": ["judge/answer_v1", "judge/faithfulness_v1"],
        **judge.usage,
        "cost_usd": cost,
    }
    (folder / "judge.jsonl").write_text(
        "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines),
        encoding="utf-8",
    )
    (folder / "judge.json").write_text(
        json.dumps(totals, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(
        f"{folder.name}: facts {totals['facts']:.2f}, clause {totals['clause']:.2f}, "
        f"faithfulness {totals['faithfulness']:.2f}, ${cost:.3f}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
