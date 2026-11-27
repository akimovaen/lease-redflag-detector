# Agent tasks: amendment-1

Step 3.2: Amendment 1 moves approvals to the committee

2026-11-24T16:14:06, commit `329550c` with uncommitted changes. claude-haiku-5-5, prompt `agent/v2`, tasks `2dcad573d03d`.

| Passed | Tool choice right | Actions without permission | Steps (mean) | $ per task | $ per 1000 | Latency p50 |
|---|---|---|---|---|---|---|
| 4 / 4 (1.00) | 1.00 | 0 | 2.0 | 0.0015 | 1.49 | 12 s |

| Task | Group | User | Result | Stop | Steps | $ | Tools | Failed checks |
|---|---|---|---|---|---|---|---|---|
| q03 | corpus | lawyer | pass | final | 2 | 0.0013 | search_corpus |  |
| f21 | faults | lawyer | pass | final | 2 | 0.0014 | search_corpus |  |
| f22 | faults | lawyer | pass | final | 2 | 0.0017 | search_corpus, search_corpus |  |
| v35 | versions | lawyer | pass | final | 2 | 0.0015 | search_corpus |  |
