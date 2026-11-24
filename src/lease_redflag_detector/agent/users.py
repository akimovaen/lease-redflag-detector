"""Who works with the agent: the users of configs/users.toml and their roles.

A user has a role from a fixed list and a legal entity of the group. An unknown user,
role or entity stops the program instead of running with rights nobody gave: the
registry server refuses to start (`registry_server.py`), and so do the agent and
`make review`.

What a role may do:
- read leases: the registry server decides, by the rules of `access.py`;
- record a decision on an approval request (`make review`): a lawyer or the head of
  legal (`DECIDERS`) who may read the lease, which is then of their own entity.
"""

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[3]
USERS = ROOT / "configs" / "users.toml"

Role = Literal["lawyer", "litigation", "head_of_legal"]
ROLE_NAMES = {
    "lawyer": "юрист",
    "litigation": "судова команда",
    "head_of_legal": "керівник юрдепартаменту",
}
# Roles that may record a decision on an approval request.
DECIDERS = {"lawyer", "head_of_legal"}


class UnknownUser(Exception):
    pass


class User(BaseModel):
    id: str
    name: str
    role: Role
    entity: str

    def describe(self) -> str:
        return f"{self.id} ({ROLE_NAMES[self.role]}, {self.entity})"


def load_users(path: Path = USERS) -> dict[str, User]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    users = {
        user_id: User(id=user_id, **fields) for user_id, fields in data["users"].items()
    }
    for user in users.values():
        if user.entity not in data["entities"]:
            raise ValueError(f"{user.id}: unknown entity {user.entity!r} in {path}")
    return users


def get_user(user_id: str | None, path: Path = USERS) -> User:
    users = load_users(path)
    if user_id not in users:
        raise UnknownUser(
            f"Unknown user {user_id!r}; the users are {', '.join(users)} "
            f"({path.relative_to(ROOT) if path.is_relative_to(ROOT) else path})."
        )
    return users[user_id]
