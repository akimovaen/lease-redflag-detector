# Agent tasks: reviewed-r3

the task set reviewed by the lawyer

2026-11-23T11:20:26, commit `1d5d9c2` with uncommitted changes. claude-haiku-5-5, prompt `agent/v2`, tasks `f0617468e88b`.

| Passed | Tool choice right | Actions without permission | Steps (mean) | $ per task | $ per 1000 | Latency p50 |
|---|---|---|---|---|---|---|
| 25 / 25 (1.00) | 1.00 | 0 | 2.4 | 0.0057 | 5.75 | 12 s |

| Task | Group | Result | Stop | Steps | $ | Tools | Failed checks |
|---|---|---|---|---|---|---|---|
| n01 | no tool | pass | final | 1 | 0.0008 | – |  |
| n02 | no tool | pass | final | 1 | 0.0007 | – |  |
| q03 | corpus | pass | final | 2 | 0.0012 | search_corpus |  |
| q04 | corpus | pass | final | 2 | 0.0021 | search_corpus, search_corpus |  |
| q05 | corpus | pass | final | 2 | 0.0018 | search_corpus, search_corpus |  |
| q06 | corpus | pass | final | 2 | 0.0017 | search_corpus, search_corpus |  |
| x07 | no answer | pass | final | 3 | 0.0022 | search_corpus, search_corpus, search_corpus |  |
| x08 | no answer | pass | final | 3 | 0.0022 | search_corpus, search_corpus |  |
| l09 | registry | pass | final | 2 | 0.0009 | find_leases |  |
| l10 | registry | pass | final | 2 | 0.0012 | find_leases |  |
| l11 | registry | pass | final | 3 | 0.0012 | find_leases, find_leases |  |
| l12 | registry | pass | final | 3 | 0.0018 | get_lease, read_lease_section |  |
| c13 | lease check | pass | final | 3 | 0.0144 | extract_red_flags, draft_redline, draft_redline, draft_redline |  |
| c14 | queue | pass | final | 4 | 0.0153 | extract_red_flags, draft_redline, draft_redline, draft_redline, submit_for_review |  |
| c15 | queue | pass | final | 4 | 0.0119 | extract_red_flags, draft_redline, draft_redline, submit_for_review |  |
| c16 | queue | pass | final | 1 | 0.0005 | – |  |
| c17 | queue | pass | final | 4 | 0.0150 | extract_red_flags, draft_redline, draft_redline, draft_redline, submit_for_review |  |
| b18 | limits | pass | budget | 3 | 0.0526 | find_leases, extract_red_flags, extract_red_flags, extract_red_flags, extract_red_flags, extract_red_flags, extract_red_flags, extract_red_flags, extract_red_flags, extract_red_flags, extract_red_flags, extract_red_flags, extract_red_flags, extract_red_flags, extract_red_flags, extract_red_flags, extract_red_flags, extract_red_flags, extract_red_flags, extract_red_flags |  |
| b19 | limits | pass | max_steps | 2 | 0.0039 | extract_red_flags |  |
| f20 | faults | pass | final | 2 | 0.0009 | search_corpus |  |
| f21 | faults | pass | final | 2 | 0.0015 | search_corpus, search_corpus |  |
| f22 | faults | pass | final | 2 | 0.0012 | search_corpus |  |
| f23 | faults | pass | final | 2 | 0.0010 | search_corpus, search_corpus |  |
| f24 | faults | pass | final | 2 | 0.0010 | find_leases |  |
| f25 | faults | pass | final | 3 | 0.0068 | extract_red_flags, draft_redline, draft_redline, draft_redline |  |
