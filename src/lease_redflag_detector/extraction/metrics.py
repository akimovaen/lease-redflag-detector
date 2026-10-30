"""Score extraction results against the golden set.

    uv run python -m lease_redflag_detector.extraction.metrics

Reads every `results/<config>/` folder and writes `results/metrics.md` and
`results/metrics.json` with one row per config:

- field accuracy: share of (golden text, field) pairs answered correctly; a failed
  output counts as wrong on every field. A config is scored only on the golden texts
  it was run on, so runs made before a text was added are not penalized for it;
- red flag precision, recall and F1 over the set of red flag types per text;
- % valid: share of all texts with an output that passed validation (schema,
  verbatim quotes, date order; older runs checked the schema only);
- % repaired: share of all texts that needed the repair attempt; `—` for runs
  made before the repair step existed;
- latency p50 and p95 over all texts, in seconds;
- cost per 1000 documents at the mean token usage per text.
"""

import json
import re
import statistics
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GOLDEN = ROOT / "data" / "golden"
RESULTS = ROOT / "results"

# USD per million input / output tokens, base rates without caching or batching.
# Source: https://platform.claude.com/docs/en/about-claude/pricing (checked 2026-10-28).
# Local models cost no API fees.
PRICES = {
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-opus-5-5": (4.0, 20.0),
}

STRING_FIELDS = ["lessor", "lessee", "premises_address"]
EXACT_FIELDS = ["document_type", "start_date", "end_date", "indexation"]
FIELDS = [
    "document_type",
    *STRING_FIELDS,
    "area",
    "start_date",
    "end_date",
    "rent",
    "indexation",
]
STRING_SIMILARITY = 0.85
NUMBER_TOLERANCE = 0.01


def normalize(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def strings_match(golden: str | None, predicted: str | None) -> bool:
    if golden is None or predicted is None:
        return golden is predicted
    ratio = SequenceMatcher(None, normalize(golden), normalize(predicted)).ratio()
    return ratio >= STRING_SIMILARITY


def numbers_match(golden: float, predicted: float) -> bool:
    return abs(golden - predicted) <= NUMBER_TOLERANCE * abs(golden)


def field_correct(name: str, golden: dict, predicted: dict) -> bool:
    g, p = golden[name], predicted.get(name)
    if name in STRING_FIELDS:
        return strings_match(g, p)
    if g is None or p is None:
        return g is p
    if name == "area":
        return g["unit"] == p["unit"] and numbers_match(g["value"], p["value"])
    if name == "rent":
        return (
            g["currency"].upper() == p["currency"].upper()
            and g["period"] == p["period"]
            and numbers_match(g["amount"], p["amount"])
        )
    return g == p


def percentile(values: list[float], q: float) -> float:
    """Percentile with linear interpolation between the closest ranks."""
    values = sorted(values)
    pos = (len(values) - 1) * q
    low = int(pos)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (pos - low)


@dataclass
class ConfigMetrics:
    config: str
    model: str
    prompt: str
    sampling: str
    texts: int
    golden_texts: int
    valid_pct: float
    repaired_pct: float | None
    field_accuracy: float
    flag_precision: float
    flag_recall: float
    flag_f1: float
    latency_p50_s: float
    latency_p95_s: float
    cost_per_1000_usd: float | None
    per_field: dict[str, float]


def score_config(folder: Path, golden: dict[str, dict]) -> ConfigMetrics:
    records = [json.loads(p.read_text()) for p in sorted(folder.glob("*.json"))]
    first = records[0]

    by_id = {r["text_id"]: r for r in records}
    scored = {text_id: g for text_id, g in golden.items() if text_id in by_id}

    field_hits = {name: 0 for name in FIELDS}
    tp = fp = fn = 0
    for text_id, g in scored.items():
        predicted = by_id[text_id]["output"]
        g_flags = {f["type"] for f in g["red_flags"]}
        if predicted is None:
            fn += len(g_flags)
            continue
        for name in FIELDS:
            field_hits[name] += field_correct(name, g, predicted)
        p_flags = {f["type"] for f in predicted["red_flags"]}
        tp += len(g_flags & p_flags)
        fp += len(p_flags - g_flags)
        fn += len(g_flags - p_flags)

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    latencies = [r["latency_s"] for r in records]
    cost = None
    if first["provider"] == "ollama":
        cost = 0.0
    elif first["model"] in PRICES:
        price_in, price_out = PRICES[first["model"]]
        mean_in = statistics.mean(r["input_tokens"] for r in records)
        mean_out = statistics.mean(r["output_tokens"] for r in records)
        cost = 1000 * (mean_in * price_in + mean_out * price_out) / 1e6

    return ConfigMetrics(
        config=first["config"],
        model=first["model"],
        prompt=first["prompt"],
        sampling=", ".join(f"{k}={v}" for k, v in first["sampling"].items()),
        texts=len(records),
        golden_texts=len(scored),
        valid_pct=100 * sum(r["status"] == "ok" for r in records) / len(records),
        repaired_pct=(
            100 * sum(r["attempts"] > 1 for r in records) / len(records)
            if "attempts" in first
            else None
        ),
        field_accuracy=sum(field_hits.values()) / (len(FIELDS) * len(scored)),
        flag_precision=precision,
        flag_recall=recall,
        flag_f1=f1,
        latency_p50_s=percentile(latencies, 0.5),
        latency_p95_s=percentile(latencies, 0.95),
        cost_per_1000_usd=cost,
        per_field={name: hits / len(scored) for name, hits in field_hits.items()},
    )


def to_markdown(rows: list[ConfigMetrics], golden_count: int) -> str:
    lines = [
        "# Extraction metrics",
        "",
        (
            f"Field accuracy and red flags are scored on the golden texts a config was "
            f"run on (of {golden_count}); % valid, latency and cost on all texts it was "
            "run on. Generated by `python -m lease_redflag_detector.extraction.metrics`."
        ),
        "",
        (
            "| Config | Model | Prompt | Sampling | Texts / golden | Field acc. | Flag P "
            "| Flag R | Flag F1 | % valid | % repaired | p50, s | p95, s | $ / 1000 docs |"
        ),
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        cost = "n/a" if r.cost_per_1000_usd is None else f"{r.cost_per_1000_usd:.2f}"
        repaired = "—" if r.repaired_pct is None else f"{r.repaired_pct:.0f}"
        lines.append(
            f"| {r.config} | {r.model} | {r.prompt} | {r.sampling} "
            f"| {r.texts} / {r.golden_texts} | {r.field_accuracy:.2f} "
            f"| {r.flag_precision:.2f} | {r.flag_recall:.2f} | {r.flag_f1:.2f} "
            f"| {r.valid_pct:.0f} | {repaired} | {r.latency_p50_s:.1f} | {r.latency_p95_s:.1f} | {cost} |"
        )
    lines += ["", "## Accuracy per field", ""]
    lines.append("| Config | " + " | ".join(FIELDS) + " |")
    lines.append("|---" * (len(FIELDS) + 1) + "|")
    for r in rows:
        values = " | ".join(f"{r.per_field[name]:.2f}" for name in FIELDS)
        lines.append(f"| {r.config} | {values} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    golden = {p.stem: json.loads(p.read_text()) for p in sorted(GOLDEN.glob("*.json"))}
    folders = sorted(p for p in RESULTS.iterdir() if p.is_dir())
    rows = [score_config(folder, golden) for folder in folders]
    (RESULTS / "metrics.json").write_text(
        json.dumps([asdict(r) for r in rows], indent=2) + "\n"
    )
    markdown = to_markdown(rows, len(golden))
    (RESULTS / "metrics.md").write_text(markdown)
    print(markdown)


if __name__ == "__main__":
    main()
