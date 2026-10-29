# Report — stage 1: structured extraction

Extract the key terms of a commercial lease and the clauses that are risky for the
**landlord** into a fixed schema, and compare a paid API model with a local one.

## Setup

**Data** ([data/README.md](data/README.md)). 20 lease texts from the ALeaseBERT
benchmark: 15 converted to plain text (group A) and 5 rendered as scans and read back
with Tesseract OCR at three noise levels (group B). They range from 800 to 9,600 words
and include OCR errors, broken layout, checkbox forms, unfilled template fields, broken
encoding and fragments in other languages. 7 of them form the golden set, labeled by
the rules in `data/README.md`.

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
- % valid, latency p50/p95: over all 20 texts.
- Cost per 1000 documents: at the mean token usage per text and the
  [list prices](https://platform.claude.com/docs/en/about-claude/pricing) of
  2026-10-28 ($2 / $10 per million input / output tokens for Sonnet 5.5, $0.10 /
  $0.50 for Haiku 5.5). The local model has no API cost.

Reproduce with `make run CONFIG=configs/<name>.toml`; `make metrics` rescores all runs.

## Results: model × prompt × sampling

All rows below use the full pipeline (schema, quote and date validation, one repair).

| Model | Prompt | Sampling | Field acc. | Flag P | Flag R | Flag F1 | % valid | % repaired | p50, s | p95, s | $ / 1000 docs |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-sonnet-5-5 | v1 | effort medium | 0.92 | 0.93 | 0.78 | 0.85 | 100 | 0 | 3.5 | 10.3 | 27.63 |
| claude-sonnet-5-5 | v2 | effort medium | **0.98** | 0.78 | 0.78 | 0.78 | 100 | 0 | 3.8 | 9.6 | 28.47 |
| claude-sonnet-5-5 | v3 | effort medium | **0.98** | 0.88 | 0.83 | 0.86 | 100 | 0 | **3.1** | **6.6** | 27.07 |
| claude-haiku-5-5 | v1 | effort medium | 0.94 | 0.78 | **1.00** | **0.88** | 100 | 0 | 11.4 | 15.0 | 2.47 |
| claude-haiku-5-5 | v2 | effort medium | 0.97 | 0.74 | 0.94 | 0.83 | 100 | 0 | 11.2 | 17.9 | 2.57 |
| claude-haiku-5-5 | v3 | effort medium | 0.95 | 0.83 | 0.83 | 0.83 | 100 | 0 | 10.2 | 15.3 | 2.53 |
| qwen3:8b | v1 | t0, capped | 0.25 | 0.50 | 0.11 | 0.18 | 40 | 65 | 89.6 | 162.6 | 0 |
| qwen3:8b | v3 | t0, capped | 0.37 | 0.50 | 0.33 | 0.40 | 55 | 60 | 59.7 | 154.0 | 0 |

"Capped" is the fix for looping described in error 1 below: at most 8 red flags in the
decoding grammar and `repeat_penalty` 1.1.

### Sampling on the local model

These runs predate the quote check, so their outputs were validated against the schema
only; compare them with each other, not with the table above. Results of commit
`9741669`.

| Config | Field acc. | Flag F1 | % valid | p50, s | p95, s |
|---|---|---|---|---|---|
| qwen3:8b t0 | 0.25 | 0.27 | 25 | 241 | 359 |
| qwen3:8b t07 | 0.25 | 0.18 | 25 | 253 | 367 |
| qwen3:8b t0, capped | 0.83 | 0.50 | 100 | 54 | 127 |
| qwen3:8b t07, capped | 0.83 | 0.51 | 100 | 60 | 138 |

Temperature and top_p made no measurable difference. Constraining the structure of the
output did: valid outputs went from 25% to 100% and latency fell four times.

### How much the numbers can be trusted

- **The golden set has 7 texts.** One red flag type more or less in one text moves
  F1 by about 0.05, and one field by 0.016 in field accuracy.
- **Runs are not repeatable.** The same Sonnet v1 config scored F1 0.77 in its first
  run and 0.85 in the second (error 4). Differences between prompt versions of the
  same model are within that range, except for the v2 regression.
- **The golden set was drafted by Claude** (Opus 5.5) and corrected by hand, so the
  scores of Claude models may be biased upward.
- **v2 and v3 were written after looking at errors on the same golden texts** they are
  scored on, so part of their gain may be overfitting.

## Error analysis

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

**Seen:** with the quote check, only 40% (v1) and 55% (v3) of qwen3:8b outputs are
valid. The repair attempt rarely helps: it fixed 1 of 13 outputs on v1 and 3 of 12 on
v3. Claude never needed a repair: all 120+ of its quotes were verbatim.

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
two of the three types, and F1 over the golden set went from 0.77 to 0.85. With prompts
v1 and v3, Sonnet's precision is high (0.88–0.93) and its recall lower (0.78–0.83);
Haiku is the other way round (recall 0.83–1.00, precision 0.74–0.83).

**Cause:** the red flag types need a judgment of whose risk a clause is. Sonnet tends to
skip borderline clauses, and with no temperature control the judgment varies between
runs.

**Consequence:** single runs on 7 texts cannot rank configs whose F1 differs by less
than about 0.08. A larger golden set, or several runs per config, is needed before
choosing between Sonnet and Haiku on red flags alone.

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
  `service_charges_limited`.
- **Handover defects.** Haiku flags the landlord's duty to remedy defects found at
  handover (`alb_lease_contract_54`) as `landlord_repairs`. The labeling rules were
  settled after v3 (it is not a red flag), so the rule goes into the next prompt.
- **OCR noise passes the quote check.** In `ocr_lease_contract_199` Haiku returned a
  `landlord_repairs` flag whose quote is `qay“a`, an OCR fragment of a garbled clause.
  The quote is verbatim, so validation accepts it. A minimum quote length would catch
  this case.
- **Rent in `alb_lease_contract_54`.** The annual rent is a formula and the lease also
  states a monthly amount. The golden set takes the annual rent, Haiku the monthly one.
- **Address scoring.** The address similarity metric rejects an answer that adds the
  land registry details to the golden address. This is a limit of the metric, not
  necessarily a wrong answer.

## Production choice

**Claude Haiku 5.5 with prompt v3, effort medium, strict validation with one repair.**

- **Quality.** Field accuracy 0.95 and red flag F1 0.83–0.88 across prompt versions,
  within the run-to-run variation of Sonnet (0.98 and 0.78–0.86). Its recall is the
  highest of all configs. For a landlord's review a missed red flag costs more than an
  extra one, because a lawyer checks every flagged clause anyway.
- **Cost.** $2.53 per 1000 documents, 11 times less than Sonnet ($27.07).
- **Latency.** p50 10 s, p95 15 s per lease. Fine for review of uploaded documents;
  Sonnet (p50 3 s) is the choice if extraction has to be interactive.
- **Reliability.** 100% valid outputs, all quotes verbatim.

**Not the local model.** qwen3:8b on a 16 GB laptop gets field accuracy 0.37 and red
flag F1 0.40 at 1–2.5 minutes per lease, and half of its outputs fail the quote check.
It would only be worth it where leases may not leave the premises, and then with a
larger model and quote snapping.

## Budget

About $2.40 of the $5 budget was spent on the Anthropic API, including runs that were
later overwritten. The local runs cost no API fees.

## Next steps

- Extend the dataset to 30 texts with Ukrainian leases (group C) and short addenda
  (group D), and the golden set to 10 texts.
- Prompt v4: the handover defects rule, and `service_charges_limited` limited to costs
  the landlord cannot pass on to the tenant. Validation: a minimum quote length.
- Snap near-verbatim quotes to the exact span of the text, so that local models can
  pass the quote check without loosening it.
- Repeat each config several times to measure variance before comparing prompts.
