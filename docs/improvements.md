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
  *Tried in prompt v4* (`Gap.changes_verdict`, checked in code), run `2026-11-14_haiku-v4`: f23 became not_covered, f24 did not, and three flags the sources settle (f02, f10, f16) got a false not_covered. Rejected for those three and the missed f24; its verdict 0.83 against 0.88 is within the spread of two runs of v3 (0.88 and 0.79) and decides nothing. The model marks as verdict-changing doubts about the clause or the deal (f02: what the clause means, the type of premises; f16: other terms of the lease) and questions of reading the sources (f10: whether companies 50 % owned by the tenant are "one group"; f16: whether ст. 797 ЦК is mandatory), not only points the sources say nothing on. Not in production.
  *Refined once in prompt v5*, run `2026-11-14_haiku-v5`: only a matter on which the sources contain no rule changes the verdict; the clause is assessed as written. The model marked nothing; no not_covered at all, as in v3. *Rejected* as a prompt rule: whether applying a general rule ("are generators engineering systems") leaves the point open is the lawyer's judgment, and the rule either lets the model settle all such points or none.
- **Route gaps to the lawyer instead of not_covered.** *done:* `Result.needs_decision` and the routing scores in `scripts/eval_redline.py`, with CI thresholds. On both runs of v3 (the saved 24-flag run and the CI run on PR #19) both flags expected not_covered are referred; 0.82 of the 11 flags with expected gaps; extra referrals 0 to 4 of the other 13 over five runs. Still to do: check on flags it was not measured on.
- **Extra referrals.** *done for the eval set:* the first count had f05, f06, f12 and f14 as extra: two points of applying a general rule (f12, f14), a quote cut off by stage 1 (f05) and no approved wording in the sources (f06). The lawyer wants to see them, and their expected answers now have gaps (14.11.2026). f02, f13 and f19, referred only in the CI run, she keeps as not needing her. *idea:* if extra referrals grow on new flags, cut them by kind of gap (facts of the deal, as in f02), not by flag.
- **Record the lawyer's decisions on gaps.** *idea, stage 3.* Next to each referred gap, a field for the lawyer's decision ("generators are common systems: verdict stands" or "no, current repair by 6.1"). Kept, they become precedents shown like committee minutes for a similar clause later, and each is a new flag with an answer given by the lawyer: the held-out data the routing has not been measured on.
- **Several runs per config.** *done for v3:* five runs on the same code (`haiku-v3-24`, `ci-pr19`, `haiku-v3-run2`, `haiku-v3-run3`, `ci-pr20`): verdict 0.79–0.88 (mean 0.84), risk 0.83–0.88, referred 0.55–1.00, no_answer 1.00 in all. Errors that repeat: verdict of f16 (5 of 5) and f10 (4 of 5), risk of f10, f11, f18 (5 of 5). The `fresh` threshold on referred went from 0.65 to 0.45 after the fifth run failed it on noise. *idea:* compare any new prompt by several runs too.
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

## Code (from the review of 2026-11-20)

- **CI cache may overwrite the committed reranker scores.** *idea, not verified.* The fresh, generation and retrieval jobs restore `data/processed/rerank` from the Actions cache over the checked-out file. If a commit adds scores to that file, an older cache can replace it and the missing scores are recomputed (over 45 minutes on a runner). Fix if it happens: restore the cache before checkout, or merge the two files.
- **Ollama retries client errors.** *idea.* `ollama_extractor._post` retries every HTTP error, a 400 as well as a 503; only transport errors, 429 and 5xx are worth retrying.
- **Three wrappers of one Claude call.** *deferred.* The stage 1 extractor, the redline generator and the judge each build the request and read the usage in their own way. Not merged: each has its own validation and repair.
- **Edge cases.** *idea.* `chunk_fixed` fails on a document with no text; `score_config` divides by zero for a run with no golden text.

## Agent (stage 3)

- **Tool calls of one step run one after another.** *idea.* The model asks for several redlines at once, and the loop runs them in turn (about 25 s each), so a lease with five or six red flags nears the request time limit and the last redlines are skipped as "time limit". Calls of tools without side effects could run in parallel. Revisit if the evals show it.
- **An explicit request to submit is not carried out.** *idea, for PR 3.* In run 1 of `results/agent/runs/2026-11-23_reviewed` (c14, c15) the lawyer asked to check a lease and send it for approval; the agent drafted the redlines but did not call `submit_for_review`, and asked the lawyer to settle the open points first. The lawyer judged it a failure: points that need the lawyer's decision go into the request, marked as such. General rule to try: an action the lawyer asked for is carried out; open points go into it, they do not hold it back. Compare over several runs.
- **A late redline still reaches the request.** *idea, from the review of 2026-11-23.* A `draft_redline` call that timed out keeps running in its thread (Python cannot stop it). If it then finishes, its redline is added to the drafts of the request and goes into the approval request, while the model was told it failed. Nothing is created without the lawyer, who sees every point in the confirmation, but the agent's answer then misses that point. Fix: drafts accept only the result of a call the loop is still waiting for.
- **Who decided on a request.** *for PR 2.* `make review` records every decision as made by `lawyer`, a committee decision too. With the users of `configs/users.toml` the decision gets its real author.
- **The lawyer's time to confirm counts against the request.** *idea.* `submit_for_review` waits for the lawyer's answer with no time limit, and that wait is part of the request's 240 s. A lawyer who reads a long request for two minutes leaves the agent too little time for the steps after it; the answer then says honestly that the time limit was reached. The wait for a person could be left out of the request clock. The evals answer at once, so they do not show it.
