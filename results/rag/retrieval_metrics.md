# Retrieval evaluation

15 questions from `evals/retrieval_questions.toml`, 22 pieces of evidence, top 10. Filter: documents in force unless marked otherwise.

| Config | recall@1 | recall@3 | recall@5 | recall@10 | MRR | Outdated chunks in top 5 | Latency p50 |
|---|---|---|---|---|---|---|---|
| structural / vector | 0.17 | 0.37 | 0.53 | 0.80 | **0.43** | 0 | 20 ms |
| structural / bm25 | 0.50 | 0.67 | 0.80 | 0.83 | **0.70** | 0 | 0 ms |
| structural / hybrid | 0.33 | 0.73 | 0.80 | 0.83 | **0.64** | 0 | 20 ms |
| structural / hybrid_rerank | 0.43 | 0.73 | 0.83 | 0.90 | **0.70** | 0 | 2709 ms |
| fixed / vector | 0.13 | 0.33 | 0.33 | 0.53 | **0.34** | 0 | 23 ms |
| fixed / bm25 | 0.40 | 0.60 | 0.83 | 0.87 | **0.64** | 0 | 0 ms |
| fixed / hybrid | 0.33 | 0.47 | 0.70 | 0.73 | **0.56** | 0 | 22 ms |
| fixed / hybrid_rerank | 0.43 | 0.67 | 0.70 | 0.80 | **0.67** | 0 | 2289 ms |
| structural / hybrid_rerank / all versions | 0.37 | 0.70 | 0.77 | 0.87 | **0.65** | 11 | 2706 ms |

## Rank of each piece of evidence

– means not in the top 10.

| Question | Kind | structural / vector | structural / bm25 | structural / hybrid | structural / hybrid_rerank | fixed / vector | fixed / bm25 | fixed / hybrid | fixed / hybrid_rerank | structural / hybrid_rerank / all versions |
|---|---|---|---|---|---|---|---|---|---|---|
| r01 | policy | 6 | 1 | 2 | 1 | 2 | 1 | 1 | 1 | 2 |
| r02 | policy | 4 5 | 4 3 | 2 1 | 4 3 | – 1 | 2 4 | 3 1 | 5 2 | 4 3 |
| r03 | policy | 6 | 1 | 1 | 1 | 3 | 1 | 1 | 1 | 1 |
| r04 | law | 2 | 1 | 2 | 1 | 7 | 2 | 5 | 1 | 1 |
| r05 | outdated | 1 2 | 3 6 | 1 2 | 2 3 | 1 – | 4 3 | 1 2 | 2 3 | 3 4 |
| r06 | combined | – 1 | – 1 | – 1 | – 1 | – 2 | – 1 | – 1 | – 1 | – 1 |
| r07 | law | 4 | 3 | 4 | 5 | 10 | 4 | 5 | 9 | 7 |
| r08 | combined | 3 4 | 1 – | 2 10 | 1 10 | – 3 | 3 – | – 6 | 2 10 | 1 – |
| r09 | combined | – – | – – | – – | – 3 | – – | – 6 | – 5 | – 1 | – 3 |
| r10 | law | 6 | 1 | 1 | 1 | – | 1 | – | – | 1 |
| r11 | outdated | 2 | 4 | 2 | 2 | 7 | 4 | 3 | 1 | 2 |
| r12 | precedent | 7 | 1 | 3 | 2 | – | 1 | 4 | 2 | 2 |
| r13 | paraphrase | – – | – 5 | – – | – 6 | – – | – 5 | – – | – – | – 6 |
| r14 | policy | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| r15 | paraphrase | – 1 | 2 1 | 2 1 | 2 1 | – – | 2 1 | 1 – | 1 2 | 2 1 |
