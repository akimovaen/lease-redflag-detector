"""The approval queue for a person: list the requests, show one, decide on it.

    make review BY=lawyer                              the requests lawyer may see
    make review BY=lawyer ID=R-0001                    one, with its points and history
    make review BY=head ID=R-0001 STATUS=відхилено COMMENT="…"
                                                       a decision on a pending one

The agent can only create requests; deciding on them is here, outside the agent.
Whoever looks at the queue says who they are (BY, a user of configs/users.toml), since
a request quotes its lease: a person sees only the requests for the leases they may
read (`access.py`), as in the registry. A decision is recorded by a lawyer or the head
of legal (`users.DECIDERS`) who may read the lease, which is then of their own entity.
A rejected or returned request also becomes a note on the lease for the agent, so that
its next check knows the committee's reason (`decision_note`).
"""

import argparse
import datetime
import sqlite3

from lease_redflag_detector.agent.access import Access
from lease_redflag_detector.agent.memory import Note, NoteStore, policy_version
from lease_redflag_detector.agent.queue import (
    DECISIONS,
    RISKS,
    VERDICTS,
    ApprovalQueue,
    Request,
)
from lease_redflag_detector.agent.users import DECIDERS, UnknownUser, User, get_user


def show(queue: ApprovalQueue, request: Request) -> None:
    print(f"Заявка {request.id} · {request.status}")
    print(f"Договір: {request.lease_id} · Кому: {request.addressee}")
    print(f"Створено: {request.created_at}, {request.created_by}")
    if request.replaces:
        print(f"Замінює: {request.replaces}")
    for section in ("погодження", "до відома"):
        items = [i for i in request.items if i["section"] == section]
        if items:
            print(f"\nПункти: {section}")
        for n, item in enumerate(items, 1):
            print(
                f" {n}. {item['type']} · {VERDICTS[item['verdict']]} · ризик "
                f"{RISKS.get(item['risk'], item['risk'])}"
            )
            print(f"    Пункт договору: «{item['quote']}»")
            for gap in item["gaps"]:
                print(f"    Відкрите питання: {gap}")
            if item["proposed_clause"]:
                print(f"    Редакція: «{item['proposed_clause']}»")
            if item["sources"]:
                print(f"    Джерела: {'; '.join(item['sources'])}")
    print("\nІсторія:")
    for entry in queue.history(request.id):
        comment = f" — {entry['comment']}" if entry["comment"] else ""
        print(f"  {entry['at']}  {entry['status']}  ({entry['by']}){comment}")


def person(user_id: str | None) -> User:
    """Who looks at the queue."""
    if not user_id:
        raise SystemExit("Say who you are: BY=lawyer, BY=head, … (configs/users.toml)")
    try:
        return get_user(user_id)
    except UnknownUser as e:
        raise SystemExit(str(e)) from None


def may_read(user: User, lease_id: str, access: Access) -> None:
    if denial := access.denial(user, lease_id):
        raise SystemExit(denial)


def decider(user_id: str | None, lease_id: str, access: Access | None = None) -> User:
    """The user who records a decision on a request for the lease, if they may: a
    lawyer or the head of legal who may read the lease."""
    user = person(user_id)
    if user.role not in DECIDERS:
        raise SystemExit(
            f"{user.describe()} may not record decisions on approval requests."
        )
    may_read(user, lease_id, access or Access())
    return user


# Decisions that need something done about the lease: the agent should know them.
NOTED = ("відхилено", "повернуто")


def decision_note(
    store: NoteStore, request: Request, status: str, user: User, comment: str
) -> Note | None:
    """A note on the lease for the agent, when the committee rejected or returned
    the request: the next check of the lease knows why."""
    if status not in NOTED:
        return None
    note, _ = store.add(
        f"Комітет: заявку {request.id} {status} {datetime.date.today():%d.%m.%Y}: "
        f"{comment or 'без коментаря'}",
        user.id,
        user.entity,
        policy_version(),
        request.lease_id,
        replace=False,
    )
    return note


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--id")
    parser.add_argument("--status", choices=DECISIONS)
    parser.add_argument("--comment", default="")
    parser.add_argument("--by", help="who looks or decides (configs/users.toml)")
    args = parser.parse_args()
    user = person(args.by)
    access = Access()
    queue = ApprovalQueue()

    if args.status and not args.id:
        raise SystemExit("A decision needs the request: ID=R-0001")
    if args.id:
        request = queue.get(args.id)
        if request is None:
            raise SystemExit(f"No request {args.id}")
        if args.status:
            decider(user.id, request.lease_id, access)
            try:
                queue.decide(args.id, args.status, user.id, args.comment)
            except ValueError as e:
                raise SystemExit(str(e)) from None
            request = queue.get(args.id)
            try:
                note = decision_note(
                    NoteStore(), request, args.status, user, args.comment
                )
            except sqlite3.Error as e:
                print(
                    f"Рішення записано, але нотатку для агента створити не вдалося: {e}"
                )
            else:
                if note:
                    print(f"Рішення збережено як нотатку {note.id} для агента.")
        may_read(user, request.lease_id, access)
        show(queue, request)
        return
    requests = visible(queue.all(), user, access)
    if not requests:
        print("Заявок немає.")
    for r in requests:
        points = sum(i["section"] == "погодження" for i in r.items)
        print(
            f"{r.id}  {r.status:<10} {r.lease_id:<12} пунктів на погодження: {points}"
            f"  {r.created_at}"
        )


def visible(requests: list[Request], user: User, access: Access) -> list[Request]:
    """The requests for the leases the user may read."""
    return [r for r in requests if access.restriction(user, r.lease_id) is None]


if __name__ == "__main__":
    main()
