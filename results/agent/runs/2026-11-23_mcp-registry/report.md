# Agent tasks: mcp-registry

Step 2.1: the registry behind its MCP server

2026-11-23T13:47:33, commit `141eb83` with uncommitted changes. claude-haiku-5-5, prompt `agent/v2`, tasks `f0617468e88b`.

| Passed | Tool choice right | Actions without permission | Steps (mean) | $ per task | $ per 1000 | Latency p50 |
|---|---|---|---|---|---|---|
| 4 / 5 (0.80) | 0.80 | 0 | 2.4 | 0.0013 | 1.27 | 4 s |

| Task | Group | Result | Stop | Steps | $ | Tools | Failed checks |
|---|---|---|---|---|---|---|---|
| l09 | registry | pass | final | 2 | 0.0009 | find_leases |  |
| l10 | registry | pass | final | 2 | 0.0011 | find_leases |  |
| l11 | registry | pass | final | 3 | 0.0015 | find_leases, find_leases |  |
| l12 | registry | pass | final | 3 | 0.0017 | get_lease, read_lease_section |  |
| f24 | faults | FAIL | final | 2 | 0.0010 | find_leases, find_leases | find_leases ≤ 1 calls: 2 calls |

## Answers of failed tasks

### f24: Покажи договір з ТОВ «Біанчі Харків».

Не вдалося знайти договір з ТОВ «Біанчі Харків». Реєстр договорів не відповів: інструмент пошуку договорів повернув помилку про зміну формату відповіді. Повторювати пошук у цій розмові я не буду.

Що можна зробити:
- Перевірити, чи доступний сервіс реєстру договорів, і повторити запит пізніше або в новій сесії.
- Якщо є ідентифікатор договору (наприклад, lease_XXXXX), назвати його. Тоді я спробую відкрити договір напряму, без пошуку за назвою.
- Назвати місто або номер договору чи дату, якщо вони відомі.

