"""From the lawyer's feedback to eval tasks: the candidates, the drafts, the task set.

    make candidates BY=lawyer                    the candidates the person may see
    make candidates BY=lawyer ID=F-0007 ACCEPT=1 a draft task from one
    make candidates BY=lawyer ID=F-0007 DISMISS=1
    make promote ID=F-0007                       the draft into the task set

A candidate is a minus or a correction the lawyer gave an answer in `make chat`
(`feedback.py`): a case where the agent was wrong in real use. Accepted, it becomes a
draft in evals/agent_task_candidates.toml, which no run reads: a question and the
lawyer's correction, with no checks yet; the answer the lawyer corrected stays in the
feedback file, out of the public repository. The checks are written with the lawyer,
as for every task, and the draft gets `reviewed = "<date>"` once the lawyer agrees,
having made sure it holds nothing confidential.

`promote` moves a draft into evals/agent_tasks.toml only if:
1. it has checks, not only a question;
2. the lawyer reviewed it (`reviewed`);
3. its answer checks fail the answer the lawyer corrected, kept in the feedback: if
   that answer passed, the checks would catch nothing;
4. it is written right (`evaluate.problems`), as the test of the task set requires.
Otherwise it says what is missing and changes nothing.

A person sees their own feedback; the head of legal sees that of the whole entity.
"""

import argparse
import json
import tomllib
from pathlib import Path

from lease_redflag_detector.agent.evaluate import CHECKS, Outcome, check, problems
from lease_redflag_detector.agent.feedback import (
    ACCEPTED,
    DISMISSED,
    NEW,
    PROMOTED,
    Feedback,
    FeedbackStore,
)
from lease_redflag_detector.agent.users import UnknownUser, User, get_user

ROOT = Path(__file__).resolve().parents[3]
TASKS = ROOT / "evals" / "agent_tasks.toml"
DRAFTS = ROOT / "evals" / "agent_task_candidates.toml"
HEADER = """\
# Draft eval tasks from the lawyer's feedback (agent/candidates.py). No run reads this
# file: a draft needs checks and the lawyer's review (reviewed = "<date>") before
# `make promote ID=...` moves it into evals/agent_tasks.toml. The repository is public:
# the review also makes sure the question and the correction hold nothing
# confidential (a closed lease's terms, personal data).
"""
# The lines of a draft that are instructions for whoever completes it.
SERVICE = "# To complete:"


def may_see(user: User, feedback: Feedback) -> bool:
    if user.role == "head_of_legal":
        return feedback.entity == user.entity
    return feedback.author == user.id


def quoted(text: str) -> str:
    """A TOML basic string: JSON's escapes are TOML's."""
    return json.dumps(text, ensure_ascii=False)


def draft(feedback: Feedback) -> str:
    """The question and the correction; the answer stays in the feedback file, out
    of the repository."""
    return f"""
[[task]]
id = {quoted(feedback.id)}
group = "feedback"
question = {quoted(feedback.question)}
why = {quoted(f"Correction of the lawyer ({feedback.id}, {feedback.at[:10]}): "
              f"{feedback.correction or 'rated minus, no text'}")}
user = {quoted(feedback.author)}
{SERVICE} checks (answer_has, answer_lacks, tools_called, …); after the lawyer's
{SERVICE} review, reviewed = "YYYY-MM-DD"; then make promote ID={feedback.id}
"""  # fmt: skip


def blocks(text: str) -> list[str]:
    """The [[task]] blocks of a file, each with the lines up to the next one."""
    parts = text.split("\n[[task]]")
    return ["[[task]]" + part for part in parts[1:]]


def promote(
    feedback_id: str,
    store: FeedbackStore,
    drafts: Path = DRAFTS,
    tasks: Path = TASKS,
) -> list[str]:
    """Move the draft into the task set; what stops it, if anything."""
    text = drafts.read_text(encoding="utf-8") if drafts.exists() else ""
    found = [
        b for b in blocks(text) if tomllib.loads(b)["task"][0]["id"] == feedback_id
    ]
    if not found:
        return [f"no draft {feedback_id} in {drafts.name}"]
    block = found[0]
    task = tomllib.loads(block)["task"][0]
    stops = []
    if not CHECKS & task.keys():
        stops.append("the draft has no checks")
    if "reviewed" not in task:
        stops.append('the lawyer has not reviewed it (reviewed = "<date>")')
    feedback = store.get(feedback_id)
    answer_checks = [c for c in check(task, Outcome(feedback.answer, "final", [], [], []))
                     if c.kind == "answer"]  # fmt: skip
    if not answer_checks:
        stops.append("no check of the answer, so the corrected one cannot fail it")
    elif all(c.passed for c in answer_checks):
        stops.append(
            "the answer the lawyer corrected passes the checks: make them stricter"
        )
    if task["id"] in {t["id"] for t in tomllib.loads(tasks.read_text())["task"]}:
        stops.append(f"{task['id']} is already in the task set")
    stops += problems(task)
    if stops:
        return stops
    kept = "\n".join(
        line for line in block.strip().splitlines() if not line.startswith(SERVICE)
    )
    with tasks.open("a", encoding="utf-8") as f:
        f.write(f"\n# From the lawyer's feedback {feedback_id} (step 3.6)\n\n{kept}\n")
    drafts.write_text(text.replace("\n" + block, ""), encoding="utf-8")
    store.update(feedback_id, status=PROMOTED)
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["candidates", "promote"])
    parser.add_argument("--by", help="who looks (configs/users.toml)")
    parser.add_argument("--id")
    parser.add_argument("--accept", action="store_true")
    parser.add_argument("--dismiss", action="store_true")
    args = parser.parse_args()
    store = FeedbackStore()

    if args.command == "promote":
        if not args.id:
            raise SystemExit("Promote which draft: ID=F-0007")
        if stops := promote(args.id, store):
            raise SystemExit("Not moved: " + "; ".join(stops) + ".")
        print(f"{args.id} is in {TASKS.relative_to(ROOT)}.")
        return

    if not args.by:
        raise SystemExit("Say who you are: BY=lawyer, BY=head, … (configs/users.toml)")
    try:
        user = get_user(args.by)
    except UnknownUser as e:
        raise SystemExit(str(e)) from None
    if args.accept or args.dismiss:
        feedback = store.get(args.id) if args.id else None
        if feedback is None or not may_see(user, feedback):
            raise SystemExit(f"No feedback {args.id}")
        if feedback.status != NEW:
            raise SystemExit(f"{args.id} is {feedback.status}, not {NEW}")
        if args.accept:
            text = DRAFTS.read_text(encoding="utf-8") if DRAFTS.exists() else HEADER
            DRAFTS.write_text(text + draft(feedback), encoding="utf-8")
            store.update(feedback.id, status=ACCEPTED)
            print(f"A draft {feedback.id} is in {DRAFTS.relative_to(ROOT)}.")
        else:
            store.update(feedback.id, status=DISMISSED)
    rows = [f for f in store.all() if f.rating < 0 and may_see(user, f)]
    if not rows:
        print("Кандидатів немає.")
    for f in rows:
        print(f"{f.id}  {f.at[:10]}  {f.status:<9} «{f.question[:90]}»")
        print(
            f"         {('виправлення: «' + f.correction + '»') if f.correction else 'мінус'}"
        )


if __name__ == "__main__":
    main()
