"""The approval queue for a person: list the requests, show one, decide on it.

    make review                                        every request
    make review ID=R-0001                              one, with its points and history
    make review ID=R-0001 STATUS=відхилено COMMENT="…" a decision on a pending one

The agent can only create requests; deciding on them is here, outside the agent.
"""

import argparse

from lease_redflag_detector.agent.queue import (
    DECISIONS,
    RISKS,
    VERDICTS,
    ApprovalQueue,
    Request,
)


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--id")
    parser.add_argument("--status", choices=DECISIONS)
    parser.add_argument("--comment", default="")
    parser.add_argument("--by", default="lawyer")
    args = parser.parse_args()
    queue = ApprovalQueue()

    if args.status:
        if not args.id:
            raise SystemExit("A decision needs the request: ID=R-0001")
        try:
            queue.decide(args.id, args.status, args.by, args.comment)
        except ValueError as e:
            raise SystemExit(str(e)) from None
    if args.id:
        request = queue.get(args.id)
        if request is None:
            raise SystemExit(f"No request {args.id}")
        show(queue, request)
        return
    requests = queue.all()
    if not requests:
        print("Черга порожня.")
    for r in requests:
        points = sum(i["section"] == "погодження" for i in r.items)
        print(
            f"{r.id}  {r.status:<10} {r.lease_id:<12} пунктів на погодження: {points}"
            f"  {r.created_at}"
        )


if __name__ == "__main__":
    main()
