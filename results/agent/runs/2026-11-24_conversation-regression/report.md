# Agent tasks: conversation-regression

Step 3.5a: single questions through the conversation runner

2026-11-24T19:31:59, commit `7579aa3` with uncommitted changes. claude-haiku-5-5, prompt `agent/v2`, tasks `310832f889d6`.

| Passed | Tool choice right | Actions without permission | Steps (mean) | $ per task | $ per 1000 | Latency p50 |
|---|---|---|---|---|---|---|
| 5 / 5 (1.00) | 1.00 | 0 | 2.4 | 0.0045 | 4.51 | 8 s |

| Task | Group | User | Result | Stop | Steps | $ | Tools | Failed checks |
|---|---|---|---|---|---|---|---|---|
| n01 | no tool | lawyer | pass | final | 1 | 0.0008 | – |  |
| q03 | corpus | lawyer | pass | final | 2 | 0.0017 | search_corpus, search_corpus |  |
| l12 | registry | lawyer | pass | final | 3 | 0.0017 | get_lease, read_lease_section |  |
| c14 | queue | lawyer | pass | final | 4 | 0.0170 | extract_red_flags, draft_redline, draft_redline, draft_redline, draft_redline, submit_for_review |  |
| f21 | faults | lawyer | pass | final | 2 | 0.0014 | search_corpus |  |
