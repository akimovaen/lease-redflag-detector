# Agent task runs

One row per full run of `scripts/eval_agent.py`. Runs compare only on the same task set (its hash).

| Run | Note | Tasks | Passed | Tool choice | Without permission | Steps | $ per 1000 | Latency p50 |
|---|---|---|---|---|---|---|---|---|
| [2026-11-23_reviewed](2026-11-23_reviewed/report.md) | the task set reviewed by the lawyer | f0617468e88b | 0.92 | 0.89 | 0 | 2.4 | 5.65 | 10 s |
| [2026-11-23_reviewed-r2](2026-11-23_reviewed-r2/report.md) | the task set reviewed by the lawyer | f0617468e88b | 1.00 | 1.00 | 0 | 2.4 | 5.45 | 9 s |
| [2026-11-23_reviewed-r3](2026-11-23_reviewed-r3/report.md) | the task set reviewed by the lawyer | f0617468e88b | 1.00 | 1.00 | 0 | 2.4 | 5.75 | 12 s |
| [2026-11-27_final-v5](2026-11-27_final-v5/report.md) | step 3.8: the whole reviewed set on prompt agent/v5 | 0785e3f3cd32 | 0.98 | 0.97 | 0 | 2.5 | 4.69 | 8 s |
| [2026-11-27_final-v5-r2](2026-11-27_final-v5-r2/report.md) | step 3.8: the whole reviewed set on prompt agent/v5 | 0785e3f3cd32 | 1.00 | 1.00 | 0 | 2.5 | 4.65 | 6 s |
| [2026-11-27_final-v5-r3](2026-11-27_final-v5-r3/report.md) | step 3.8: the whole reviewed set on prompt agent/v5 | 0785e3f3cd32 | 0.96 | 1.00 | 0 | 2.6 | 4.88 | 7 s |
