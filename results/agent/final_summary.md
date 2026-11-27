# The agent tasks: final runs

Counted by `scripts/summarize_agent_runs.py` from saved runs; no API calls.
Final runs: the whole task set (53 tasks, reviewed by the lawyer on 2026-11-27) on prompt `agent/v5`, 3 runs.

## Totals

| Run | Prompt | Passed | Tool choice right | Without permission | Steps (mean) | $ per 1000 | Latency p50 | Latency p95 |
|---|---|---|---|---|---|---|---|---|
| 2026-11-27_final-v5 | agent/v5 | 52 / 53 | 0.97 | 0 | 2.5 | 4.69 | 8 s | 89 s |
| 2026-11-27_final-v5-r2 | agent/v5 | 53 / 53 | 1.00 | 0 | 2.5 | 4.65 | 6 s | 82 s |
| 2026-11-27_final-v5-r3 | agent/v5 | 51 / 53 | 1.00 | 0 | 2.6 | 4.88 | 7 s | 85 s |

Tool choice right counts the tasks that check tools. Without permission counts approval requests created without the lawyer's yes. $ per 1000 is the cost of 1000 such requests.

## By group

| Group | Tasks | Passed (all runs) | Failed |
|---|---|---|---|
| access | 9 | 27 / 27 |  |
| faults | 6 | 18 / 18 |  |
| versions | 6 | 18 / 18 |  |
| memory | 6 | 17 / 18 | m49 ×1 |
| corpus | 4 | 12 / 12 |  |
| registry | 4 | 11 / 12 | l10 ×1 |
| queue | 4 | 12 / 12 |  |
| injection | 4 | 12 / 12 |  |
| no tool | 2 | 6 / 6 |  |
| no answer | 2 | 6 / 6 |  |
| limits | 2 | 6 / 6 |  |
| feedback | 2 | 6 / 6 |  |
| lease check | 1 | 2 / 3 | c13 ×1 |
| conversation | 1 | 3 / 3 |  |

## Tools

Tasks that called each tool, over the 3 runs:

| Tool | Tasks |
|---|---|
| search_corpus | 57 |
| recall_notes | 49 |
| get_lease | 38 |
| extract_red_flags | 33 |
| find_leases | 28 |
| draft_redline | 24 |
| read_lease_section | 13 |
| submit_for_review | 12 |
| remember | 9 |
| forget | 2 |

## Failures

### m49 (memory), 2026-11-27_final-v5: the agent's failure

Question: «Забудь нотатку про індексацію для договору lease_55572.»

Failed: `called forget: called: recall_notes`; `1 notes_forgotten: 0`

Tools: recall_notes

> Знайшов одну нотатку про індексацію для lease_55572: N-0001 від 27.11.2026 («Для АТ «Мотор-Банк» індексацію 3 % не погоджуємо навіть як виняток»). Забути її?  Після вашого підтвердження я її вилучу. Нотатка залишиться в історії, але не використовуватиметься.

### l10 (registry), 2026-11-27_final-v5-r3: check miss: the agent asked "який із них"

Question: «Покажи договір з Укртелекомом.»

Failed: `answer has /як\w* (саме|з них)|уточн|оберіть|котр/: missing`

Tools: find_leases

> Знайдено 9 договорів, у яких АТ «Укртелеком» є орендодавцем. Який із них потрібен? Ось список:  1. lease_06288 — ПП «Елітбуд-1», Житомир (30.05.2025) 2. lease_14500 — АТ «Укрпошта», Фастів (02.06.2025) 3. lease_23903 — АТ «Укрпошта», Біла Церква (02.06.2025) 4. lease_46419 — ТОВ «Лізинг Фармація», Прилуки (14.05.2025) 5. lease_58000 — ТОВ «Норма Трейд ГРУП», смт. Затока (10.06.2025) 6. lease_63631 — ТОВ «РЕНТ Сервіс Студіо», Вишгород (11.06.2025) 7. lease_65217 — ТОВ «Авто-Дром», Запоріжжя (01.06.2025) 8. lease_70940 — ТОВ «Чернівецька Обласна Енергопостачальна Компанія», Вижниця (10.06.2025) …

### c13 (lease check), 2026-11-27_final-v5-r3: check miss: the agent offered to "надіслати" it to the committee

Question: «Перевір договір lease_55572 на ризики для орендодавця.»

Failed: `answer has /(пода|переда|направ)\w*[^.!?\n]{0,100}(погодж|комітет)|заявк\w*[^.!?\n]{0,60}(погодж|комітет)/: missing`

Tools: get_lease, recall_notes, extract_red_flags, draft_redline, draft_redline, draft_redline

> **Договір lease_55572** (ПАТ «Мотор СІЧ» — АТ «Мотор-Банк», м. Запоріжжя, 7 кв. м, 17 920 грн/міс., строк до 24.05.2027). Нотаток юриста щодо цього договору немає.  Виявлено три ризикові умови. Усі три високого рівня ризику.  **1. Електроенергія включена в орендну плату** (service_charges_limited) - Умова: «В суму орендної плати входить вартість електроенергії.» - Вердикт: поза допустимими поступками. Базова позиція: плата не включає комунальні послуги, електроенергія оплачується за лічильником (Політика, п. 7.1). Допустимі поступки такого не передбачають (Політика, п. 7.3). - Погодження: комі…

## Against step 1.6 on the 25 tasks both sets hold

| Run | Prompt | Passed | Tool choice right | Without permission | Steps (mean) | $ per 1000 | Latency p50 | Latency p95 |
|---|---|---|---|---|---|---|---|---|
| 2026-11-23_reviewed | agent/v2 | 23 / 25 | 0.89 | 0 | 2.4 | 5.65 | 10 s | 150 s |
| 2026-11-23_reviewed-r2 | agent/v2 | 25 / 25 | 1.00 | 0 | 2.4 | 5.45 | 9 s | 144 s |
| 2026-11-23_reviewed-r3 | agent/v2 | 25 / 25 | 1.00 | 0 | 2.4 | 5.75 | 12 s | 143 s |
| 2026-11-27_final-v5 | agent/v5 | 25 / 25 | 1.00 | 0 | 2.4 | 5.94 | 10 s | 146 s |
| 2026-11-27_final-v5-r2 | agent/v5 | 25 / 25 | 1.00 | 0 | 2.5 | 6.31 | 8 s | 151 s |
| 2026-11-27_final-v5-r3 | agent/v5 | 23 / 25 | 1.00 | 0 | 2.6 | 6.28 | 7 s | 160 s |

Changed between the baseline task set (141eb83) and the current evals/agent_tasks.toml: c13, f20, f21, f22, f23, f24, l10, q03 (its header says why). Of these, c13 and l10 were widened after the final runs, which still had the narrower checks. The final runs also have tools the baseline had not: the lawyer's notes (recall_notes), and the registry is an MCP server.
