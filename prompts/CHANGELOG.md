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

## rag

Redline proposals for a red flag from the chunks of the role search
(`src/lease_redflag_detector/rag/redline.py`). The answer schema is `Redline` in the
same module. `rag/repair_v1` is the repair message, as in stage 1.

### v5 — which gaps change the verdict

| Change | Error in v4 |
|---|---|
| Only a matter on which the sources contain no rule changes the verdict. Doubts about the clause or the deal (what it means, other terms, facts) and how to apply a rule the sources do contain are gaps without the mark; the clause is assessed as written | three flags the sources settle got not_covered: the model marked the meaning of the clause, the type of premises, other terms of the lease and the reading of a policy term as verdict-changing |

The one refinement of the v4 rule; further changes need a set the rule was not tuned on.
Neither v4 nor v5 was kept: the code went back to plain-string gaps after commit
5c6bae2, which has the schema both need.

### v4 — a gap that changes the verdict means not_covered

| Change | Error in v3 |
|---|---|
| Each gap is marked whether it changes the verdict (`Gap.changes_verdict` in the schema); if one does, the verdict is not_covered with no changed clause. The code checks both directions and sends a mismatch back for repair | in the 24-flag run the model never said not_covered: on the two flags the sources do not settle it named the deciding point as a gap and gave a verdict anyway |

A general rule, not written for those two flags: the prompt names no topic of theirs.
Older answers keep gaps as plain strings; the readers accept both.

### v3 — fixes from the lawyer's review of the expected answers

| Change | Error in v2 |
|---|---|
| The notes under a library wording are the company's position: a limit for a deviation (the lowest cap the general director may approve for an anchor tenant) binds everyone | f07: a 6 % cap was said to be within the general director's power, although the note to Ф-2.3 sets 7 % as the lowest |
| For a concession, keep the tenant's clause and change only what differs | f10: a related-party sublease with notice "in advance" was rewritten from scratch instead of fixing the notice period |
| Sublease or transfer without consent to any third party is high risk; to persons linked to the tenant it stays at the default | the lawyer rated unrestricted sublease (f09, f21) high, not the default medium |

The approval text for beyond_concessions in `redline.py` now says the general director
approves only within the limits of the policy and the clause library.

### v2 — risk levels and gaps from the first run of v1

| Change | Error in v1 (Haiku, 22 red flags) |
|---|---|
| Keep the default risk unless the clause clearly fits another level of policy 1.7; critical only as in its examples; breaking several criteria of 1.6 or the precedent criterion does not raise the level | risk differed from the expected one in 9 of 22 answers, 8 times higher: "all four criteria are touched, so critical", sublease raised to high for the precedent criterion |
| Gaps only for points that change the verdict or the changed clause; facts of the deal missing from the clause are not gaps | every answer had 2–5 gaps, mostly minor details and the unknown term or type of premises |

The expected answers these errors are counted against were a draft not yet reviewed
by the lawyer.

### v1 — baseline

Use only the sources and cite them; the roles of the sources and their order when
they disagree (law, the policy in force, committee decisions, market practice); five
verdicts by the three levels of the policy plus "beyond concessions" and "not
covered"; the risk level from the default of the red flag type and policy 1.6–1.7;
the changed clause from the approved wording with deal values kept as placeholders.
Before the first recorded run two fixes were made on three red flags: at most five
short findings (answers were cut off at 4000 tokens), conflicts only between sources,
no invented dates; and gaps for what the sources do not settle, since a claim without
a source failed validation.
