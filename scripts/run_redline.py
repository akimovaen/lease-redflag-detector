"""Generate redline proposals for the red flags of evals/redflag_retrieval.toml.

    uv run python scripts/run_redline.py --config configs/rag-haiku-v1.toml \
        --name haiku-v1 --note "first prompt"

Every run goes to its own folder, results/rag/generation/<date>_<name>/, and is never
overwritten:

- run.json: what was run (commit, config, prompt, hashes of the flag set and the
  chunks, totals of tokens, cost and latency, note);
- outputs.jsonl: one line per red flag with its context sources, the model's answer,
  the approval that follows from it, and usage;
- report.md: the answers as the lawyer reads them.

`--only f01 f07` runs a few flags for a quick look; such runs are marked partial.
"""

import argparse
import datetime
import hashlib
import json
import statistics
import subprocess
import sys
import tomllib
from pathlib import Path

from dotenv import load_dotenv

from lease_redflag_detector.extraction.extractor import RunConfig
from lease_redflag_detector.extraction.metrics import PRICES
from lease_redflag_detector.extraction.schema import RedFlag, RedFlagType
from lease_redflag_detector.rag.redline import (
    CONTEXT_TOKENS,
    DEFAULT_RISK,
    ROLE_NAMES,
    RedlineGenerator,
    Result,
    approval,
    gap_line,
)
from lease_redflag_detector.rag.redline_search import RedlineSearch
from lease_redflag_detector.rag.retrieve import CHUNKS, Retriever, load_chunks

ROOT = Path(__file__).resolve().parents[1]
FLAGS = ROOT / "evals" / "redflag_retrieval.toml"
OUT = ROOT / "results" / "rag" / "generation"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    if model not in PRICES:
        return None
    price_in, price_out = PRICES[model]
    return (input_tokens * price_in + output_tokens * price_out) / 1e6


def record(flag: dict, result: Result) -> dict:
    return {
        "id": flag["id"],
        "type": flag["type"],
        "trap": flag.get("trap"),
        "quote": flag["quote"],
        "status": result.status,
        "error": result.error,
        "output": result.output.model_dump(mode="json") if result.output else None,
        "approval": result.approval,
        "needs_decision": result.needs_decision,
        "sources": [
            {
                "id": s.id,
                "role": s.role,
                "chunk": s.chunk.id,
                "score": None if s.score is None else round(s.score, 4),
            }
            for s in result.sources
        ],
        "raw": None if result.output else result.raw,
        "latency_s": round(result.latency_s, 2),
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        **result.extra,
    }


def claim_line(claim: dict, chunks: dict[str, str]) -> str:
    cited = ", ".join(f"{s} `{chunks.get(s, '?')}`" for s in claim["sources"])
    return f"{claim['text']} — {cited}"


def report(info: dict, rows: list[dict]) -> str:
    lines = [
        f"# Redline proposals: {info['name']}",
        "",
        info["note"],
        "",
        (
            f"{info['date']}, commit `{info['commit']}`"
            + (" with uncommitted changes" if info["uncommitted_changes"] else "")
            + f". {info['model']}, prompt `{info['prompt']}`. {info['ok']} of "
            f"{info['flags']} answers valid, {info['repaired']} after repair. Cost "
            f"${info['cost_usd']:.4f}, ${info['cost_per_1000_usd']:.2f} per 1000 red "
            f"flags. Latency p50 {info['latency_p50_s']:.1f} s."
        ),
        "",
    ]
    for row in rows:
        chunks = {s["id"]: s["chunk"] for s in row["sources"]}
        lines += [
            f"## {row['id']} · {row['type']}"
            + (f" · {row['trap']}" if row["trap"] else ""),
            "",
            f"> {row['quote']}",
            "",
        ]
        out = row["output"]
        if not out:
            lines += [f"**Не вдалося:** {row['error']}", ""]
            continue
        default = DEFAULT_RISK[RedFlagType(row["type"])]
        # Computed, not read from the run: older runs saved the route without the
        # lawyer's step for answers with gaps.
        verdict = "Вердикт (попередній)" if out["gaps"] else "Вердикт"
        route = approval(out["verdict"], bool(out["gaps"]))
        lines += [
            f"**{verdict}:** {out['verdict']} · **Погоджує:** {route}",
            "",
        ]
        if out["gaps"]:
            lines += [
                "**Потрібне рішення юриста.** Джерела не вирішують:",
                "",
                *[f"- {gap_line(gap)}" for gap in out["gaps"]],
                "",
            ]
        lines += [
            f"**Ризик:** {out['risk']}"
            + (f" (за замовчуванням {default})" if out["risk"] != default else "")
            + f" — {claim_line(out['risk_reason'], chunks)}",
            "",
            "**Висновки:**",
            "",
            *[f"- {claim_line(c, chunks)}" for c in out["findings"]],
            "",
        ]
        if out["proposed_clause"]:
            cited = ", ".join(
                f"{s} `{chunks.get(s, '?')}`" for s in out["proposed_sources"]
            )
            lines += [
                f"**Запропонована редакція** ({cited}):",
                "",
                f"> {out['proposed_clause']}",
                "",
            ]
        if out["conflicts"]:
            lines += [
                "**Суперечності джерел:**",
                "",
                *[f"- {claim_line(c, chunks)}" for c in out["conflicts"]],
                "",
            ]
        roles = {}
        for s in row["sources"]:
            roles.setdefault(s["role"], []).append(f"{s['id']} `{s['chunk']}`")
        lines += [
            "<details><summary>Контекст</summary>",
            "",
            *[f"- {ROLE_NAMES[role]}: {', '.join(ids)}" for role, ids in roles.items()],
            "",
            "</details>",
            "",
        ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--name", required=True, help="short name of the run")
    parser.add_argument("--note", default="", help="what changed since the last run")
    parser.add_argument("--only", nargs="+", help="flag ids to run")
    args = parser.parse_args()
    folder = OUT / f"{datetime.date.today().isoformat()}_{args.name}"
    if folder.exists():
        raise SystemExit(f"{folder.relative_to(ROOT)} exists; choose another --name")

    load_dotenv(ROOT / ".env")
    config = RunConfig.load(args.config)
    flags = tomllib.loads(FLAGS.read_text(encoding="utf-8"))["flag"]
    if args.only:
        flags = [flag for flag in flags if flag["id"] in args.only]
    generator = RedlineGenerator(config, RedlineSearch(Retriever(load_chunks())))

    rows = []
    for flag in flags:
        result = generator.generate(RedFlag(type=flag["type"], quote=flag["quote"]))
        rows.append(record(flag, result))
        print(
            flag["id"],
            result.status,
            result.output.verdict if result.output else result.error,
            file=sys.stderr,
        )

    input_tokens = sum(row["input_tokens"] for row in rows)
    output_tokens = sum(row["output_tokens"] for row in rows)
    total = cost(config.model, input_tokens, output_tokens)
    info = {
        "name": args.name,
        "note": args.note,
        "date": datetime.datetime.now().isoformat(timespec="seconds"),
        "commit": git("rev-parse", "--short", "HEAD"),
        "uncommitted_changes": bool(git("status", "--porcelain")),
        "config": config.model_dump(),
        "model": config.model,
        "prompt": config.prompt,
        "partial": bool(args.only),
        "flag_set": {"path": str(FLAGS.relative_to(ROOT)), "hash": file_hash(FLAGS)},
        "chunks": {"path": str(CHUNKS.relative_to(ROOT)), "hash": file_hash(CHUNKS)},
        "context_tokens": CONTEXT_TOKENS,
        "flags": len(rows),
        "ok": sum(row["status"] == "ok" for row in rows),
        "repaired": sum(row["status"] == "ok" and row["attempts"] > 1 for row in rows),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": total,
        "cost_per_1000_usd": None if total is None else 1000 * total / len(rows),
        "latency_p50_s": statistics.median(row["latency_s"] for row in rows),
    }

    folder.mkdir(parents=True)
    (folder / "run.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (folder / "outputs.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    (folder / "report.md").write_text(report(info, rows), encoding="utf-8")
    print(f"Wrote {folder.relative_to(ROOT)}: ${total:.4f}", file=sys.stderr)


if __name__ == "__main__":
    main()
