# Generation runs

One row per full run of `scripts/run_redline.py`, scored by `scripts/eval_redline.py` against the current expected answers; facts, clause and faithfulness from the LLM judges (`scripts/judge_redline.py`). Routing: referred, no_answer and referred_extra, the shares of flags an answer with gaps sends to the lawyer (see the script). Runs compare only on the same flag set (its hash).

| Run | Note | Model | Prompt | Flag set | valid | verdict | risk | cite | gaps | referred | no_answer | referred_extra | facts | clause | faithfulness | $ / 1000 | Latency p50 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| [2026-11-11_haiku-v1](2026-11-11_haiku-v1/report.md) | Перший прогін генерації: Haiku, промпт v1 | claude-haiku-5-5 | `rag/v1` | 207fb6de | 1.00 | 0.86 | 0.68 | 0.98 | 0.41 | 1.00 | – | 1.00 | – | – | – | 3.11 | 28 s |
| [2026-11-11_haiku-v2](2026-11-11_haiku-v2/report.md) | Промпт v2: правила рівня ризику, gaps лише суттєві | claude-haiku-5-5 | `rag/v2` | 207fb6de | 1.00 | 0.86 | 0.86 | 0.98 | 0.77 | 0.89 | – | 0.31 | – | – | – | 2.86 | 24 s |
| [2026-11-11_haiku-v3](2026-11-11_haiku-v3/report.md) | Промпт v3: межі відступів з бібліотеки, мінімальна правка для поступки, ризик суборенди без згоди; f04 у гривнях | claude-haiku-5-5 | `rag/v3` | 795b9b05 | 1.00 | 0.95 | 0.82 | 1.00 | 0.91 | 0.78 | – | 0.00 | 0.93 | 0.68 | 0.72 | 2.81 | 23 s |
| [2026-11-13_haiku-v3-24](2026-11-13_haiku-v3-24/report.md) | Промпт v3 на 24 прапорцях: haiku-v3 (f01–f22) і haiku-v3-f23-f24 (нові «немає в документах»), той самий код і конфіг | claude-haiku-5-5 | `rag/v3` | 10aea6a0 | 1.00 | 0.88 | 0.83 | 1.00 | 0.92 | 0.82 | 1.00 | 0.00 | 0.89 | 0.62 | 0.73 | 2.82 | 23 s |
| [2026-11-14_ci-pr19](2026-11-14_ci-pr19/report.md) | CI run on PR 19 | claude-haiku-5-5 | `rag/v3` | 10aea6a0 | 1.00 | 0.79 | 0.83 | 1.00 | 0.79 | 0.82 | 1.00 | 0.23 | – | – | – | 2.83 | 20 s |
| [2026-11-14_haiku-v4](2026-11-14_haiku-v4/report.md) | Промпт v4: прогалина, що змінює вердикт, — not_covered (поле в схемі, перевірка в коді) | claude-haiku-5-5 | `rag/v4` | 10aea6a0 | 1.00 | 0.83 | 0.83 | 0.99 | 0.71 | 0.45 | 0.50 | 0.08 | – | – | – | 2.97 | 19 s |
| [2026-11-14_haiku-v5](2026-11-14_haiku-v5/report.md) | Промпт v5: вердикт змінює лише питання, на яке в джерелах немає правила | claude-haiku-5-5 | `rag/v5` | 10aea6a0 | 1.00 | 0.83 | 0.88 | 1.00 | 0.67 | 0.27 | 0.50 | 0.00 | – | – | – | 2.94 | 18 s |
| [2026-11-14_haiku-v3-run2](2026-11-14_haiku-v3-run2/report.md) | Промпт v3, повторний прогін 2 для розкиду | claude-haiku-5-5 | `rag/v3` | 10aea6a0 | 1.00 | 0.83 | 0.88 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | – | – | – | 2.72 | 17 s |
| [2026-11-14_haiku-v3-run3](2026-11-14_haiku-v3-run3/report.md) | Промпт v3, повторний прогін 3 для розкиду | claude-haiku-5-5 | `rag/v3` | 10aea6a0 | 1.00 | 0.88 | 0.83 | 1.00 | 0.79 | 0.73 | 1.00 | 0.15 | – | – | – | 2.85 | 18 s |
