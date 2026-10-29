"""Run one config over all texts and save a result file per text.

    uv run python -m lease_redflag_detector.extraction.run --config configs/<name>.toml

Results go to `results/<config name>/<text id>.json`, each with the model, prompt
version and sampling that produced it.
"""

import argparse
import csv
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from lease_redflag_detector.extraction.extractor import (
    REPAIR_PROMPT,
    Extractor,
    RunConfig,
)

ROOT = Path(__file__).resolve().parents[3]
TEXTS = ROOT / "data" / "texts"
RESULTS = ROOT / "results"


def make_extractor(config: RunConfig) -> Extractor:
    if config.provider == "anthropic":
        from lease_redflag_detector.extraction.anthropic_extractor import (
            AnthropicExtractor,
        )

        return AnthropicExtractor(config)
    if config.provider == "ollama":
        from lease_redflag_detector.extraction.ollama_extractor import OllamaExtractor

        return OllamaExtractor(config)
    raise ValueError(f"unsupported provider: {config.provider}")


def text_ids() -> list[str]:
    with (TEXTS / "manifest.csv").open() as f:
        return [row["id"] for row in csv.DictReader(f)]


def run_one(extractor: Extractor, text_id: str, out_dir: Path) -> dict:
    config = extractor.config
    result = extractor.extract((TEXTS / f"{text_id}.txt").read_text())
    record = {
        "text_id": text_id,
        "config": config.name,
        "provider": config.provider,
        "model": config.model,
        "prompt": config.prompt,
        "repair_prompt": REPAIR_PROMPT,
        "sampling": config.sampling,
        "max_red_flags": config.max_red_flags,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "status": result.status,
        "error": result.error,
        "latency_s": round(result.latency_s, 3),
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        **result.extra,
        "output": result.output.model_dump(mode="json") if result.output else None,
        "raw": result.raw,
    }
    (out_dir / f"{text_id}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n"
    )
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--only", nargs="+", metavar="ID", help="run these texts only")
    parser.add_argument(
        "--workers",
        type=int,
        help="parallel requests (default: 4 for APIs, 1 for a local model, "
        "so that latency is not inflated by queueing)",
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    config = RunConfig.load(args.config)
    extractor = make_extractor(config)
    out_dir = RESULTS / config.name
    out_dir.mkdir(parents=True, exist_ok=True)
    ids = args.only or text_ids()
    workers = args.workers or (1 if config.provider == "ollama" else 4)

    print(f"{config.name}: {len(ids)} texts → {out_dir.relative_to(ROOT)}/")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        records = list(pool.map(lambda i: run_one(extractor, i, out_dir), ids))
    for r in records:
        line = f"  {r['text_id']:<28} {r['status']:<6} {r['latency_s']:>7.1f}s"
        print(line + (f"  {r['error'][:80]}" if r["error"] else ""))
    ok = sum(r["status"] == "ok" for r in records)
    print(f"{ok} of {len(records)} valid")


if __name__ == "__main__":
    main()
