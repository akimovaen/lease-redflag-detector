"""Merge generation runs on parts of the flag set into one full run.

    uv run python scripts/merge_runs.py --name haiku-v3-24 --note "..." \
        2026-11-11_haiku-v3 2026-11-13_haiku-v3-f23-f24

For flags added after a full run: run only them (scripts/run_redline.py --only) with
the same config, and merge. The runs must share the model, the prompt and the config,
and the generation code must not have changed between them (check with git diff); a
later run wins for a flag in both. The merged folder lists its parts in run.json
(`merged_from`); answers, costs and, if every part was judged, the judge's lines are
copied, and the totals recomputed.
"""

import argparse
import datetime
import json
import statistics
import tomllib

from judge_redline import mean
from run_redline import FLAGS, OUT, file_hash, git, report

from lease_redflag_detector.rag.judge import CLAUSE_SCORES, FACT_SCORES, SUPPORT_SCORES


def read_jsonl(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def write_jsonl(path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", required=True, help="short name of the merged run")
    parser.add_argument("--note", default="")
    parser.add_argument("runs", nargs="+", help="run folders, earlier first")
    args = parser.parse_args()
    folder = OUT / f"{datetime.date.today().isoformat()}_{args.name}"
    if folder.exists():
        raise SystemExit(f"{folder.name} exists; choose another --name")

    parts = [OUT / run for run in args.runs]
    infos = [json.loads((p / "run.json").read_text(encoding="utf-8")) for p in parts]
    for info in infos[1:]:
        if info["config"] != infos[0]["config"]:
            raise SystemExit(f"{info['name']}: another config than {infos[0]['name']}")

    rows, judged = {}, {}
    for part in parts:
        rows |= {row["id"]: row for row in read_jsonl(part / "outputs.jsonl")}
        if (part / "judge.jsonl").exists():
            judged |= {line["id"]: line for line in read_jsonl(part / "judge.jsonl")}
    order = [f["id"] for f in tomllib.loads(FLAGS.read_text(encoding="utf-8"))["flag"]]
    rows = [rows[i] for i in order if i in rows]

    input_tokens = sum(row["input_tokens"] for row in rows)
    output_tokens = sum(row["output_tokens"] for row in rows)
    total = sum(info["cost_usd"] for info in infos)
    info = {
        **infos[0],
        "name": args.name,
        "note": args.note,
        "date": datetime.datetime.now().isoformat(timespec="seconds"),
        "commit": git("rev-parse", "--short", "HEAD"),
        "uncommitted_changes": bool(git("status", "--porcelain")),
        "merged_from": [
            {"run": p.name, "commit": i["commit"], "flags": i["flags"]}
            for p, i in zip(parts, infos, strict=True)
        ],
        "partial": len(rows) < len(order),
        "flag_set": {"path": infos[0]["flag_set"]["path"], "hash": file_hash(FLAGS)},
        "flags": len(rows),
        "ok": sum(row["status"] == "ok" for row in rows),
        "repaired": sum(row["status"] == "ok" and row["attempts"] > 1 for row in rows),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": total,
        "cost_per_1000_usd": 1000 * total / len(rows),
        "latency_p50_s": statistics.median(row["latency_s"] for row in rows),
    }
    folder.mkdir(parents=True)
    (folder / "run.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    write_jsonl(folder / "outputs.jsonl", rows)
    (folder / "report.md").write_text(report(info, rows), encoding="utf-8")

    if all((p / "judge.json").exists() for p in parts):
        lines = [judged[row["id"]] for row in rows]
        ok = [line for line in lines if not line.get("failed")]
        judges = [json.loads((p / "judge.json").read_text()) for p in parts]
        totals = {
            "facts": mean([FACT_SCORES[f["grade"]] for l in ok for f in l["facts"]]),
            "clause": mean(
                [CLAUSE_SCORES[l["clause"]] for l in ok if l["clause"] != "not_needed"]
            ),
            "faithfulness": mean(
                [SUPPORT_SCORES[c["support"]] for l in ok for c in l["claims"]]
            ),
            "unsupported_claims": sum(
                c["support"] == "no" for l in ok for c in l["claims"]
            ),
            "claims": sum(len(l["claims"]) for l in ok),
            "judge": judges[0]["judge"],
            "prompts": judges[0]["prompts"],
            "input_tokens": sum(j["input_tokens"] for j in judges),
            "output_tokens": sum(j["output_tokens"] for j in judges),
            "cost_usd": sum(j["cost_usd"] for j in judges),
        }
        write_jsonl(folder / "judge.jsonl", lines)
        (folder / "judge.json").write_text(
            json.dumps(totals, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    print(f"Wrote {folder.name}: {len(rows)} flags from {len(parts)} runs")


if __name__ == "__main__":
    main()
