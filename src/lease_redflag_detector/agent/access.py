"""Who may read which lease of the registry: the rules the registry server applies.

The marks of the leases are in configs/lease_access.toml; the users and their roles in
configs/users.toml. Three reasons refuse a lease, checked in this order:

- B, another legal entity of the group: only the users of that entity read it, and
  the others do not see that it exists (it is the registry of another company);
- A, a court dispute: only the litigation team;
- C, an NDA with an anchor tenant: only the head of legal.

A and C leases are listed to the users of their entity, marked as restricted, so that
the lawyer knows the lease exists and whom to ask. Every denial starts with `DENIED`,
which the agent's client recognizes as a refusal that no retry or other tool can get
past.
"""

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from lease_redflag_detector.agent.users import User

ROOT = Path(__file__).resolve().parents[3]
ACCESS = ROOT / "configs" / "lease_access.toml"
DENIED = "Access denied"


class LeaseMarks(BaseModel):
    model_config = ConfigDict(extra="forbid")  # a misspelt mark must not pass silently

    entity: str | None = None  # None: the default entity
    litigation: bool = False
    nda: bool = False


class Access:
    def __init__(self, path: Path = ACCESS):
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        self.default_entity: str = data["default_entity"]
        self.marks = {
            lease_id: LeaseMarks.model_validate(marks)
            for lease_id, marks in data.get("leases", {}).items()
        }

    def entity(self, lease_id: str) -> str:
        marks = self.marks.get(lease_id)
        return (marks and marks.entity) or self.default_entity

    def restriction(self, user: User, lease_id: str) -> str | None:
        """Why `user` may not read the lease, or None if they may."""
        marks = self.marks.get(lease_id, LeaseMarks())
        entity = self.entity(lease_id)
        if entity != user.entity:
            return f"it belongs to another legal entity of the group ({entity})"
        if marks.litigation and user.role != "litigation":
            return "it is in a court dispute; only the litigation team may read it"
        if marks.nda and user.role != "head_of_legal":
            return (
                "it is under an NDA with an anchor tenant; only the head of legal may "
                "read it"
            )
        return None

    def shared(self, user: User, lease_id: str) -> bool:
        """Whether every user of the user's entity may read the lease: no court
        dispute, no NDA. Only such leases may serve as market practice in a redline,
        since a redline goes to the approval queue, where others read it."""
        marks = self.marks.get(lease_id, LeaseMarks())
        return (
            self.entity(lease_id) == user.entity
            and not marks.litigation
            and not marks.nda
        )

    def listed(self, user: User, lease_id: str) -> bool:
        """Whether the lease shows in the user's search: not a lease of another entity."""
        return self.entity(lease_id) == user.entity

    def denial(self, user: User, lease_id: str) -> str | None:
        reason = self.restriction(user, lease_id)
        return f"{DENIED}: {lease_id}: {reason}." if reason else None
