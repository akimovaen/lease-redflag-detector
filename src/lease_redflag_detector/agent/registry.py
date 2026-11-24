"""The registry of the landlord's leases: find a lease, read its sections and its text.

It reads the pseudonymized Prozorro leases of the corpus. The agent does not use it
directly: the registry is served by an MCP server (`registry_server.py`), and the agent
reaches it through `registry_client.py`, as any other client would. The schemas of the
registry's tools are here, shared by the server and the agent.
"""

import re
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field

from lease_redflag_detector.rag.chunking import block_text, sections
from lease_redflag_detector.rag.document import Document

ROOT = Path(__file__).resolve().parents[3]
DOCUMENTS = ROOT / "data" / "corpus" / "documents"
QUOTES = re.compile(r'["«»“”„]')

LEASE_ID = r"^lease_\d+$"
LeaseId = Annotated[
    str, Field(pattern=LEASE_ID, description="Lease id, e.g. lease_37032.")
]
Party = Annotated[
    str | None,
    Field(max_length=100, description="Part of the landlord's or tenant's name."),
]
City = Annotated[
    str | None, Field(max_length=100, description="Part of the city name.")
]
SectionNumber = Annotated[
    int, Field(ge=1, description="Section number from get_lease.")
]


class FindArgs(BaseModel):
    party: Party = None
    city: City = None


class LeaseSummary(BaseModel):
    lease_id: str
    title: str
    landlord: str
    tenant: str
    city: str
    date: str


class FoundLease(LeaseSummary):
    # Why the user may not read it (access.py); None if they may.
    restricted: str | None = None


class FindResult(BaseModel):
    leases: list[FoundLease]


class LeaseArgs(BaseModel):
    lease_id: LeaseId


class SectionTitle(BaseModel):
    number: int
    title: str


class LeaseInfo(LeaseSummary):
    sections: list[SectionTitle]


class SectionArgs(LeaseArgs):
    section: SectionNumber


class SectionText(BaseModel):
    lease_id: str
    number: int
    title: str
    text: str


class LeaseNotFound(Exception):
    def __init__(self, lease_id: str):
        super().__init__(
            f"No lease {lease_id} in the registry; find_leases lists them."
        )


@dataclass
class Section:
    number: int  # position in the lease, from 1
    title: str
    text: str


def normalize(text: str) -> str:
    return " ".join(QUOTES.sub(" ", text).casefold().split())


class LeaseRegistry:
    def __init__(self, documents: Path = DOCUMENTS):
        self.documents = documents

    @cached_property
    def leases(self) -> dict[str, Document]:
        paths = sorted(self.documents.glob("lease_*.json"))
        return {path.stem: Document.load(path) for path in paths}

    def lease(self, lease_id: str) -> Document:
        if lease_id not in self.leases:
            raise LeaseNotFound(lease_id)
        return self.leases[lease_id]

    def summary(self, lease_id: str) -> dict:
        document = self.lease(lease_id)
        meta = document.meta
        return {
            "lease_id": lease_id,
            "title": document.title,
            "landlord": meta.get("landlord", ""),
            "tenant": meta.get("tenant", ""),
            "city": meta.get("city", ""),
            "date": meta.get("date", ""),
        }

    def find(self, party: str | None = None, city: str | None = None) -> list[dict]:
        """Leases where `party` is in the landlord's or tenant's name and `city` in the
        city, ignoring case and quotes."""
        found = []
        for lease_id, document in self.leases.items():
            names = normalize(
                f"{document.meta.get('landlord')} {document.meta.get('tenant')}"
            )
            if party and normalize(party) not in names:
                continue
            if city and normalize(city) not in normalize(document.meta.get("city", "")):
                continue
            found.append(self.summary(lease_id))
        return found

    def sections(self, lease_id: str) -> list[Section]:
        return [
            Section(
                number,
                section.path[-1] if section.path else "(преамбула)",
                "\n".join(block_text(block) for block in section.blocks),
            )
            for number, section in enumerate(sections(self.lease(lease_id)), start=1)
        ]

    def text(self, lease_id: str) -> str:
        return self.lease(lease_id).text
