# Agent tasks: versions

Step 3.4: version conflicts (policy 2024/2026, amendment, clause library)

2026-11-24T19:10:39, commit `ba53b06` with uncommitted changes. claude-haiku-5-5, prompt `agent/v2`, tasks `71f304495a4a`.

| Passed | Tool choice right | Actions without permission | Steps (mean) | $ per task | $ per 1000 | Latency p50 |
|---|---|---|---|---|---|---|
| 5 / 5 (1.00) | 1.00 | 0 | 2.2 | 0.0023 | 2.28 | 28 s |

| Task | Group | User | Result | Stop | Steps | $ | Tools | Failed checks |
|---|---|---|---|---|---|---|---|---|
| v40 | versions | lawyer | pass | final | 2 | 0.0021 | search_corpus, search_corpus |  |
| v41 | versions | lawyer | pass | final | 2 | 0.0020 | search_corpus |  |
| v42 | versions | lawyer | pass | final | 2 | 0.0022 | search_corpus, search_corpus |  |
| v43 | versions | lawyer | pass | final | 2 | 0.0021 | search_corpus, search_corpus |  |
| v44 | versions | lawyer | pass | final | 3 | 0.0029 | search_corpus, search_corpus, search_corpus |  |
