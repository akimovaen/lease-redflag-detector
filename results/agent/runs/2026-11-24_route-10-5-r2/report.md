# Agent tasks: route-10-5-r2

Step 3.2: open points go to the committee marked (point 10.5)

2026-11-24T16:22:40, commit `329550c` with uncommitted changes. claude-haiku-5-5, prompt `agent/v2`, tasks `d0ab2cb8d579`.

| Passed | Tool choice right | Actions without permission | Steps (mean) | $ per task | $ per 1000 | Latency p50 |
|---|---|---|---|---|---|---|
| 3 / 3 (1.00) | 1.00 | 0 | 3.7 | 0.0132 | 13.18 | 67 s |

| Task | Group | User | Result | Stop | Steps | $ | Tools | Failed checks |
|---|---|---|---|---|---|---|---|---|
| c13 | lease check | lawyer | pass | final | 3 | 0.0145 | extract_red_flags, draft_redline, draft_redline, draft_redline |  |
| c14 | queue | lawyer | pass | final | 4 | 0.0142 | extract_red_flags, draft_redline, draft_redline, draft_redline, submit_for_review |  |
| c15 | queue | lawyer | pass | final | 4 | 0.0108 | extract_red_flags, draft_redline, draft_redline, submit_for_review |  |
