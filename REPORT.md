# Report — stage 1: structured extraction

Extract the key terms of a commercial lease and the clauses that are risky for the
**landlord** into a fixed schema, and compare a paid API model with a local one.

## Setup

**Data** ([data/README.md](data/README.md)). 30 lease texts, from 500 to 9,600 words:

- **Group A (15):** English leases from the ALeaseBERT benchmark, converted to plain text.
- **Group B (5):** other ALeaseBERT leases rendered as scans and read back with Tesseract
  OCR at three noise levels.
- **Group C (10):** Ukrainian leases: six signed leases of state property published on
  Prozorro.Sale as scans and read with Tesseract (`ukr+eng`), three municipal leases
  with the publisher's OCR text layer, and a lease template. Personal data is
  pseudonymized.

The texts include OCR errors (Cyrillic read as Latin look-alikes in group C), broken
layout, checkbox forms, unfilled template fields, broken encoding and fragments in
other languages. 10 of them form the golden set (5 from A, 2 from B, 3 from C), labeled by the rules
in `data/README.md`.

**Schema** ([schema.py](src/lease_redflag_detector/extraction/schema.py)).
`LeaseAbstract` has 10 fields: document type, lessor, lessee, premises address, area
(value and unit), start and end date, rent (amount, currency and period), indexation,
and a list of red flags. Each red flag has one of 5 types and a verbatim quote. The
field descriptions are sent to the model as part of the JSON schema.

**Pipeline** ([extractor.py](src/lease_redflag_detector/extraction/extractor.py)).
1. One request per text, with the output constrained to the schema by structured
   outputs: Anthropic `output_config.format` for Claude, Ollama `format` for the local
   model.
2. Validation. The output must match the schema, every quote must appear verbatim in
   the text (whitespace ignored), and the end date may not be before the start date.
3. If validation fails, the model gets its answer back with the list of problems and
   one repair attempt ([repair/v1](prompts/repair/v1.md)). If the second answer is
   invalid too, the result is `failed`.
4. Every result in `results/<config>/` records the model, prompt version, sampling,
   attempts, first error, token usage and latency.

API errors are retried by the Anthropic SDK (3 retries, 180 s timeout); Ollama
requests by the extractor (2 retries with backoff, 900 s timeout).

**Models.**
- `claude-sonnet-5-5` and `claude-haiku-5-5` through the Anthropic API.
- `qwen3:8b` (Q4_K_M, 5.2 GB) through Ollama on a MacBook Pro M1 Pro with 16 GB RAM,
  thinking off, 32k context.

**Sampling.** Current Claude models accept no `temperature` or `top_p`; the knob they
expose is the effort level, kept at `medium`. Temperature and top_p are compared on
qwen3:8b: `t0` = temperature 0, top_p 1; `t07` = temperature 0.7, top_p 0.8 (the values
Qwen recommends for non-thinking mode).

**Metrics** ([metrics.py](src/lease_redflag_detector/extraction/metrics.py)).
- Field accuracy: share of correct (golden text, field) pairs over the 9 scalar
  fields. Names and addresses match at similarity ≥ 0.85 after normalization,
  numbers within 1%, dates and enums exactly. A correct `null` counts as correct, and
  a failed output counts as wrong on every field.
- Red flags: precision, recall and F1 over the set of red flag types per golden text.
- % valid, latency p50/p95: over all texts the config was run on.
- Cost per 1000 documents: at the mean token usage per text and the
  [list prices](https://platform.claude.com/docs/en/about-claude/pricing) of
  2026-10-28 ($2 / $10 per million input / output tokens for Sonnet 5.5, $0.10 /
  $0.50 for Haiku 5.5). The local model has no API cost.

A config is scored only on the texts it was run on; runs made before group C existed
cover 20 texts and 7 golden texts. Reproduce with `make run CONFIG=configs/<name>.toml`;
`make metrics` rescores all runs into [results/metrics.md](results/metrics.md).

## Results: model × prompt × sampling

All rows below use the full pipeline (schema, quote and date validation, one repair).

| Model | Prompt | Sampling | Texts / golden | Field acc. | Flag P | Flag R | Flag F1 | % valid | % repaired | p50, s | p95, s | $ / 1000 docs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-sonnet-5-5 | v1 | effort medium | 30 / 10 | 0.93 | 0.88 | 0.75 | 0.81 | 100 | 0 | 3.7 | 10.0 | 34.33 |
| claude-sonnet-5-5 | v2 | effort medium | 30 / 10 | **0.98** | 0.80 | 0.80 | 0.80 | 100 | 0 | 4.2 | 9.7 | 35.24 |
| claude-sonnet-5-5 | v3 | effort medium | 30 / 10 | **0.98** | **0.89** | 0.80 | **0.84** | 100 | 0 | **3.4** | **8.2** | 34.18 |
| claude-haiku-5-5 | v1 | effort medium | 30 / 10 | 0.94 | 0.68 | **0.95** | 0.79 | 100 | 10 | 12.0 | 20.4 | 3.16 |
| claude-haiku-5-5 | v2 | effort medium | 30 / 10 | 0.97 | 0.73 | **0.95** | 0.83 | 100 | 10 | 11.5 | 21.5 | 3.19 |
| claude-haiku-5-5 | v3 | effort medium | 30 / 10 | 0.96 | 0.80 | 0.80 | 0.80 | 100 | 3 | 10.8 | 14.9 | 2.89 |
| qwen3:8b | v1 | t0, capped | 20 / 7 | 0.25 | 0.50 | 0.11 | 0.18 | 40 | 65 | 89.6 | 162.6 | 0 |
| qwen3:8b | v3 | t0, capped | 30 / 10 | 0.39 | 0.39 | 0.35 | 0.37 | 53 | 60 | 92.3 | 321.7 | 0 |
| qwen3:8b | v3 | t07, capped | 30 / 10 | 0.29 | 0.47 | 0.35 | 0.40 | 50 | 60 | 87.9 | 352.9 | 0 |

"Capped" is the fix for looping described in error 1 below: at most 8 red flags in the
decoding grammar and `repeat_penalty` 1.1. The qwen3:8b v1 run was not repeated on group
C to save about an hour of local compute.

### Sampling on the local model

The two v3 rows above are the sampling comparison: same prompt, pipeline and 30 texts,
only temperature and top_p differ.

- **No measurable difference.** Of the 10 golden texts, t0 returns a valid output on 5
  and t07 on 4; the other outputs are identical in status. The gap in field accuracy
  (0.39 vs 0.29) is that one text, `uk_prz_91885`, failing the quote check at t07: a
  failed output counts as wrong on all 9 fields. Flag F1 (0.37 vs 0.40) and latency
  are within the run-to-run noise of a 10-text set.
- **The quote check, not sampling, limits qwen3:8b.** At either setting half of its
  outputs fail it even after the repair (error 3 below).

Earlier runs on prompt v1 showed the same picture before the quote check and group C
existed (schema validation only, 20 texts, 7 golden; results of commit `9741669`):

| Config | Field acc. | Flag F1 | % valid | p50, s | p95, s |
|---|---|---|---|---|---|
| qwen3:8b t0 | 0.25 | 0.27 | 25 | 241 | 359 |
| qwen3:8b t07 | 0.25 | 0.18 | 25 | 253 | 367 |
| qwen3:8b t0, capped | 0.83 | 0.50 | 100 | 54 | 127 |
| qwen3:8b t07, capped | 0.83 | 0.51 | 100 | 60 | 138 |

Temperature and top_p made no difference there either; constraining the structure of
the output did: valid outputs went from 25% to 100% and latency fell four times.
`results/qwen3-8b-t0`, `-t07` and `-t07-capped` still hold these v1 runs, while
`results/qwen3-8b-t0-capped` was rerun later with the quote check, so in
[results/metrics.md](results/metrics.md) only the v3 pair compares sampling on equal
terms.

### Ukrainian leases

- **Few red flags.** The Prozorro.Sale leases are written on standard forms of state
  and municipal landlords and protect the landlord: the tenant pays the costs, may not
  sublet, and only the landlord may end the lease early. Of the two in the golden set,
  one has no red flag and one has a single flag. They test whether a model invents
  flags, and the Claude models mostly do not (one false positive by Haiku v3).
- **The repair step pays off.** On the Cyrillic OCR text Haiku returned 7 quotes that
  were not verbatim across its three runs; every one was fixed by the repair attempt,
  so all its outputs are valid. On English text it never needed a repair.
- **qwen3:8b invents quotes.** Half of its outputs on group C fail the quote check
  after the repair, one with a quote that is not in the lease at all ("Не, сублесування
  не дозволен…", "No, subleasing is not permitted").
- **A subtle clause is missed.** Both Claude models miss the stabilization clause in
  `uk_prz_c9bfc288` ("the terms of the lease remain in force … even if later legislation
  worsens the tenant's position"), labeled `indexation_limited`. Nothing in the prompt
  or the schema describes this kind of clause.

### How much the numbers can be trusted

- **The golden set has 10 texts.** One red flag type more or less in one text moves
  F1 by about 0.04, and one field by 0.011 in field accuracy.
- **Runs are not repeatable.** The same Sonnet v1 config scored F1 0.77 in its first
  run and 0.85 in the second, on the 7 English golden texts (error 4). Differences
  between prompt versions of the same model are within that range, except for the v2
  regression.
- **The golden set was drafted by Claude** (Opus 5.5) and corrected by hand, so the
  scores of Claude models may be biased upward.
- **v2 and v3 were written after looking at errors on the same golden texts** they are
  scored on, so part of their gain may be overfitting. Group C was added after v3 and
  is free of this.

## Error analysis

Errors 1–5 were found on the 20 English texts and 7 golden ones, before group C; the
numbers in them are from those runs.

### 1. qwen3:8b loops on the red flag list

**Seen:** with prompt v1, 15 of 20 outputs ran into the 4,000-token output limit in both
sampling configs, at 4–6 minutes per text. In `alb_lease_contract_201` the model
listed one clause, "Party B has the priority to lease the house after the contract
expires…", as `tenant_break_option` dozens of times until the JSON was cut off.

**Cause:** greedy or near-greedy decoding of a long list in a grammar-constrained
output. Once the model repeats an item, the repetition becomes the most likely
continuation, and the grammar allows the list to go on forever. A higher temperature
did not break the loop (25% valid in both configs).

**Fix:** `max_red_flags = 8` in the run config adds `maxItems` to the schema that Ollama
compiles into the grammar, so the list must close after 8 items; `repeat_penalty` 1.1
makes the repetition less likely. Valid outputs went from 25% to 100%. The model still
repeats clauses within the 8 items, but the output now ends.

### 2. Prompt v2 made the models flag the rent clause

**Seen:** v2 raised field accuracy (Sonnet 0.92 → 0.98) but lowered red flag F1 (Sonnet
0.85 → 0.78, Haiku 0.88 → 0.83). Both models now returned `indexation_limited` for
3 of 7 golden texts that have no such clause, quoting the clause that sets the rent:
"The rent is 1.2 million Yuan, and Party B shall pay 100000 Yuan to Party A before 15
of each month as the monthly rent." (`alb_lease_contract_201`).

**Cause:** v2 added the rule "a rent that stays unchanged for the whole term … is a red
flag" to catch explicit rent freezes, which v1 missed. The models read it literally:
any fixed rent stays unchanged.

**Fix:** v3 limits the flag to an explicit clause that freezes, caps or conditions rent
increases during the term, and says the rent amount and the rent for a renewal are not
red flags. F1 returned to the v1 level (Sonnet 0.86, Haiku 0.83) while the field gains
of v2 stayed. Prompt versions are kept side by side in [prompts/](prompts/CHANGELOG.md),
so the regression could be measured and the rest of v2 kept.

### 3. qwen3:8b does not copy quotes verbatim

**Seen:** with the quote check, only 40% (v1) and 55% (v3) of qwen3:8b outputs on the
English texts are valid. The repair attempt rarely helps: it fixed 1 of 13 outputs on
v1 and 3 of 12 on v3. Claude never needed a repair on English text: all its quotes
were verbatim.

**Cause:** most of the rejected quotes are close to the text but not equal to it:

| The text | qwen3:8b |
|---|---|
| `“B” shall bear the other repair expense.` | `"B" shall bear the other repair expense.` |
| `Party B shal bear the costs of water…` (OCR error) | `Party B shall bear the costs of water…` |
| `4.16.2 Not to assign or agree to assign…` | `4.16 Alienation 4.16.2 Not to assign…` (heading glued on) |
| `Lessee shall be obligated to repair…` | `Lessee shall be under obligation to repair…` |

Normalizing quote marks alone would not change the count, because almost every
rejected output also has a corrected OCR error or a reworded phrase. Accepting quotes
with similarity ≥ 0.9 would make 15–16 of 20 outputs valid.

**Decision:** keep the strict check. A quote the landlord's lawyer cannot find in the
lease is not a citation, and the low % valid is an honest measure of that. Snapping
near-verbatim quotes to the exact text span is the next step (see below).

### 4. Sonnet misses red flags, and not consistently

**Seen:** in its first run with prompt v1, Sonnet returned no red flags for
`alb_lease_contract_259`, which has five (three service charges borne by the landlord,
a repairs clause and a break option). In the second run of the same config it found
two of the three types, and F1 over the golden set went from 0.77 to 0.85. Sonnet's
precision is at least as high as its recall in every prompt version; Haiku with v1 and v2 is
the other way round (recall 0.95 on the 10 golden texts, precision 0.68–0.73).

**Cause:** the red flag types need a judgment of whose risk a clause is. Sonnet tends to
skip borderline clauses, and with no temperature control the judgment varies between
runs.

**Consequence:** single runs on a small golden set cannot rank configs whose F1 differs
by less than about 0.08. A larger golden set, or several runs per config, is needed
before choosing between Sonnet and Haiku on red flags alone.

### 5. Which area is "the area"

**Seen:** `alb_lease_contract_201` says "the workshop … with the building area of 10000
square meters and usable area of 3000 square meters". The golden value is 10,000, the
total leased; Sonnet v1 returned 3,000.

**Fix:** v2 and v3 say to take the total when several areas are given. Area accuracy of
Sonnet went from 0.86 to 1.00, with no change for Haiku, which was already right.

**Errors that remain** with prompt v3:
- **Keyword matching on the definition.** Both Claude models flag "The Landlord shall
  be obliged to have a valid insurance policy for the Premises…" in
  `alb_lease_contract_54` as `service_charges_limited`. The clause only says the
  landlord insures its own property, which is normal; nothing in it stops the landlord
  from recovering the cost. The schema lists insurance among the costs the flag is
  about, and the models seem to react to the word. The definition should say that the
  flag is about costs the landlord cannot pass on to the tenant.
- **Type confusion.** In `alb_lease_contract_201` Sonnet labels the tenant's right to
  refuse fees other than the rent as `indexation_limited` instead of
  `service_charges_limited`. In `uk_prz_91885` Haiku labels the duty to re-sign the
  lease with the tenant's successor after a reorganization as `sublease_permitted`.
- **Handover defects.** Haiku flags the landlord's duty to remedy defects found at
  handover (`alb_lease_contract_54`) as `landlord_repairs`. The labeling rules were
  settled after v3 (it is not a red flag), so the rule goes into the next prompt.
- **OCR noise passes the quote check.** In `ocr_lease_contract_199` Haiku returned a
  `landlord_repairs` flag whose quote is `qay“a`, an OCR fragment of a garbled clause.
  The quote is verbatim, so validation accepts it. A minimum quote length would catch
  this case.
- **The last day of the term.** For a 5-year lease starting on 2026-03-02 both Claude
  models give 2031-03-02 as the end date; the golden set, like the leases that state
  both dates, takes the day before (2031-03-01).
- **Address scoring.** The address similarity metric rejects an answer that adds the
  land registry details to the golden address. This is a limit of the metric, not
  necessarily a wrong answer.

## Production choice

**Claude Haiku 5.5 with prompt v3, effort medium, strict validation with one repair.**

- **Quality.** Field accuracy 0.96 and red flag F1 0.80, against 0.98 and 0.84 for
  Sonnet v3. The red flag gap is within the run-to-run variation of a single config
  (about 0.08). Haiku with v1 and v2 reaches recall 0.95, at the cost of more false
  positives; v3 is chosen because it removes a known failure (error 2).
- **Cost.** $2.89 per 1000 documents, 12 times less than Sonnet ($34.18).
- **Latency.** p50 11 s, p95 15 s per lease. Fine for review of uploaded documents;
  Sonnet (p50 3 s) is the choice if extraction has to be interactive.
- **Reliability.** 100% valid outputs. On Ukrainian OCR text 3% of its outputs needed
  the repair attempt, and all of them passed after it.

**Not the local model.** qwen3:8b on a 16 GB laptop gets field accuracy 0.39 and red
flag F1 0.37 at 1.5–5 minutes per lease, half of its outputs fail the quote check, and
it invents quotes in Ukrainian. It would only be worth it where leases may not leave
the premises, and then with a larger model and quote snapping.

## Budget

About $4.00 of the $5 budget was spent on the Anthropic API, including runs that were
later overwritten. Cyrillic OCR text costs more tokens per word than English: the 10
Ukrainian texts took $1.57 across six configs, about as much as the first 20 texts. The
local runs cost no API fees.

## Next steps

- Group D: short addenda and side letters, to test `document_type`.
- Prompt v4: the handover defects rule, `service_charges_limited` limited to costs the
  landlord cannot pass on to the tenant, stabilization clauses as `indexation_limited`,
  and the last day of the term. Validation: a minimum quote length.
- Snap near-verbatim quotes to the exact span of the text, so that local models can
  pass the quote check without loosening it.
- Repeat each config several times to measure variance before comparing prompts.

# Report — stage 2: RAG

An assistant for the lawyer of a landlord: given a red flag from stage 1 (its type and
the clause quote), it finds what the leasing policy, the clause library, the law and
the committee minutes say, and proposes a redline with a verdict, a risk level and a
citation for every claim. The corpus and the chunking (structural against fixed-size
windows, with the comparison) are described in the [README](README.md#stage-2-rag).

## Setup

**Search by role** (`rag/redline_search.py`). A redline has parts, and each part rests
on its own kind of source. A role is that part together with the documents it is
searched in:

| Role | Searched in | k | What it gives the redline |
|---|---|---|---|
| position | leasing policy | 3 | what the landlord requires, i.e. what is wrong with the clause |
| wording | clause library | 3 | approved clauses to base the changed clause on |
| law | laws in force, without the state-property regime (Law 157-IX) | 3 | the bounds of the change: mandatory rules, caps |
| precedent | lease committee minutes | 2 | deviations the committee has approved before |
| market | market research, signed leases | 2 | background only; not scored |

Why separately: in one ranked list over the whole corpus the policy and the library
match the clause best and crowd out the law and the minutes (see the second table under
[Retrieval](#retrieval)). Each role is one hybrid search (multilingual-e5 vectors +
BM25 over lemmas, fused with RRF, reranked by bge-reranker-v2-m3) with a metadata
filter, which also keeps outdated and wrong-regime documents out. The query is the
clause plus a description of the red flag type. Hits under a reranker score of 0.01 are
dropped, so a role with nothing relevant (most flags have no precedent) comes back
empty instead of filling the context with noise.

**Generation** (`rag/redline.py`, prompt `rag/v3`, Haiku). Sources are numbered S1…
in a 6,000-token context; the policy points on how to assess a change and on approval
are always included. The answer is structured output: a verdict by the levels of the
policy (compliant, concession, beyond concessions, unacceptable, not covered), findings
and a risk reason as claims with source ids, the risk level, the changed clause with
its sources, gaps (points the sources do not settle) and conflicts between sources.
Who approves follows from the verdict in code. Every cited id is checked against the
context, with one repair attempt.

**Test set** (`evals/`). 24 red flags, written before any model answer and reviewed
by the landlord's lawyer, who corrected every expected answer:

- `redflag_retrieval.toml`: the clause and, per role, the passages the search must
  find, as quotes copied from the documents, so any chunking is scored alike;
- `redline_expected.toml`: verdict, risk, key facts, documents that must be cited,
  whether gaps are expected;
- 8 traps: 3 clauses that the outdated 2024 policy allowed (f01, f18, f19), a clause
  built on the repealed Commercial Code (f20), a sublease clause that matches the
  state-property law better than the Civil Code (f21), and 3 on "is there an answer at
  all". f22 (termination because of war) looks uncovered but is
  settled by the general rule of policy 4.3; f23 (generator costs) and f24 (war damage
  repairs) are not settled, and the expected verdict is not_covered.

## Retrieval

Recall of the role search: the share of a flag's expected passages that its role
returns, averaged over flags. Avoid: the share of trap passages (outdated or
wrong-regime documents) any role returns; it must be 0. Every run is kept in
`results/rag/retrieval/`, with [history.md](results/rag/retrieval/history.md).

| Run | position | wording | law | precedent | Overall | Avoid |
|---|---|---|---|---|---|---|
| reviewed set, threshold 0.05, wording k 2 | 0.98 | 0.77 | 0.82 | 0.89 | 0.86 | 0.00 |
| threshold 0.01 | 0.98 | 0.77 | 0.92 | 1.00 | 0.90 | 0.00 |
| wording k 3 | 0.98 | 0.93 | 0.92 | 1.00 | **0.95** | 0.00 |
| two queries fused (rejected) | 0.98 | 0.86 | 0.79 | 1.00 | 0.91 | 0.00 |
| **24 flags** (f23, f24 added) | 0.98 | 0.94 | 0.93 | 1.00 | **0.95** | 0.00 |

The role search against one list over the whole corpus, on the 24 flags:

| Search | Recall | position | wording | law | precedent | Avoid |
|---|---|---|---|---|---|---|
| one list, top 10, structural chunks, hybrid + rerank | 0.70 | 0.92 | 0.94 | 0.10 | 0.00 | 0.07 |
| same, fixed-size chunks | 0.68 | 0.90 | 0.96 | 0.00 | 0.00 | 0.07 |
| same, outdated documents not filtered out | 0.67 | 0.88 | 0.94 | 0.00 | 0.00 | 1.00 |
| **by role**, clause only | 0.81 | 0.98 | 0.75 | 0.60 | 0.78 | 0.00 |
| **by role**, clause + type description | **0.95** | 0.98 | 0.94 | 0.93 | 1.00 | 0.00 |
| same, fixed-size chunks | 0.90 | 0.97 | 1.00 | 0.70 | 0.71 | 0.00 |

One list of 10 is filled by the policy and the library, which match the clause best;
the law and the minutes almost never make it. Searching each role separately, with
about the same number of chunks (11), finds the law article and the precedent for
nearly every flag. The type description in the query adds the vocabulary the clause
lacks ("суборенда", "згода наймодавця") and is worth 0.14. The status filter is what
keeps the traps out: without it every trap passage is returned.

Structural chunks against fixed windows matter little in one list (0.70 against
0.68) but in the role search they are 0.95 against 0.90 (run `2026-11-14_fixed-roles`).
The difference is in the law (0.93 against 0.70) and the precedents (1.00 against
0.71), the short units: a 350-token window holds parts of two or three articles or
decisions, which likely dilutes the match (not checked hit by hit). Fixed windows find the library
wording slightly better (1.00 against 0.94), since one window often holds a clause and
its neighbour. The reranker threshold was chosen on the structural chunks, which
favours them somewhat.

The reranker threshold and k were chosen on this set, so 0.95 is optimistic: there is
no held-out set yet.

## Answers

Scored against the expected answers, every run in `results/rag/generation/` with
[history.md](results/rag/generation/history.md). Deterministic scores: valid (passed
validation), verdict and risk (equal to the expected), cite (share of the expected
documents among the cited ones), gaps (named exactly when expected). From the LLM
judges: facts (share of the key facts the answer states, partial as half), clause
(changed clause good 1, minor edits 0.5, wrong or missing 0) and faithfulness (share of
the claims their cited sources support).

| Run | Flags | valid | verdict | risk | cite | gaps | facts | clause | faithfulness | $ / 1000 flags | p50 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Haiku, prompt v1 | 22 | 1.00 | 0.86 | 0.68 | 0.98 | 0.23 | | | | 3.11 | 28 s |
| Haiku, prompt v2 | 22 | 1.00 | 0.86 | 0.86 | 0.98 | 0.59 | | | | 2.86 | 24 s |
| Haiku, prompt v3 | 22 | 1.00 | 0.95 | 0.82 | 1.00 | 0.73 | 0.93 | 0.68 | 0.72 | 2.81 | 23 s |
| **Haiku, prompt v3** | **24** | 1.00 | **0.88** | 0.83 | 1.00 | 0.75 | 0.89 | 0.62 | 0.73 | 2.82 | 23 s |

v1 and v2 were scored against the draft of the expected answers, which the lawyer then
corrected (f04 also changed currency), so the rows compare only roughly. The 24-flag
run merges the 22 answers of v3 with the two new flags run on the same code and config
(`scripts/merge_runs.py`). The two new flags take verdict from 0.95 to 0.88: both are
missed (error 2).

19 of the 24 expected verdicts are `unacceptable`, so an answer that always says so
would score 0.79 on verdict; the metric is read with that in mind.

### The judge and its calibration

The judges are Sonnet with structured output (`prompts/judge/`). The answer judge sees
the clause, the expected answer and the model's answer, and grades each key fact and
the changed clause. The faithfulness judge sees every claim with the full text of the
chunks it cites, and grades it supported, partly supported or not.

The lawyer graded 12 answers of the v3 run by hand (46 key facts, 12 changed clauses,
`evals/judge_calibration.toml`), without seeing the judge's grades
([judge_calibration.md](results/rag/judge_calibration.md)):

| | Grades | Exact agreement | Cohen's kappa |
|---|---|---|---|
| Key facts | 46 | 0.74 | 0.14 |
| Changed clause | 12 | 0.58 | 0.25 |

The judge is **too lenient on facts**: 4 of the 5 facts the lawyer found missing it
counts as present, because the answer touches the point without stating it. It is
**too strict on the clause**: all 5 disagreements are "good" from the lawyer against
"minor edits" from the judge, which marks down a clause for anything beyond the minimal
edit, while the lawyer asks whether it can go into the lease as it is. High agreement
with a kappa near zero means the judge agrees on the common case (a fact that is
there) and not on the rare ones that matter. Facts and clause are therefore reported
but are not CI thresholds; the faithfulness judge was not calibrated separately.

### Faithfulness

0.73 on 111 claims of the 24-flag run. Most "partial" grades are claims that add a
conclusion to a cited rule. 3 claims are not supported at all: a risk level the prompt
prescribes but no source states (f09), a statement about what the committee did not
consider (f06), and a law article read the wrong way round (f11, error 3).

## CI

[evals.yml](.github/workflows/evals.yml) runs on every push and pull request: lint,
tests and the production generation run rescored against the expected answers, under a
minute. [retrieval.yml](.github/workflows/retrieval.yml) runs the role search on the
eval set when the search code, the chunks, the flag set or the thresholds change, in
about 6 minutes. Either fails when a metric is under its threshold in
[evals/thresholds.toml](evals/thresholds.toml), set a little under the current
numbers: retrieval overall ≥ 0.90 and no trap passage; valid 1.00, verdict ≥ 0.85, risk
≥ 0.75, cite ≥ 0.95, faithfulness ≥ 0.65. New generation and judging cost money and run
only by hand.

On the runner's CPU the reranker could not score the eval set within 45 minutes. Its
scores are cached by a hash of the model, the query and the chunk and the cache is
committed: a score never changes for the same pair, so CI recomputes only the pairs a
change touches.

## Error analysis

### 1. The reranker threshold dropped the right law articles

**Expected:** for a sublease or repair clause, the law role returns the Civil Code
article (774, 776). **Got:** at a threshold of 0.05 the law role missed the right
article for some flags: law recall 0.82. **Why:** the reranker scores a Ukrainian statute
article against a contract clause low, even when it is the right one: the right article
scored as low as 0.01, while unrelated minutes scored up to 0.007. The threshold was
set before measuring this. Lowered to 0.01, law recall rose to 0.92 and precedent recall to
1.00; the cost is that the precedent slot of a flag without a precedent comes back
empty less often (31% of them instead of 44%), so more minutes on the topic reach the
context as noise. The library role had a related problem: with k 2 it missed the second approved
wording (a fallback after the base one); k 3 took it from 0.77 to 0.93. A fix tried
for both, a second query with the clause alone fused with RRF, lowered recall to 0.91
and was reverted.

### 2. The model names what the sources do not settle and decides anyway

**Expected:** f23 (generator costs left with the landlord) and f24 (the landlord
restores war damage at its cost) are `not_covered`: the policy lists operating costs
without generators and splits repairs into current and capital only, so the lawyer
decides. **Got:** f23 `beyond_concessions`, reading generators into "maintenance of
engineering systems"; f24 `unacceptable`, reading the restoration of finishes, windows
and doors as the current repair of policy 6.4. Both with a changed clause. **Why:** in
both answers the gaps say exactly what is open ("whether the generators are a common
system of the building… changes the verdict and the clause"; "the sources do not say
whether finishes, windows and doors are structural elements"), but the prompt asks for
`not_covered` only when "the sources do not settle the main point", and the model does
not apply that to its own gaps. This is the failure that matters most for a lawyer: a
confident verdict on a point the company has no rule for.

### 3. A law article inverted

**Expected (f11):** Civil Code art. 774: a sublease is possible only with the lessor's
consent, unless the contract or the law provides otherwise. **Got:** "Art. 774 allows a
sublease without the lessor's consent if the contract provides so, so the law is not
broken." **Why:** the article has an exception clause, and the model read the
exception as the rule. The verdict is still right, because it rests on the policy,
and cite is 1.00, because the right document is cited. Only the faithfulness judge,
which reads the claim against the cited text, caught it. Citation checks alone do not
show that the cited source says what the claim says.

### 4. A prompt rule written for two flags spread to others

**Expected:** a sublease with consent that "cannot be unreasonably withheld" (f18) is
medium risk: consent is still needed. **Got:** medium in v2, high in v3. **Why:** v3
added "sublease or transfer without consent to any third party is high risk", written
from the lawyer's corrections of f09 and f21. It fixed f09 (medium in v2, high in v3)
and moved f18 the other way: the model applied the rule to a sublease clause that does
require consent, because the consent cannot be refused. The rule was checked on the
flags it was written for, not on the others of its type. (f11, the business buyer, was
high in every version against the expected medium.) Since then fixes are recorded as general rules
for a class of errors in [docs/improvements.md](docs/improvements.md) before any prompt
change.

### 5. The test, not the model, was wrong

**Expected (draft):** f04, rent fixed at 85,330 yuan for the whole term, is
`unacceptable`: no indexation. **Got:** `not_covered` from v1 and v2. **Why:** the
model was right. The policy indexes hryvnia rent (section 2) and sets euro rent for
some premises (section 3); yuan rent is in neither, so the currency is a point the
policy does not settle. The flag was meant to test the missing indexation, and the
currency added a second question. The lawyer changed it to hryvnias; v3 answers
`unacceptable`. Expected answers written before the model runs still need a second
look when the model disagrees for a reason.

## Budget

About $1.3 of the $5 budget so far: three full Haiku runs at about $0.065 each, the two
new flags $0.006, the judges $0.57 for the 24-flag run (recorded runs $0.77 in all), and
short smoke runs that were not kept. Retrieval, chunking and CI run locally and cost nothing. A redline costs
about $0.003 with Haiku ($2.82 per 1,000 red flags) and takes 23 s (p50).

## Next steps

From [docs/improvements.md](docs/improvements.md), none implemented yet:

- **Generation:** a gap that changes the verdict means `not_covered` (error 2), checked
  in code through a field of the schema; risk from a table of verdict and type in code,
  with the model only explaining a deviation (error 4); for an unacceptable clause the
  base wording without unrequested concessions; a comparison with Sonnet.
- **Judge:** a fact is present only if stated; a clause is good if it can go into the
  lease as it is; then calibrate on new grades, not on the 12 the prompt was fixed on.
  A deterministic check that the clause numbers a claim cites are in its source.
- **Eval set:** a held-out set for the reranker threshold and k; an "either" value for
  gaps that may or may not be named; expected gaps as key facts, so their content is
  judged and not only their presence; more flags with verdicts other than
  `unacceptable`.
- **Input:** stage 1 should return the clause to the end of its sentence or list (f05
  was cut at "in the following cases:").

## Limitations

### Document structure comes from hand-written rules

Headings, and with them the section path that every chunk is cited by, are found by
rules written for the sources of this corpus: the markup of zakon.rada.gov.ua, DOCX
heading styles, font sizes in typeset PDFs, and in scanned contracts numbered titles in
capitals, with filters for party names, stamps and table rows. The pipeline calls no
model: it is deterministic, free and covered by tests, and anyone can rebuild the
corpus without an API key.

The rules were tuned by reading their output on these 35 documents, so they fit these
documents. A new kind of source, such as another legislation site, a contract laid out
differently or a worse scan, can produce headings that are noise, and the rules have to
be extended for it. On the current corpus the residue is visible already: 27 headings
of scanned contracts keep OCR errors beyond Latin look-alikes ("IIPABA СТОРІН"), a
section number "3." is sometimes read as the letter "З", and documents without headings
(the CMU 630 methodology) are cited by the clause numbers in their text only.

The alternative is to find the structure with a model at run time: an LLM, or a
multimodal model reading each page of a scan, or a document layout tool built on ML
models (Docling, Unstructured, LlamaParse). It copes better with new formats, but costs
API fees or compute and is less predictable: the same document can be split
differently from run to run, which makes chunks and citations unstable between
rebuilds. For 35 documents and a $5 budget the rules are the better trade-off; a
corpus that grows with new sources would need the model-based approach, or at least a
model as a fallback for documents the rules structure poorly.

### Exact search, no approximate index

Neither index is built for scale; both are exact.

- **Vectors.** Qdrant runs in local mode (`QdrantClient(path=...)`), the Python
  implementation inside `qdrant-client` rather than the Qdrant server. It keeps the
  points in SQLite and, on a search, computes the cosine of the query against every
  vector that passes the metadata filter: one matrix product over 1,209 × 768 numbers
  (about 3.7 MB), well under a millisecond. No HNSW graph is built; the HNSW settings
  the collection reports are a stub kept for API compatibility.
- **BM25.** bm25s precomputes the BM25 weight of every (lemma, chunk) pair into a
  sparse matrix, so a query sums the rows of its lemmas. The index lives in memory and
  is rebuilt on every start, which takes seconds, mostly for lemmatization. Filters
  are applied to the scores afterwards.

At this size exact search is the right choice: it is fast, and it cannot miss a
nearest neighbour, which an approximate index such as HNSW trades for speed. Even the
Qdrant server scans small segments in full instead of using HNSW.

Exact vector search stops being enough at tens to hundreds of thousands of chunks,
e.g. if every signed lease of the landlord went into the corpus. The move is to the
Qdrant server (Docker) with an HNSW index and payload indexes on the filter fields
(`type`, `status`, `regime`), so that the filters are applied while the graph is
walked; `Retriever` changes only in how it connects and creates the collection. The
BM25 index would be saved to disk instead of rebuilt, and holds up without changes to
about a million chunks.
