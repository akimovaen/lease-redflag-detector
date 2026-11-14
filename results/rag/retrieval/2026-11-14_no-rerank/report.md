# Retrieval evaluation: no-rerank

Пошук по ролях і без reranker

2026-11-14T11:23:43, commit `a73977c` with uncommitted changes. 24 red flags (5 with trap passages), 114 pieces of evidence (`evals/redflag_retrieval.toml` 10aea6a0fe31, chunks 558f6f8f5647). Recall is the share of a flag's evidence found, averaged over flags; for a role, over the flags with evidence for it.

## One list

The clause and its type description as one query, top 10, documents in force unless marked otherwise. The role columns are recall@10 of that role's evidence. Avoid: share of the trap passages in the top 10; trap first: flags where a trap passage ranks above all the right evidence.

| Config | recall@1 | recall@3 | recall@5 | recall@10 | MRR | position | wording | law | precedent | Outdated chunks in top 5 | Avoid | Trap first | Latency p50 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| structural / vector | 0.24 | 0.57 | 0.64 | 0.66 | **0.92** | 0.84 | 0.97 | 0.00 | 0.00 | 0 | 0.07 | 0 | 26 ms |
| structural / bm25 | 0.32 | 0.55 | 0.57 | 0.68 | **0.88** | 0.92 | 0.80 | 0.15 | 0.33 | 0 | 0.07 | 0 | 1 ms |
| structural / hybrid | 0.27 | 0.57 | 0.58 | 0.67 | **0.85** | 0.88 | 0.90 | 0.05 | 0.00 | 0 | 0.07 | 0 | 27 ms |
| structural / hybrid_rerank | 0.26 | 0.55 | 0.64 | 0.70 | **0.85** | 0.92 | 0.94 | 0.10 | 0.00 | 0 | 0.07 | 0 | 27 ms |
| fixed / vector | 0.27 | 0.48 | 0.56 | 0.59 | **0.84** | 0.81 | 0.77 | 0.00 | 0.00 | 0 | 0.07 | 1 | 26 ms |
| fixed / bm25 | 0.31 | 0.58 | 0.63 | 0.71 | **0.88** | 0.97 | 0.91 | 0.10 | 0.08 | 0 | 0.07 | 0 | 1 ms |
| fixed / hybrid | 0.32 | 0.58 | 0.62 | 0.66 | **0.86** | 0.92 | 0.88 | 0.00 | 0.00 | 0 | 0.07 | 1 | 26 ms |
| fixed / hybrid_rerank | 0.19 | 0.50 | 0.59 | 0.68 | **0.76** | 0.90 | 0.96 | 0.00 | 0.00 | 0 | 0.07 | 0 | 26 ms |
| structural / hybrid_rerank / all versions | 0.23 | 0.52 | 0.60 | 0.67 | **0.81** | 0.88 | 0.94 | 0.00 | 0.00 | 24 | 1.00 | 2 | 228 ms |

## By role

Hybrid search with reranking, k per role {'position': 3, 'wording': 3, 'law': 3, 'precedent': 2, 'market': 2}, reranker threshold 0.01. Empty precedent: the share of flags with no precedent whose precedent slot comes back empty. Avoid: share of the trap passages returned by any role (should be 0).

| Query | position | wording | law | precedent | Overall | Empty precedent | Avoid | Latency p50 |
|---|---|---|---|---|---|---|---|---|
| clause + type description | 0.98 | 0.94 | 0.93 | 1.00 | **0.95** | 0.39 | 0.00 | 0.1 s |
| clause only | 0.98 | 0.75 | 0.60 | 0.78 | **0.81** | 0.83 | 0.00 | 4.8 s |
| clause + type description, fixed-size chunks | 0.97 | 1.00 | 0.70 | 0.71 | **0.90** | 0.50 | 0.00 | 0.1 s |
| clause + type description, hybrid without reranker | 0.98 | 0.98 | 0.78 | 0.78 | **0.93** | 0.00 | 0.00 | 0.1 s |

## Reranker threshold

Search by role with the type description, cut at each threshold.

| Threshold | position | wording | law | precedent | Overall | Empty precedent | Avoid |
|---|---|---|---|---|---|---|---|
| 0 | 0.98 | 0.94 | 0.93 | 1.00 | 0.95 | 0.00 | 0.00 |
| 0.01 | 0.98 | 0.94 | 0.93 | 1.00 | 0.95 | 0.39 | 0.00 |
| 0.02 | 0.98 | 0.94 | 0.88 | 0.94 | 0.93 | 0.44 | 0.00 |
| 0.05 | 0.98 | 0.94 | 0.88 | 0.89 | 0.93 | 0.44 | 0.00 |
| 0.1 | 0.97 | 0.94 | 0.78 | 0.78 | 0.89 | 0.67 | 0.00 |
| 0.2 | 0.97 | 0.94 | 0.68 | 0.33 | 0.84 | 0.83 | 0.00 |
| 0.3 | 0.97 | 0.92 | 0.47 | 0.17 | 0.78 | 1.00 | 0.00 |

## Each red flag, by role

Evidence found / expected at threshold 0.01; for a flag with no precedent, whether the precedent slot came back empty; trap passages returned / listed.

| Flag | Type | Trap | position | wording | law | precedent | Avoid |
|---|---|---|---|---|---|---|---|
| f01 | tenant_break_option | outdated_policy | 4/4 | 3/3 | 1/1 | 2/2 | 0/1 |
| f02 | tenant_break_option | – | 2/2 | 2/2 | 1/1 | 3/3 | – |
| f03 | tenant_break_option | – | 2/2 | 3/3 | 1/1 | 3/3 | – |
| f04 | indexation_limited | – | 1/1 | 1/1 | 1/1 | not empty | – |
| f05 | indexation_limited | – | 2/2 | 2/2 | 1/1 | not empty | – |
| f06 | indexation_limited | – | 1/1 | 0/1 | 0/1 | not empty | – |
| f07 | indexation_limited | – | 1/2 | 1/1 | 1/1 | 4/4 | – |
| f08 | sublease_permitted | – | 2/2 | 1/1 | 1/1 | not empty | – |
| f09 | sublease_permitted | – | 2/2 | 1/1 | 1/1 | 1/1 | – |
| f10 | sublease_permitted | – | 1/1 | 1/1 | 1/1 | not empty | – |
| f11 | sublease_permitted | – | 1/1 | 1/1 | – | not empty | – |
| f12 | landlord_repairs | – | 2/2 | 2/2 | 1/1 | empty | – |
| f13 | landlord_repairs | – | 2/2 | 1/1 | 1/1 | empty | – |
| f14 | landlord_repairs | – | 1/1 | 1/1 | 1/1 | not empty | – |
| f15 | service_charges_limited | – | 2/2 | 1/1 | – | not empty | – |
| f16 | service_charges_limited | – | 1/1 | 1/1 | 1/1 | empty | – |
| f17 | service_charges_limited | – | 2/2 | 1/1 | – | empty | – |
| f18 | sublease_permitted | outdated_policy | 2/2 | 1/1 | 1/1 | not empty | 0/1 |
| f19 | landlord_repairs | outdated_policy | 2/2 | 2/2 | 1/1 | empty | 0/1 |
| f20 | indexation_limited | outdated_law | 2/2 | 1/1 | 1/1 | not empty | 0/1 |
| f21 | sublease_permitted | similar_document | 2/2 | 1/1 | 1/1 | 1/1 | 0/3 |
| f22 | tenant_break_option | not_covered | 2/2 | 1/2 | 1/2 | not empty | – |
| f23 | service_charges_limited | not_covered | 2/2 | 1/1 | – | empty | – |
| f24 | landlord_repairs | not_covered | 3/3 | 1/1 | 2/2 | empty | – |
