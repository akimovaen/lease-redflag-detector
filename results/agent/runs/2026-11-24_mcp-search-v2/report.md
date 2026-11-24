# Agent tasks: mcp-search-v2

Step 2.1: registry over MCP, search_corpus v2 without registry leases

2026-11-24T12:20:32, commit `141eb83` with uncommitted changes. claude-haiku-5-5, prompt `agent/v2`, tasks `5c782b7dd28b`.

| Passed | Tool choice right | Actions without permission | Steps (mean) | $ per task | $ per 1000 | Latency p50 |
|---|---|---|---|---|---|---|
| 10 / 11 (0.91) | 1.00 | 0 | 2.3 | 0.0014 | 1.43 | 13 s |

| Task | Group | Result | Stop | Steps | $ | Tools | Failed checks |
|---|---|---|---|---|---|---|---|
| q03 | corpus | pass | final | 2 | 0.0015 | search_corpus, search_corpus |  |
| q04 | corpus | pass | final | 2 | 0.0016 | search_corpus, search_corpus |  |
| q05 | corpus | pass | final | 2 | 0.0013 | search_corpus |  |
| q06 | corpus | pass | final | 2 | 0.0016 | search_corpus, search_corpus |  |
| x07 | no answer | pass | final | 4 | 0.0023 | search_corpus, search_corpus, search_corpus, search_corpus, search_corpus |  |
| x08 | no answer | pass | final | 3 | 0.0021 | search_corpus, search_corpus, search_corpus |  |
| f20 | faults | pass | final | 2 | 0.0009 | search_corpus |  |
| f21 | faults | pass | final | 2 | 0.0015 | search_corpus, search_corpus |  |
| f22 | faults | pass | final | 2 | 0.0011 | search_corpus |  |
| f23 | faults | FAIL | final | 2 | 0.0010 | search_corpus | answer has /недоступн\|не працює\|не відповіда\|помилк/: missing |
| f24 | faults | pass | final | 2 | 0.0010 | find_leases, find_leases |  |

## Answers of failed tasks

### f23: Яку межу щорічної індексації орендної плати ми можемо погодити як допустиму поступку?

Не вдалося відповісти на це питання за документами компанії. Інструмент пошуку по корпусу (політика орендодавця, затверджені формулювання, рішення комітету) не відповів: запит завершився тайм-аутом після трьох спроб. Повторно в цьому запиті я його не викликатиму, тому назвати допустиму межу індексації з джерел не можу.

Щоб отримати відповідь, потрібно одне з двох:
- повторити запит пізніше, коли сервіс запрацює;
- перевірити вручну розділ політики орендодавця про індексацію орендної плати та розділ затверджених формулювань про індексацію.

Якщо дасте номер конкретного договору, я можу перевірити його умови про індексацію через реєстр договорів. Для цього теж потрібен доступ до пошуку по корпусу, щоб порівняти умови з межами політики.

