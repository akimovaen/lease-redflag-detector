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

Already downloaded procedures are skipped.

Single public documents can be fetched by id as well, for contracts found outside the
API search (e.g. through a web search of procedure.prozorro.sale):

    uv run python scripts/fetch_prozorro.py --document <document id> ...

Each goes to `data/raw/prozorro/doc-<id>/` with `document.json` (url, file name).
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


def is_candidate(procedure: dict) -> bool:
    return (
        procedure.get("sellingMethod", "").startswith(LEASE_METHODS)
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", default="2026-01-01")
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--max-pages", type=int, default=30)
    parser.add_argument("--document", nargs="+", metavar="ID", default=[])
    args = parser.parse_args()

    client = httpx.Client(timeout=60, follow_redirects=True)
    OUT.mkdir(parents=True, exist_ok=True)
    if args.document:
        for document_id in args.document:
            fetch_document(client, document_id)
        return

    found = sum(
        not path.parent.name.startswith("doc-") for path in OUT.glob("*/contract.pdf")
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
        for record in filter(is_candidate, records):
            folder = OUT / record["auctionId"]
            if (folder / "contract.pdf").exists():
                continue
            procedure = client.get(f"{API}/procedures/{record['_id']}").json()
            match = signed_contract(procedure)
            if not match:
                continue
            buyer, url = match
            pdf = client.get(url)
            if pdf.status_code != 200 or not pdf.content.startswith(b"%PDF"):
                continue
            folder.mkdir(exist_ok=True)
            (folder / "procedure.json").write_text(
                json.dumps(procedure, ensure_ascii=False, indent=2)
            )
            (folder / "contract.pdf").write_bytes(pdf.content)
            found += 1
            name = buyer["identifier"]["legalName"]["uk_UA"]
            print(f"{found:>3} {record['auctionId']}  {name[:60]}")
            if found >= args.count:
                break
            time.sleep(0.5)
    print(f"{found} contracts in {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
