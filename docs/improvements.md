# Improvement ideas

A log of thinking about improvements at each level. These are ideas, not implemented changes: each has its evidence (what we saw) and a status. An implemented idea is marked with a link to the commit or the run.

Principle: improvements must be general rules, not fitting to a particular flag of the eval set. If an idea came from one case, first state which class of errors it addresses and check whether that class occurs more widely.

Statuses: **idea** · **deferred** · **rejected** · **done**.

## Input (stage 1)

- **Truncated quotes.** *idea.* The f05 quote breaks off at "у таких випадках:", and the model honestly says the list is unknown. Stage 1 should return the clause to the end of the sentence or the list; otherwise stage 2 judges incomplete text.

## Retrieval

- **Two fused queries per role (clause + description; clause only).** *rejected*, run `2026-11-11_two-queries`: recall 0.91 against 0.95.
- **Empty precedents.** *idea.* The precedent role is empty for 0.31 of flags: for some types there are simply no minutes. Check whether this is a gap in the corpus rather than in the search.
- **Reranker threshold tuned on the eval set.** *idea.* MIN_SCORE 0.01 was chosen on the same 22 flags, so recall 0.95 is optimistic. A held-out set is needed.

## Generation

- **The quote is only a fragment of the lease.** *idea.* The model draws its conclusion from one clause, although the answer may depend on other terms of the lease (for example, whether reimbursement is provided for elsewhere). General rule: if the conclusion depends on terms outside the quote, name that in gaps and do not rate the clause worse than it is. Seen in: f16.
- **A gap that changes the verdict means not_covered.** *idea.* The model names in gaps a question on which, by its own words, the verdict depends, but still gives a verdict and proposes a redline (f23, f24 in `haiku-v3-24`: no not_covered out of two). General rule: if a named gap changes the verdict, the verdict is not_covered and there is no redline. This could also be checked in code: not_covered is required when the model marks a gap as changing the verdict (a separate field in the schema).
  *Tried in prompt v4* (`Gap.changes_verdict`, checked in code), run `2026-11-14_haiku-v4`: f23 became not_covered, f24 did not, and three flags the sources settle (f02, f10, f16) got a false not_covered; verdict 0.83 against 0.88. The model marks as verdict-changing doubts about the clause or the deal (f02: what the clause means, the type of premises; f16: other terms of the lease) and questions of reading the sources (f10: whether companies 50 % owned by the tenant are "one group"; f16: whether ст. 797 ЦК is mandatory), not only points the sources say nothing on. Not in production.
  *Refined once in prompt v5*, run `2026-11-14_haiku-v5`: only a matter on which the sources contain no rule changes the verdict; the clause is assessed as written. The model marked nothing; no not_covered at all, verdict 0.83. *Rejected* as a prompt rule: whether applying a general rule ("are generators engineering systems") leaves the point open is the lawyer's judgment, and the rule either lets the model settle all such points or none.
- **Route gaps to the lawyer instead of not_covered.** *idea.* Show any answer with a gap as "needs a decision" next to its verdict, rather than asking the model to choose between a verdict and not_covered; score the routing (did every expected-gap flag get one) on flags the rule was not tuned on.
- **Inflated risk.** *idea.* The rule on sublease without consent is applied more widely than intended (f11, f18), and f20 gets critical. Consider setting the risk by a rule in code from the verdict and the type, with the model only justifying a deviation.
- **Minimal edit against rewriting.** *idea.* For a concession the model often rewrites the clause from a library formula instead of a minimal edit (f10, f16) and loses tenant terms nobody disputed.
- **Unrequested concessions.** *idea.* In a redline for unacceptable the model adds library concessions the tenant did not ask for (f18, Ф-5.3). Rule: for unacceptable, the base position without concessions; concessions only in findings, as an option for negotiation.
- **Comparison with Sonnet.** *deferred.* The config `configs/rag-sonnet-v3.toml` is ready.

## Evaluation (eval set and scoring)

- **Optional gaps.** *idea.* `gaps` is now true/false, but in f20 a gap is acceptable, not required. Add an "either" value so that neither answer is penalised.
- **What the gaps say, not only whether there are any.** *idea.* The deterministic gaps metric only checks whether gaps exist. An expected gap (as in f16) should go into key_facts, so the judge checks its content.
- **Showing gaps in the report.** *idea.* In `report.md` the block is called "Джерела не вирішують" and is easy to miss; `scores.md` has no per-flag comparison of expected and found gaps.
- **CPU build of torch in CI.** *idea.* On Linux `uv sync` installs torch with the CUDA libraries (several GB), although CI computes on CPU. A pytorch-cpu index for Linux in `pyproject.toml` would shorten the install.
- **Overall score.** *done:* there is no aggregate number; CI checks thresholds of individual metrics (`evals/thresholds.toml`), not a weighted sum.

## Judge

- **Calibration of answer_v1:** facts — agreement 0.74, kappa 0.14; redline — agreement 0.58, kappa 0.25 (`results/rag/judge_calibration.md`).
- **Lenient on facts.** *idea.* The judge counts a fact when the answer only touches on it (4 of the lawyer's 5 "missing" are "present" for it). Criterion: present only if the fact is stated directly.
- **Strict on the redline.** *idea.* All 5 disagreements are the lawyer's "good" against the judge's "minor_edits". The judge penalises additions beyond a minimal edit; the lawyer judges whether the redline can be used. Criterion: "can it go into the lease as is".
- **Calibrating on the same answers.** *idea.* If the judge prompt is changed, measure agreement on new grades by the lawyer, not on the 12 it was adjusted to.
- **Deterministic check of clause numbers.** *idea.* The numbers п./ст./Ф- in a claim must appear in the text of the cited chunk — a cheap faithfulness check without an LLM.
