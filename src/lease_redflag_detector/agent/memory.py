"""The lawyer's notes: the long-term memory of the agent.

A note is a decision or a comment of the lawyer, kept across conversations: its
author and the author's legal entity, the lease and the topic (a red flag type) it is
about, if any, and the version of the policy in force when it was written. The agent
reads the notes with `recall_notes` and writes or forgets one with `remember` and
`forget` after the lawyer confirms (`toolset.py`); a person sees and forgets them with
`make notes` (`notes.py`).

What is out of date is put aside by the code, not by the model:

- a new note on the same lease and topic, in the same entity, replaces the active one;
- a note written under another version of the policy is not given to the agent (the
  version is the set of policy documents in force, `policy_version`). The version is
  their ids, so renaming a policy document in the corpus would put every note aside
  too, though nothing in the policy changed: `make notes` still shows them;
- a note the lawyer asks to forget is forgotten.

Nothing is deleted: a note changes its status (active, replaced, forgotten), so its
history stays. The notes are a local SQLite file, not committed; the evals use a fresh
one per task.
"""

import csv
import datetime
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MEMORY = ROOT / "data" / "agent" / "memory.db"
MANIFEST = ROOT / "data" / "corpus" / "manifest.csv"

ACTIVE = "чинна"
REPLACED = "замінена"
FORGOTTEN = "забута"

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    author TEXT NOT NULL,
    entity TEXT NOT NULL,
    lease_id TEXT,
    topic TEXT,
    policy_version TEXT NOT NULL,
    text TEXT NOT NULL,
    status TEXT NOT NULL,
    replaced_by TEXT,
    closed_by TEXT,
    closed_at TEXT
);
"""


@dataclass
class Note:
    id: str
    created_at: str
    author: str
    entity: str
    lease_id: str | None
    topic: str | None
    policy_version: str
    text: str
    status: str
    replaced_by: str | None
    closed_by: str | None
    closed_at: str | None

    def as_dict(self) -> dict:
        return asdict(self)


def now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def policy_version(manifest: Path = MANIFEST) -> str:
    """The policy documents in force, e.g. "policy_2026+policy_2026_amendment_1": a
    note written under other ones may no longer hold."""
    with manifest.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    ids = sorted(
        row["id"]
        for row in rows
        if row["type"] == "policy" and row["status"] == "current"
    )
    return "+".join(ids)


class NoteStore:
    def __init__(self, path: Path = MEMORY):
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

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
            except BaseException:
                db.execute("ROLLBACK")
                raise
            db.execute("COMMIT")

    @staticmethod
    def note(row: sqlite3.Row) -> Note:
        return Note(**dict(row))

    def get(self, note_id: str) -> Note | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        return self.note(row) if row else None

    def all(self) -> list[Note]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM notes ORDER BY id").fetchall()
        return [self.note(row) for row in rows]

    def active(self, version: str) -> list[Note]:
        """The active notes written under this version of the policy."""
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM notes WHERE status = ? AND policy_version = ? "
                "ORDER BY id",
                (ACTIVE, version),
            ).fetchall()
        return [self.note(row) for row in rows]

    def same(
        self,
        entity: str,
        lease_id: str | None,
        topic: str | None,
        text: str,
        version: str,
    ) -> Note | None:
        """The active note with exactly this content, if any."""
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM notes WHERE status = ? AND entity = ? AND lease_id IS ? "
                "AND topic IS ? AND text = ? AND policy_version = ?",
                (ACTIVE, entity, lease_id, topic, text, version),
            ).fetchone()
        return self.note(row) if row else None

    def replaced_by_new(
        self, entity: str, lease_id: str | None, topic: str | None
    ) -> Note | None:
        """The active note a new one on this lease and topic would replace: only a
        note about something (a lease or a topic) is replaced, never a general one."""
        if lease_id is None and topic is None:
            return None
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM notes WHERE status = ? AND entity = ? "
                "AND lease_id IS ? AND topic IS ?",
                (ACTIVE, entity, lease_id, topic),
            ).fetchone()
        return self.note(row) if row else None

    def add(
        self,
        text: str,
        author: str,
        entity: str,
        version: str,
        lease_id: str | None = None,
        topic: str | None = None,
        replace: bool = True,
    ) -> tuple[Note, bool]:
        """A new active note (True), replacing the active one on the same lease and
        topic; the same note already active is returned as it is (False). With
        `replace` False nothing is replaced: a record that adds to the others, such as
        a committee's decision or a correction."""
        with self.transaction() as db:
            same = db.execute(
                "SELECT * FROM notes WHERE status = ? AND entity = ? AND lease_id IS ? "
                "AND topic IS ? AND text = ? AND policy_version = ?",
                (ACTIVE, entity, lease_id, topic, text, version),
            ).fetchone()
            if same:
                return self.note(same), False
            count = db.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
            note_id = f"N-{count + 1:04d}"
            at = now()
            if replace and (lease_id is not None or topic is not None):
                db.execute(
                    "UPDATE notes SET status = ?, replaced_by = ?, closed_by = ?, "
                    "closed_at = ? WHERE status = ? AND entity = ? AND lease_id IS ? "
                    "AND topic IS ?",
                    (REPLACED, note_id, author, at, ACTIVE, entity, lease_id, topic),
                )
            db.execute(
                "INSERT INTO notes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    note_id,
                    at,
                    author,
                    entity,
                    lease_id,
                    topic,
                    version,
                    text,
                    ACTIVE,
                    None,
                    None,
                    None,
                ),
            )
        return self.get(note_id), True

    def forget(self, note_id: str, by: str) -> Note:
        with self.transaction() as db:
            row = db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
            if row is None:
                raise ValueError(f"no note {note_id}")
            if row["status"] != ACTIVE:
                raise ValueError(f"{note_id} is {row['status']}, not {ACTIVE}")
            db.execute(
                "UPDATE notes SET status = ?, closed_by = ?, closed_at = ? WHERE id = ?",
                (FORGOTTEN, by, now(), note_id),
            )
        return self.get(note_id)
