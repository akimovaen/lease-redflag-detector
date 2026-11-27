"""The lawyer's notes for a person: list them, forget one.

    make notes BY=lawyer                       the notes lawyer may see, all statuses
    make notes BY=lawyer ID=N-0003 FORGET=1    forget one

Unlike the agent, a person sees every note, replaced, forgotten and written under an
older version of the policy too, marked as such, so that nothing the agent no longer
uses is hidden from the lawyer. As in the registry, a note about a lease is shown only
to whoever may read the lease (`access.py`), a general one within the author's entity.
"""

import argparse

from lease_redflag_detector.agent.access import Access
from lease_redflag_detector.agent.memory import ACTIVE, Note, NoteStore, policy_version
from lease_redflag_detector.agent.users import UnknownUser, User, get_user


def visible(note: Note, user: User, access: Access) -> bool:
    if note.lease_id:
        return access.denial(user, note.lease_id) is None
    return note.entity == user.entity


def line(note: Note, version: str) -> str:
    about = " · ".join(filter(None, [note.lease_id, note.topic])) or "загальна"
    marks = [note.status]
    if note.status == ACTIVE and note.policy_version != version:
        marks.append("за попередньою редакцією Політики, агент її не бачить")
    if note.replaced_by:
        marks.append(f"замінена на {note.replaced_by}")
    if note.closed_by and not note.replaced_by:
        marks.append(f"{note.closed_by}, {note.closed_at}")
    return (
        f"{note.id}  {note.created_at[:10]}  {note.author:<9} {about}\n"
        f"         «{note.text}»\n         [{'; '.join(marks)}]"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--by", help="who looks (configs/users.toml)")
    parser.add_argument("--id")
    parser.add_argument("--forget", action="store_true")
    args = parser.parse_args()
    if not args.by:
        raise SystemExit("Say who you are: BY=lawyer, BY=head, … (configs/users.toml)")
    try:
        user = get_user(args.by)
    except UnknownUser as e:
        raise SystemExit(str(e)) from None
    store, access, version = NoteStore(), Access(), policy_version()

    if args.forget:
        if not args.id:
            raise SystemExit("Forgetting needs the note: ID=N-0003")
        note = store.get(args.id)
        if note is None or not visible(note, user, access):
            raise SystemExit(f"No note {args.id}")
        try:
            store.forget(args.id, user.id)
        except ValueError as e:
            raise SystemExit(str(e)) from None
    notes = [n for n in store.all() if visible(n, user, access)]
    if args.id:
        notes = [n for n in notes if n.id == args.id]
    if not notes:
        print("Нотаток немає.")
    for note in notes:
        print(line(note, version))


if __name__ == "__main__":
    main()
