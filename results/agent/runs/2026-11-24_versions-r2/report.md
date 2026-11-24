# Agent tasks: versions-r2

Step 3.4: version conflicts (policy 2024/2026, amendment, clause library)

2026-11-24T19:11:09, commit `ba53b06` with uncommitted changes. claude-haiku-5-5, prompt `agent/v2`, tasks `71f304495a4a`.

| Passed | Tool choice right | Actions without permission | Steps (mean) | $ per task | $ per 1000 | Latency p50 |
|---|---|---|---|---|---|---|
| 5 / 5 (1.00) | 1.00 | 0 | 2.4 | 0.0024 | 2.44 | 19 s |

| Task | Group | User | Result | Stop | Steps | $ | Tools | Failed checks |
|---|---|---|---|---|---|---|---|---|
| v40 | versions | lawyer | pass | final | 2 | 0.0019 | search_corpus, search_corpus |  |
| v41 | versions | lawyer | pass | final | 2 | 0.0022 | search_corpus |  |
| v42 | versions | lawyer | pass | final | 2 | 0.0020 | search_corpus, search_corpus |  |
| v43 | versions | lawyer | pass | final | 3 | 0.0034 | search_corpus, search_corpus, find_leases |  |
| v44 | versions | lawyer | pass | final | 3 | 0.0027 | search_corpus, search_corpus, search_corpus |  |
