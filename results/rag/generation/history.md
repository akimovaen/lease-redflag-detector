# Generation runs

One row per full run of `scripts/run_redline.py`, scored by `scripts/eval_redline.py` against the current expected answers; facts, clause and faithfulness from the LLM judges (`scripts/judge_redline.py`). Runs compare only on the same flag set (its hash).

| Run | Note | Model | Prompt | Flag set | valid | verdict | risk | cite | gaps | facts | clause | faithfulness | $ / 1000 | Latency p50 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| [2026-11-11_haiku-v1](2026-11-11_haiku-v1/report.md) | Перший прогін генерації: Haiku, промпт v1 | claude-haiku-5-5 | `rag/v1` | 207fb6de | 1.00 | 0.86 | 0.68 | 0.98 | 0.23 | – | – | – | 3.11 | 28 s |
| [2026-11-11_haiku-v2](2026-11-11_haiku-v2/report.md) | Промпт v2: правила рівня ризику, gaps лише суттєві | claude-haiku-5-5 | `rag/v2` | 207fb6de | 1.00 | 0.86 | 0.86 | 0.98 | 0.59 | – | – | – | 2.86 | 24 s |
| [2026-11-11_haiku-v3](2026-11-11_haiku-v3/report.md) | Промпт v3: межі відступів з бібліотеки, мінімальна правка для поступки, ризик суборенди без згоди; f04 у гривнях | claude-haiku-5-5 | `rag/v3` | 795b9b05 | 1.00 | 0.95 | 0.82 | 1.00 | 0.73 | 0.93 | 0.68 | 0.72 | 2.81 | 23 s |
| [2026-11-13_haiku-v3-24](2026-11-13_haiku-v3-24/report.md) | Промпт v3 на 24 прапорцях: haiku-v3 (f01–f22) і haiku-v3-f23-f24 (нові «немає в документах»), той самий код і конфіг | claude-haiku-5-5 | `rag/v3` | 10aea6a0 | 1.00 | 0.88 | 0.83 | 1.00 | 0.75 | 0.89 | 0.62 | 0.73 | 2.82 | 23 s |
| [2026-11-14_haiku-v4](2026-11-14_haiku-v4/report.md) | Промпт v4: прогалина, що змінює вердикт, — not_covered (поле в схемі, перевірка в коді) | claude-haiku-5-5 | `rag/v4` | 10aea6a0 | 1.00 | 0.83 | 0.83 | 0.99 | 0.71 | – | – | – | 2.97 | 19 s |
| [2026-11-14_haiku-v5](2026-11-14_haiku-v5/report.md) | Промпт v5: вердикт змінює лише питання, на яке в джерелах немає правила | claude-haiku-5-5 | `rag/v5` | 10aea6a0 | 1.00 | 0.83 | 0.88 | 1.00 | 0.75 | – | – | – | 2.94 | 18 s |
