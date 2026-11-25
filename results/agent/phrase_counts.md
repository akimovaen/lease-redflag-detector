# Phrases in the agent's answers

Counted by `scripts/count_phrases.py` from saved runs; no API calls.

## After a denial the agent offers what it cannot do: to read the lease once the lawyer confirms being the head of legal or the litigation team (step 3.7; the lawyer judged it a prompt fix, not a failure of the task)

Tasks a26, a31, a34; pattern `підтверд\w*[^.]{0,60}(керівник|судов)|якщо ви (керівник|належите|з судов)`.

| Prompt | Runs | Answers with it | Answers | Tasks |
|---|---|---|---|---|
| agent/v3 | 2026-11-25_prompt-v3, 2026-11-25_prompt-v3-r2, 2026-11-25_prompt-v3-r3 | 5 | 9 | a31, a34, a31, a34, a34 |
| agent/v4 | 2026-11-25_prompt-v4, 2026-11-25_prompt-v4-r2, 2026-11-25_prompt-v4-r3 | 0 | 9 |  |

## Asked who approves 7 % for an anchor tenant, the agent names the clause library's discrepancy (Ф-2.3 still names the general director; step 3.4, counted, not required)

Tasks v42; pattern `Ф-2\.3|[Бб]ібліотек`.

| Prompt | Runs | Answers with it | Answers | Tasks |
|---|---|---|---|---|
| agent/v3 | 2026-11-24_versions, 2026-11-24_versions-r2, 2026-11-24_versions-r3 | 3 | 3 | v42, v42, v42 |
