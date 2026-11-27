# How the agent uses the corpus search

Written by `scripts/search_behaviour.py` from the traces of saved runs; no API calls. Runs of different prompts or task sets are counted apart.

## Prompt agent/v2, tasks f0617468e88b

From the traces of 3 runs, 24 task runs with at least one successful search:

| Run | Prompt | Tasks | Commit |
|---|---|---|---|
| 2026-11-23_reviewed | agent/v2 | f0617468e88b | 1d5d9c2 |
| 2026-11-23_reviewed-r2 | agent/v2 | f0617468e88b | 1d5d9c2 |
| 2026-11-23_reviewed-r3 | agent/v2 | f0617468e88b | 1d5d9c2 |

### How often it searches

| Searches in the task | Task runs |
|---|---|
| 1 | 7 |
| 2 | 14 |
| 3 | 2 |
| 4 | 1 |

Task runs with a second search in the same step as the first (chosen before seeing its results): 13. With a search in a later step, after seeing them: 6.

Source roles asked for: any 33, position 9, precedent 3. Versions: current 42, all 3.

### Does it search again when the answer is not there?

| Tasks | Task runs | With a later search | Searches (mean) | Passed |
|---|---|---|---|---|
| answer in the corpus (f21, f22, q03, q04, q05, q06) | 18 | 0 | 1.6 | 18 |
| no answer in the corpus (x07, x08) | 6 | 6 | 2.7 | 6 |

In the first group the first search returned the source in 18 of 18 task runs.

Per task run:

| Run | Task | Searches | Same step | Later | Queries | Passed |
|---|---|---|---|---|---|---|
| 2026-11-23_reviewed | f21 | 1 | 0 | 0 | «хто погоджує допустимі поступки в договорі оренди» (any, step 1) | yes |
| 2026-11-23_reviewed | f22 | 1 | 0 | 0 | «хто погоджує допустимі поступки в договорі оренди» (any, step 1) | yes |
| 2026-11-23_reviewed | q03 | 1 | 0 | 0 | «хто погоджує допустимі поступки в договорі оренди» (any, step 1) | yes |
| 2026-11-23_reviewed | q04 | 2 | 1 | 0 | «дострокова відмова орендаря від договору строк повідомлення» (any, step 1); «право орендаря на дострокову відмову від договору оренди допустима поступка» (any, step 1) | yes |
| 2026-11-23_reviewed | q05 | 2 | 1 | 0 | «індексація орендної плати допустима межа поступка» (any, step 1); «щорічна індексація орендної плати відсоток» (position, step 1) | yes |
| 2026-11-23_reviewed | q06 | 2 | 1 | 0 | «комерційний комітет відступ гранична індексація орендної плати» (precedent, step 1); «граничний розмір індексації орендної плати відступи» (any, step 1) | yes |
| 2026-11-23_reviewed-r2 | f21 | 2 | 1 | 0 | «хто погоджує допустимі поступки в договорі оренди» (any, step 1); «поступки орендаря погодження комітет» (position, step 1) | yes |
| 2026-11-23_reviewed-r2 | f22 | 1 | 0 | 0 | «хто погоджує допустимі поступки в договорі оренди» (any, step 1) | yes |
| 2026-11-23_reviewed-r2 | q03 | 1 | 0 | 0 | «хто погоджує допустимі поступки в договорі оренди» (any, step 1) | yes |
| 2026-11-23_reviewed-r2 | q04 | 2 | 1 | 0 | «дострокова відмова орендаря від договору строк повідомлення» (any, step 1); «односторонню відмову орендаря від договору оренди повідомити орендодавця за місяців» (position, step 1) | yes |
| 2026-11-23_reviewed-r2 | q05 | 2 | 1 | 0 | «індексація орендної плати допустима межа поступка» (any, step 1); «щорічна індексація орендної плати відсоток інфляція» (position, step 1) | yes |
| 2026-11-23_reviewed-r2 | q06 | 2 | 1 | 0 | «комерційний комітет відступ граничний розмір індексації орендної плати» (precedent, step 1); «індексація орендної плати обмеження максимальний розмір відступ погодження» (any, step 1) | yes |
| 2026-11-23_reviewed-r3 | f21 | 2 | 1 | 0 | «хто погоджує поступки в договорі оренди» (any, step 1); «допустимі поступки погодження комерційний комітет» (any, step 1) | yes |
| 2026-11-23_reviewed-r3 | f22 | 1 | 0 | 0 | «хто погоджує допустимі поступки в договорі оренди» (any, step 1) | yes |
| 2026-11-23_reviewed-r3 | q03 | 1 | 0 | 0 | «допустимі поступки в договорі оренди погодження» (any, step 1) | yes |
| 2026-11-23_reviewed-r3 | q04 | 2 | 1 | 0 | «дострокова відмова орендаря від договору строк повідомлення поступка» (any, step 1); «право орендаря на дострокову відмову від договору оренди повідомлення за місяців» (position, step 1) | yes |
| 2026-11-23_reviewed-r3 | q05 | 2 | 1 | 0 | «межа щорічної індексації орендної плати допустима поступка» (any, step 1); «індексація орендної плати обмеження поступки орендаря» (position, step 1) | yes |
| 2026-11-23_reviewed-r3 | q06 | 2 | 1 | 0 | «комерційний комітет відступ граничний розмір індексації орендної плати» (precedent, step 1); «індексація орендної плати граничний розмір відступ погодження» (any, step 1) | yes |
| 2026-11-23_reviewed | x07 | 4 | 0 | 3 | «утримання тварин у орендованому приміщенні домашні тварини» (any, step 1); «домашні тварини орендар» (any, step 2); «тварини в приміщенні» (position, step 2); «питомці тварини заборона утримання» (any, step 3) | yes |
| 2026-11-23_reviewed | x08 | 2 | 0 | 1 | «страхова сума цивільної відповідальності орендаря мінімальна» (any, step 1); «страхування цивільної відповідальності орендаря сума страхового покриття розмір» (any, step 2) | yes |
| 2026-11-23_reviewed-r2 | x07 | 3 | 1 | 1 | «утримання тварин у орендованому приміщенні» (position, step 1); «домашні тварини орендар згода орендодавця» (any, step 1); «тварини» (any, step 2) | yes |
| 2026-11-23_reviewed-r2 | x08 | 2 | 0 | 1 | «мінімальна страхова сума цивільна відповідальність орендаря» (any, step 1); «страхування відповідальності орендаря перед третіми особами страхова сума мінімальний розмір» (any, step 2) | yes |
| 2026-11-23_reviewed-r3 | x07 | 3 | 1 | 1 | «утримання домашніх тварин орендарем у приміщенні» (position, step 1); «домашні тварини в орендованому приміщенні згода орендодавця» (any, step 1); «тварини домашні улюбленці заборона утримання» (any, step 2) | yes |
| 2026-11-23_reviewed-r3 | x08 | 2 | 0 | 1 | «страхування цивільної відповідальності орендаря мінімальна страхова сума» (any, step 1); «страхова сума відповідальності орендаря перед третіми особами розмір» (any, step 2) | yes |

### What a search costs

| Searches | Task runs | Mean $ per task | Latency p50 |
|---|---|---|---|
| 1 | 7 | 0.0012 | 4 s |
| 2 | 14 | 0.0018 | 14 s |
| 3 | 2 | 0.0020 | 17 s |
| 4 | 1 | 0.0020 | 27 s |

The rows hold different tasks: those without an answer search more and also write longer answers, so the table does not give the price of one search. A search itself takes 3.3 s (median); one in a later step also adds a model call.

Few cases (24 task runs in the two groups), so this describes the behaviour; it is not a statistical result.

## Prompt agent/v5, tasks 0785e3f3cd32

From the traces of 3 runs, 51 task runs with at least one successful search:

| Run | Prompt | Tasks | Commit |
|---|---|---|---|
| 2026-11-27_final-v5 | agent/v5 | 0785e3f3cd32 | 9ae44f8 |
| 2026-11-27_final-v5-r2 | agent/v5 | 0785e3f3cd32 | 9ae44f8 |
| 2026-11-27_final-v5-r3 | agent/v5 | 0785e3f3cd32 | 9ae44f8 |

### How often it searches

| Searches in the task | Task runs |
|---|---|
| 1 | 23 |
| 2 | 18 |
| 3 | 5 |
| 4 | 5 |

Task runs with a second search in the same step as the first (chosen before seeing its results): 27. With a search in a later step, after seeing them: 10.

Source roles asked for: any 67, position 19, precedent 4, law 3, wording 1. Versions: current 81, all 13.

### Does it search again when the answer is not there?

| Tasks | Task runs | With a later search | Searches (mean) | Passed |
|---|---|---|---|---|
| answer in the corpus (f21, f22, q03, q04, q05, q06) | 18 | 0 | 1.3 | 18 |
| no answer in the corpus (x07, x08) | 6 | 6 | 3.3 | 6 |

In the first group the first search returned the source in 18 of 18 task runs.

Per task run:

| Run | Task | Searches | Same step | Later | Queries | Passed |
|---|---|---|---|---|---|---|
| 2026-11-27_final-v5 | f21 | 2 | 1 | 0 | «хто погоджує допустимі поступки в договорі оренди» (any, step 1); «погодження поступок комерційний комітет орендодавця» (position, step 1) | yes |
| 2026-11-27_final-v5 | f22 | 1 | 0 | 0 | «хто погоджує допустимі поступки в договорі оренди» (any, step 1) | yes |
| 2026-11-27_final-v5 | q03 | 1 | 0 | 0 | «хто погоджує допустимі поступки в договорі оренди» (any, step 1) | yes |
| 2026-11-27_final-v5 | q04 | 2 | 1 | 0 | «дострокова відмова орендаря від договору строк повідомлення» (any, step 1); «право орендаря на дострокове розірвання договору допустима поступка» (position, step 1) | yes |
| 2026-11-27_final-v5 | q05 | 2 | 1 | 0 | «індексація орендної плати допустима поступка межа відсоток» (any, step 1); «щорічна індексація орендної плати обмеження орендар» (position, step 1) | yes |
| 2026-11-27_final-v5 | q06 | 2 | 1 | 0 | «комітет погодив відступ індексація орендної плати гранична межа» (precedent, step 1); «індексація орендної плати обмеження максимальний розмір» (any, step 1) | yes |
| 2026-11-27_final-v5-r2 | f21 | 1 | 0 | 0 | «хто погоджує допустимі поступки в договорі оренди» (any, step 1) | yes |
| 2026-11-27_final-v5-r2 | f22 | 1 | 0 | 0 | «хто погоджує допустимі поступки в договорі оренди» (any, step 1) | yes |
| 2026-11-27_final-v5-r2 | q03 | 1 | 0 | 0 | «хто погоджує допустимі поступки в договорі оренди» (any, step 1) | yes |
| 2026-11-27_final-v5-r2 | q04 | 1 | 0 | 0 | «дострокова відмова орендаря від договору строк повідомлення поступка» (any, step 1) | yes |
| 2026-11-27_final-v5-r2 | q05 | 1 | 0 | 0 | «щорічна індексація орендної плати допустима поступка межа» (any, step 1) | yes |
| 2026-11-27_final-v5-r2 | q06 | 2 | 1 | 0 | «комерційний комітет погодження відступу індексація орендної плати граничний розмір» (precedent, step 1); «індексація орендної плати обмеження максимальний розмір відступ» (any, step 1) | yes |
| 2026-11-27_final-v5-r3 | f21 | 1 | 0 | 0 | «хто погоджує допустимі поступки в договорі оренди» (any, step 1) | yes |
| 2026-11-27_final-v5-r3 | f22 | 1 | 0 | 0 | «хто погоджує допустимі поступки в договорі оренди» (any, step 1) | yes |
| 2026-11-27_final-v5-r3 | q03 | 1 | 0 | 0 | «хто погоджує допустимі поступки в договорі оренди» (any, step 1) | yes |
| 2026-11-27_final-v5-r3 | q04 | 1 | 0 | 0 | «дострокова відмова орендаря від договору строк повідомлення допустима поступка» (any, step 1) | yes |
| 2026-11-27_final-v5-r3 | q05 | 1 | 0 | 0 | «щорічна індексація орендної плати межа допустима поступка» (any, step 1) | yes |
| 2026-11-27_final-v5-r3 | q06 | 2 | 1 | 0 | «комерційний комітет відступ граничний розмір індексації орендної плати» (precedent, step 1); «граничний розмір індексації орендної плати відступ» (any, step 1) | yes |
| 2026-11-27_final-v5 | x07 | 4 | 1 | 2 | «домашні тварини в орендованому приміщенні» (any, step 1); «утримання тварин орендарем» (position, step 1); «тварини» (any, step 2); «домашні улюбленці орендар заборона» (any, step 2) | yes |
| 2026-11-27_final-v5 | x08 | 3 | 1 | 1 | «страхова сума цивільної відповідальності орендаря мінімальна» (any, step 1); «страхування відповідальності орендаря договір оренди» (wording, step 1); «страхова сума ліміт відповідальності страховий поліс орендаря» (any, step 2) | yes |
| 2026-11-27_final-v5-r2 | x07 | 4 | 0 | 3 | «утримання тварин у приміщенні орендар домашні тварини» (any, step 1); «домашні тварини в орендованому приміщенні» (any, step 2); «тварини» (position, step 2); «свійські тварини утримання, заборона або дозвіл орендодавця» (any, step 3) | yes |
| 2026-11-27_final-v5-r2 | x08 | 3 | 1 | 1 | «страхова сума цивільної відповідальності орендаря мінімальна» (any, step 1); «страхування цивільної відповідальності орендаря полісу» (position, step 1); «страхова сума ліміт відповідальності страховика розмір покриття» (any, step 2) | yes |
| 2026-11-27_final-v5-r3 | x07 | 3 | 1 | 1 | «утримання домашніх тварин в орендованому приміщенні» (any, step 1); «тварини у приміщенні орендаря заборона погодження орендодавця» (any, step 1); «домашні тварини собаки коти правила об'єкта» (any, step 2) | yes |
| 2026-11-27_final-v5-r3 | x08 | 3 | 1 | 1 | «мінімальна страхова сума цивільної відповідальності орендаря» (any, step 1); «страхування відповідальності орендаря страхова сума» (position, step 1); «розмір страхової суми страхування цивільної відповідальності орендаря договір оренди приміщення» (any, step 2) | yes |

### What a search costs

| Searches | Task runs | Mean $ per task | Latency p50 |
|---|---|---|---|
| 1 | 23 | 0.0021 | 8 s |
| 2 | 18 | 0.0023 | 12 s |
| 3 | 5 | 0.0027 | 13 s |
| 4 | 5 | 0.0038 | 21 s |

The rows hold different tasks: those without an answer search more and also write longer answers, so the table does not give the price of one search. A search itself takes 2.2 s (median); one in a later step also adds a model call.

Few cases (24 task runs in the two groups), so this describes the behaviour; it is not a statistical result.
