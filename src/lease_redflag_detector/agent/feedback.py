"""The lawyer's feedback on the agent's answers, and the candidates it gives the evals.

After every answer of `make chat` the lawyer may rate it (+ or -) or write a
correction, a minus with a text (`take_feedback`). A correction may also become a
note of the long-term memory on the lease it is about, after the lawyer says so: then
the next conversations use it. When the question and the answer name no lease or
several, no note is made: a note with no lease reaches the whole entity. A rating or a correction is typed by the lawyer, not proposed by the model, so
it needs no other confirmation.

A minus or a correction is a candidate for the eval tasks: a case where the agent was
wrong in real use. `make candidates` lists them and turns one into a draft task in
evals/agent_task_candidates.toml; `make promote` moves a draft into the task set only
once the lawyer has reviewed it and its checks fail the answer the lawyer corrected
(`candidates.py`). The feedback is a local SQLite file, not committed.
"""

import datetime
import re
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from lease_redflag_detector.agent.memory import NoteStore, policy_version
from lease_redflag_detector.agent.users import User

ROOT = Path(__file__).resolve().parents[3]
FEEDBACK = ROOT / "data" / "agent" / "feedback.db"
LEASE = re.compile(r"\blease_\d+\b")

RATED = "оцінка"  # a plus: no candidate
NEW = "новий"  # a candidate not looked at yet
ACCEPTED = "чернетка"  # turned into a draft task
PROMOTED = "у наборі"  # the draft became a task
DISMISSED = "відхилено"

SCHEMA = """
CREATE TABLE IF NOT EXISTS feedback (
    id TEXT PRIMARY KEY,
    at TEXT NOT NULL,
    author TEXT NOT NULL,
    entity TEXT NOT NULL,
    conversation TEXT,
    question_number INTEGER NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    rating INTEGER NOT NULL,
    correction TEXT,
    note_id TEXT,
    status TEXT NOT NULL
);
"""


@dataclass
class Feedback:
    id: str
    at: str
    author: str
    entity: str
    conversation: str | None
    question_number: int
    question: str
    answer: str
    rating: int  # +1 or -1
    correction: str | None
    note_id: str | None
    status: str


class FeedbackStore:
    def __init__(self, path: Path = FEEDBACK):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    def add(
        self,
        user: User,
        question_number: int,
        question: str,
        answer: str,
        rating: int,
        correction: str | None = None,
        conversation: str | None = None,
    ) -> Feedback:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
            feedback_id = f"F-{count + 1:04d}"
            db.execute(
                "INSERT INTO feedback VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    feedback_id,
                    datetime.datetime.now().isoformat(timespec="seconds"),
                    user.id,
                    user.entity,
                    conversation,
                    question_number,
                    question,
                    answer,
                    rating,
                    correction,
                    None,
                    NEW if rating < 0 else RATED,
                ),
            )
            db.execute("COMMIT")
        return self.get(feedback_id)

    def get(self, feedback_id: str) -> Feedback | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM feedback WHERE id = ?", (feedback_id,)
            ).fetchone()
        return Feedback(**dict(row)) if row else None

    def all(self) -> list[Feedback]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM feedback ORDER BY id").fetchall()
        return [Feedback(**dict(row)) for row in rows]

    def update(self, feedback_id: str, **fields) -> None:
        names = ", ".join(f"{name} = ?" for name in fields)
        with self.connect() as db:
            db.execute(
                f"UPDATE feedback SET {names} WHERE id = ?",
                (*fields.values(), feedback_id),
            )


def lease_of(*texts: str) -> str | None:
    """The one lease the texts are about, if exactly one is named."""
    found = {lease for text in texts for lease in LEASE.findall(text)}
    return found.pop() if len(found) == 1 else None


def take_feedback(
    store: FeedbackStore,
    notes: NoteStore,
    user: User,
    number: int,
    question: str,
    answer: str,
    conversation: str | None = None,
    read: Callable[[str], str] = input,
    say: Callable[[str], None] = print,
) -> Feedback | None:
    """Ask the lawyer for a rating or a correction of the answer; keep a correction
    as a note on its lease too if the lawyer says so, and only when the answer is
    about one lease."""
    given = read("Оцінка: + / - / або напишіть виправлення (Enter — пропустити): ")
    given = given.strip()
    if not given:
        return None
    if given in ("+", "-"):
        rating = 1 if given == "+" else -1
        return store.add(
            user, number, question, answer, rating, conversation=conversation
        )
    feedback = store.add(user, number, question, answer, -1, given, conversation)
    lease = lease_of(question, answer)
    if lease is None:
        # A note with no lease reaches the whole entity: a correction about a closed
        # lease could reach those who may not read it, or one about one of two leases
        # would become a general rule. The lawyer names the lease with "remember".
        say(
            "Не зрозуміло, до якого договору виправлення, тож нотатку не створено. "
            "Щоб агент запам'ятав, напишіть «запам'ятай…» з номером договору."
        )
        return feedback
    keep = read("Зберегти виправлення як нотатку для наступних розмов? [так/ні]: ")
    if keep.strip().casefold() in ("так", "т", "yes", "y"):
        note, _ = notes.add(
            f"Виправлення юриста до відповіді на «{question[:150]}»: {given}",
            user.id,
            user.entity,
            policy_version(),
            lease,
            replace=False,
        )
        store.update(feedback.id, note_id=note.id)
        feedback = store.get(feedback.id)
    return feedback
