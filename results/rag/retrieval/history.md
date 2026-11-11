# Retrieval runs

One row per run of `scripts/eval_retrieval.py`, rebuilt from the run folders. Runs compare only with the same flag set and chunks hashes. Role columns: search by role with the type description; one list: structural chunks, hybrid with reranking, recall@10. \* uncommitted changes.

| Run | Note | Flag set | Chunks | Commit | position | wording | law | precedent | Overall | Empty precedent | Avoid | One list | Latency p50 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| [2026-11-11_reviewed-set](2026-11-11_reviewed-set/report.md) | Перший прогін на перевіреному юристом наборі: 22 прапорці, з них 6 пасток | 207fb6de | 558f6f8f | `f0846e8`* | 0.98 | 0.77 | 0.82 | 0.89 | **0.86** | 0.44 | 0.00 | 0.69 | 5.2 s |
| [2026-11-11_threshold-0.01](2026-11-11_threshold-0.01/report.md) | Поріг reranker 0.05 → 0.01 | 207fb6de | 558f6f8f | `1a40fed`* | 0.98 | 0.77 | 0.92 | 1.00 | **0.90** | 0.31 | 0.00 | 0.69 | 5.2 s |
| [2026-11-11_wording-k3](2026-11-11_wording-k3/report.md) | Поріг 0.01; формулювання k 2 → 3 | 207fb6de | 558f6f8f | `1a40fed`* | 0.98 | 0.93 | 0.92 | 1.00 | **0.95** | 0.31 | 0.00 | 0.69 | 5.2 s |
| [2026-11-11_two-queries](2026-11-11_two-queries/report.md) | Кожна роль: два запити (умова + опис; лише умова), злиті RRF — гірше (0.91 проти 0.95), зміну відкочено | 207fb6de | 558f6f8f | `a6ce776`* | 0.98 | 0.93 | 0.92 | 1.00 | **0.95** | 0.31 | 0.00 | 0.69 | 5.1 s |
| [2026-11-11_f04-uah](2026-11-11_f04-uah/report.md) | f04: юані замінено на гривні; налаштування як у wording-k3 | 795b9b05 | 558f6f8f | `4b76516`* | 0.98 | 0.93 | 0.92 | 1.00 | **0.95** | 0.31 | 0.00 | 0.69 | 5.2 s |
