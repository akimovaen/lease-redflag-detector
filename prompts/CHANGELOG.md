# Prompt changelog

Prompts live in `prompts/<task>/<version>.md` and are sent as the system prompt.
Field-level instructions are in the field descriptions of the output schema
(`src/lease_redflag_detector/extraction/schema.py`), which is sent with every request.
Every result in `results/` records the prompt version that produced it.

## extraction

### v3 — fixes the indexation regression of v2

v2 is v1 plus the fixes below, except that one rule backfired: "a rent that stays
unchanged for the whole term is a red flag" made both Claude models flag the clause
that merely sets the rent amount (3 of 7 golden texts), so red flag F1 fell even
though field accuracy rose. v3 changes only that rule: an `indexation_limited` flag
needs an explicit clause that freezes, caps or conditions rent increases during the
term; the rent amount itself and the rent for a renewal are not red flags.

### v2 — fixes from the error analysis of v1

Every change answers an error pattern seen in the v1 results on the golden set
(Sonnet, Haiku and qwen3:8b). Rules are written for leases in general, not for
the golden texts, but they were found on the same texts they are scored on, so
part of any gain may be overfitting.

| Change | Error in v1 |
|---|---|
| A red flag is defined in one sentence, then the lease is checked type by type | Sonnet found no flags at all in a lease with five, and missed one type in three others (recall 0.67) |
| Costs included in the rent or paid by the landlord are named as `service_charges_limited` | missed in 2 of 7 golden texts by Sonnet and qwen |
| A rent fixed for the term or changed only by agreement is named as `indexation_limited` | missed in 2 of 7 golden texts by Sonnet, in 4 by qwen |
| A list of clauses that are not red flags: tenant's obligations, a ban on subletting, renewal and purchase rights, the landlord's remedies | Haiku flagged the tenant paying service charges and repairs; qwen flagged a ban on subletting and the tenant's renewal right |
| Checked and unchecked boxes in forms | qwen read the options of a checkbox form as clauses that apply |
| `area` takes the total of several stated areas | both Claude models took the usable area instead of the building area |
| Never list the same clause twice; keep quotes to the sentences that raise the flag | qwen repeated one clause up to 8 times; 27% of its quotes were not verbatim |

### v1 — baseline

Role, a note that the text may be OCR'd, translated or mixed-language, and the
labeling rules of the golden set in short: null for absent values, ISO dates, computed
end date, rent per period without VAT, `indexation: none` when the rent never changes,
and verbatim quotes for red flags.

## repair

Sent as a follow-up message when an answer fails validation (schema, verbatim quotes,
end date before start date), with `{errors}` replaced by the problems found.

### v1

Lists the problems and asks for the complete corrected answer: quotes copied character
for character, a red flag left out if its exact wording cannot be found, no repeats.
