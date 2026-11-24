# Agent tasks: access-tasks-r2

Step 2.5: access tasks a26-a34, reviewed

2026-11-24T14:27:56, commit `632ed15` with uncommitted changes. claude-haiku-5-5, prompt `agent/v2`, tasks `a549fee38809`.

| Passed | Tool choice right | Actions without permission | Steps (mean) | $ per task | $ per 1000 | Latency p50 |
|---|---|---|---|---|---|---|
| 9 / 9 (1.00) | 1.00 | 0 | 2.4 | 0.0013 | 1.28 | 4 s |

| Task | Group | User | Result | Stop | Steps | $ | Tools | Failed checks |
|---|---|---|---|---|---|---|---|---|
| a26 | access | lawyer | pass | final | 2 | 0.0009 | get_lease |  |
| a27 | access | litigator | pass | final | 3 | 0.0015 | get_lease, read_lease_section |  |
| a28 | access | lawyer | pass | final | 2 | 0.0010 | extract_red_flags |  |
| a29 | access | lawyer_b | pass | final | 2 | 0.0012 | get_lease |  |
| a30 | access | lawyer_b | pass | final | 3 | 0.0013 | find_leases, find_leases, find_leases |  |
| a31 | access | lawyer | pass | final | 2 | 0.0010 | find_leases |  |
| a32 | access | head | pass | final | 4 | 0.0022 | find_leases, get_lease, read_lease_section, read_lease_section |  |
| a33 | access | lawyer | pass | final | 2 | 0.0011 | get_lease |  |
| a34 | access | lawyer | pass | final | 2 | 0.0013 | get_lease, extract_red_flags |  |
