"""The approval queue: one request per lease to the commercial committee.

A request lists the contested points of one lease, as the redlines of stage 2 left
them. It is created only by the agent's `submit_for_review` after the lawyer confirms,
and its status is changed only by a person (`make review`): the agent has no tool for
that.

Each request has an idempotency key, a hash of the lease and its points. Among the
pending requests the key is unique, and checking and creating happen in one
transaction, so a repeated call (the model retrying, a request rerun after a lost
connection) returns the pending request instead of a second one. Once a request is
decided or replaced, the same points may be submitted again as a new request. A lease
has at most one pending request, which the database enforces too: a new request for
the lease replaces it.

The queue is a local SQLite file, not committed; the evals use a fresh one per task.
"""

import datetime
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
QUEUE = ROOT / "data" / "agent" / "queue.db"

PENDING = "очікує"  # also in the indexes of SCHEMA
REPLACED = "замінено"
# What a person may set a pending request to.
DECISIONS = ("погоджено", "відхилено", "повернуто")
ADDRESSEE = "юрист → комерційний комітет"
# How a request shows the verdicts and risks of stage 2.
VERDICTS = {
    "compliant": "відповідає політиці",
    "concession": "поступка",
    "beyond_concessions": "понад поступки",
    "unacceptable": "неприйнятно",
    "not_covered": "політика не визначає",
}
RISKS = {
    "low": "низький",
    "medium": "середній",
    "high": "високий",
    "critical": "критичний",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id TEXT PRIMARY KEY,
    lease_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL,
    addressee TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    items TEXT NOT NULL,
    replaces TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS pending_key
    ON requests (idempotency_key) WHERE status = 'очікує';
CREATE UNIQUE INDEX IF NOT EXISTS pending_lease
    ON requests (lease_id) WHERE status = 'очікує';
CREATE TABLE IF NOT EXISTS history (
    request_id TEXT NOT NULL,
    at TEXT NOT NULL,
    status TEXT NOT NULL,
    by TEXT NOT NULL,
    comment TEXT
);
"""


@dataclass
class Request:
    id: str
    lease_id: str
    idempotency_key: str
    status: str
    addressee: str
    created_at: str
    created_by: str
    items: list[dict]
    replaces: str | None


def now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


class ApprovalQueue:
    def __init__(self, path: Path = QUEUE):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            self.migrate(db)
            db.executescript(SCHEMA)

    @staticmethod
    def migrate(db: sqlite3.Connection) -> None:
        """A queue from before the key was unique among pending requests only: the
        rows move to a table without the old constraint."""
        row = db.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'requests'"
        ).fetchone()
        if row and "idempotency_key TEXT NOT NULL UNIQUE" in row["sql"]:
            db.executescript(
                "BEGIN; ALTER TABLE requests RENAME TO requests_old;"
                + SCHEMA
                + "INSERT INTO requests SELECT * FROM requests_old;"
                "DROP TABLE requests_old; COMMIT;"
            )

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
        """One writer at a time: what is read inside holds until the commit."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
            except BaseException:
                db.execute("ROLLBACK")
                raise
            db.execute("COMMIT")

    @staticmethod
    def request(row: sqlite3.Row) -> Request:
        return Request(**dict(row) | {"items": json.loads(row["items"])})

    def get(self, request_id: str) -> Request | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM requests WHERE id = ?", (request_id,))
            row = row.fetchone()
        return self.request(row) if row else None

    def pending_with_key(self, key: str) -> Request | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM requests WHERE idempotency_key = ? AND status = ?",
                (key, PENDING),
            ).fetchone()
        return self.request(row) if row else None

    def pending(self, lease_id: str) -> Request | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM requests WHERE lease_id = ? AND status = ?",
                (lease_id, PENDING),
            ).fetchone()
        return self.request(row) if row else None

    def all(self) -> list[Request]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM requests ORDER BY id").fetchall()
        return [self.request(row) for row in rows]

    def history(self, request_id: str) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT at, status, by, comment FROM history WHERE request_id = ? "
                "ORDER BY rowid",
                (request_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create(
        self, lease_id: str, key: str, items: list[dict], by: str
    ) -> tuple[Request, bool]:
        """The pending request with this key, or a new one (True) that replaces the
        pending request of the lease, if any."""
        with self.transaction() as db:
            row = db.execute(
                "SELECT * FROM requests WHERE idempotency_key = ? AND status = ?",
                (key, PENDING),
            ).fetchone()
            if row:
                return self.request(row), False
            count = db.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
            request_id = f"R-{count + 1:04d}"
            replaced = db.execute(
                "SELECT id FROM requests WHERE lease_id = ? AND status = ?",
                (lease_id, PENDING),
            ).fetchone()
            at = now()
            if replaced:
                db.execute(
                    "UPDATE requests SET status = ? WHERE id = ?",
                    (REPLACED, replaced["id"]),
                )
                db.execute(
                    "INSERT INTO history VALUES (?, ?, ?, ?, ?)",
                    (replaced["id"], at, REPLACED, by, f"замінено на {request_id}"),
                )
            db.execute(
                "INSERT INTO requests VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    request_id,
                    lease_id,
                    key,
                    PENDING,
                    ADDRESSEE,
                    at,
                    by,
                    json.dumps(items, ensure_ascii=False),
                    replaced["id"] if replaced else None,
                ),
            )
            db.execute(
                "INSERT INTO history VALUES (?, ?, ?, ?, ?)",
                (request_id, at, PENDING, by, "створено агентом за підтвердженням"),
            )
        return self.get(request_id), True

    def decide(self, request_id: str, status: str, by: str, comment: str = "") -> None:
        """A person's decision on a pending request."""
        if status not in DECISIONS:
            raise ValueError(f"status must be one of {', '.join(DECISIONS)}")
        with self.transaction() as db:
            row = db.execute(
                "SELECT status FROM requests WHERE id = ?", (request_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"no request {request_id}")
            if row["status"] != PENDING:
                raise ValueError(f"{request_id} is {row['status']}, not {PENDING}")
            db.execute(
                "UPDATE requests SET status = ? WHERE id = ?", (status, request_id)
            )
            db.execute(
                "INSERT INTO history VALUES (?, ?, ?, ?, ?)",
                (request_id, now(), status, by, comment or None),
            )
