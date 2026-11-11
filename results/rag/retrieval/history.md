# Retrieval runs

One row per run of `scripts/eval_retrieval.py`, rebuilt from the run folders. Runs compare only with the same flag set and chunks hashes. Role columns: search by role with the type description; one list: structural chunks, hybrid with reranking, recall@10. \* uncommitted changes.

| Run | Note | Flag set | Chunks | Commit | position | wording | law | precedent | Overall | Empty precedent | Avoid | One list | Latency p50 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| [2026-11-11_reviewed-set](2026-11-11_reviewed-set/report.md) | Перший прогін на перевіреному юристом наборі: 22 прапорці, з них 6 пасток | 207fb6de | 558f6f8f | `f0846e8`* | 0.98 | 0.77 | 0.82 | 0.89 | **0.86** | 0.44 | 0.00 | 0.69 | 5.2 s |
