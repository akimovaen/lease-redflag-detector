"""Download signed lease contracts of state and municipal property from Prozorro.Sale.

    uv run python scripts/fetch_prozorro.py --since 2026-01-01 --count 20

Prozorro.Sale is Ukraine's public e-auction system. After an auction for the lease of
state or municipal property, the signed lease contract is attached to the procedure
and published. The script pages through the public API from `--since`, keeps completed
property lease auctions whose documents are public (many are masked under martial law)
and whose tenant is a legal entity (an 8-digit EDRPOU code, not an individual), and
saves each one to `data/raw/prozorro/<auction id>/`:

    procedure.json   the full procedure record
    contract.pdf     the signed lease contract

Already downloaded procedures are skipped, and `--count` includes them.

By default the script takes leases of state and municipal property, which follow the
Law "On the Lease of State and Municipal Property" and its standard contract.
`--methods commercialPropertyLease` takes commercial leases instead: property of
companies outside that law (e.g. JSC Ukrtelecom), leased under the Civil Code.

Single public documents can be fetched by id as well, for contracts found outside the
API search (e.g. through a web search of procedure.prozorro.sale):

    uv run python scripts/fetch_prozorro.py --document <document id> ...

Each goes to `data/raw/prozorro/doc-<id>/` with `document.json` (url, file name).

Procedures can also be fetched by auction id, with the same filters:

    uv run python scripts/fetch_prozorro.py --auction CLE001-UA-20230412-83432 ...
"""

import argparse
import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "prozorro"
API = "https://procedure.prozorro.sale/api"
LEASE_METHODS = ("legitimatePropertyLease", "regulationsPropertyLease")


def is_candidate(procedure: dict, methods: tuple[str, ...]) -> bool:
    return (
        procedure.get("sellingMethod", "").startswith(methods)
        and procedure.get("status") == "complete"
        and not procedure.get("_protected")
        and bool(procedure.get("contracts"))
    )


def signed_contract(procedure: dict) -> tuple[dict, str] | None:
    """Return the buyer and the URL of the signed contract, if the tenant is a company."""
    for contract in procedure.get("contracts", []):
        buyers = contract.get("buyers") or []
        if not buyers or len(buyers[0].get("identifier", {}).get("id", "")) != 8:
            continue
        for doc in contract.get("documents", []):
            url = doc.get("url", "")
            if doc.get("documentType") == "contractSigned" and url.startswith("http"):
                return buyers[0], url
    return None


def fetch_document(client: httpx.Client, document_id: str) -> None:
    folder = OUT / f"doc-{document_id}"
    if (folder / "contract.pdf").exists():
        return
    url = f"{API}/documents/public/{document_id}"
    response = client.get(url)
    response.raise_for_status()
    if not response.content.startswith(b"%PDF"):
        raise ValueError(f"{document_id} is not a PDF")
    disposition = response.headers.get("content-disposition", "")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "document.json").write_text(
        json.dumps({"url": url, "content_disposition": disposition}, indent=2)
    )
    (folder / "contract.pdf").write_bytes(response.content)
    print(f"doc-{document_id}")


def save_procedure(client: httpx.Client, procedure_id: str) -> bool:
    """Save a procedure and its signed contract if the tenant is a company."""
    procedure = client.get(f"{API}/procedures/{procedure_id}").json()
    match = signed_contract(procedure)
    if not match:
        return False
    buyer, url = match
    pdf = client.get(url)
    if pdf.status_code != 200 or not pdf.content.startswith(b"%PDF"):
        return False
    folder = OUT / procedure["auctionId"]
    folder.mkdir(exist_ok=True)
    (folder / "procedure.json").write_text(
        json.dumps(procedure, ensure_ascii=False, indent=2)
    )
    (folder / "contract.pdf").write_bytes(pdf.content)
    name = buyer["identifier"]["legalName"]["uk_UA"]
    print(f"{procedure['auctionId']}  {name[:60]}")
    return True


def fetch_auction(client: httpx.Client, auction_id: str, methods: tuple[str, ...]):
    if (OUT / auction_id / "contract.pdf").exists():
        return
    response = client.get(f"{API}/search/byAuctionId/{auction_id}")
    response.raise_for_status()
    records = response.json()
    records = records if isinstance(records, list) else [records]
    for record in records:
        if is_candidate(record, methods) and save_procedure(client, record["_id"]):
            return
    print(f"{auction_id}  skipped: not a completed public lease with a company tenant")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", default="2026-01-01")
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--max-pages", type=int, default=30)
    parser.add_argument("--document", nargs="+", metavar="ID", default=[])
    parser.add_argument("--auction", nargs="+", metavar="ID", default=[])
    parser.add_argument(
        "--methods",
        nargs="+",
        default=list(LEASE_METHODS),
        help="selling methods to take (prefixes, e.g. commercialPropertyLease)",
    )
    args = parser.parse_args()

    client = httpx.Client(timeout=60, follow_redirects=True)
    OUT.mkdir(parents=True, exist_ok=True)
    if args.document:
        for document_id in args.document:
            fetch_document(client, document_id)
        return
    if args.auction:
        for auction_id in args.auction:
            fetch_auction(client, auction_id, tuple(args.methods))
        return

    methods = tuple(args.methods)
    found = sum(
        json.loads(path.read_text())["sellingMethod"].startswith(methods)
        for path in OUT.glob("*/procedure.json")
    )
    cursor = f"{args.since}T00:00:00"
    for _ in range(args.max_pages):
        if found >= args.count:
            break
        page = client.get(
            f"{API}/search/byDateModified/{cursor}", params={"limit": 100}
        )
        page.raise_for_status()
        records = page.json()
        if not records:
            break
        cursor = records[-1]["dateModified"]
        for record in records:
            if not is_candidate(record, methods):
                continue
            if (OUT / record["auctionId"] / "contract.pdf").exists():
                continue
            if save_procedure(client, record["_id"]):
                found += 1
                if found >= args.count:
                    break
                time.sleep(0.5)
    print(f"{found} contracts in {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
