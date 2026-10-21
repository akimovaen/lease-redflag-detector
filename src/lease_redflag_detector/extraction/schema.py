"""Structured output of lease extraction.

Every model must return a `LeaseAbstract`. Field descriptions end up in the JSON
schema sent to the model, so they double as extraction instructions.

Fields are kept simple so they can be scored against the golden set:
strings by normalized match, dates and enums exactly, numbers within a small
tolerance, and `red_flags` as F1 over the set of red flag types.
"""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class DocumentType(StrEnum):
    LEASE = "lease"
    AMENDMENT = "amendment"
    OTHER = "other"


class AreaUnit(StrEnum):
    SQM = "sqm"
    SQFT = "sqft"


class RentPeriod(StrEnum):
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"


class Indexation(StrEnum):
    NONE = "none"
    FIXED = "fixed"
    INDEX_LINKED = "index_linked"
    MARKET_REVIEW = "market_review"


class RedFlagType(StrEnum):
    LANDLORD_REPAIRS = "landlord_repairs"
    SERVICE_CHARGES_LIMITED = "service_charges_limited"
    TENANT_BREAK_OPTION = "tenant_break_option"
    INDEXATION_LIMITED = "indexation_limited"
    SUBLEASE_PERMITTED = "sublease_permitted"


class Area(BaseModel):
    value: float = Field(description="Total leased area as a number.")
    unit: AreaUnit = Field(description="Unit as stated in the lease.")


class Rent(BaseModel):
    amount: float = Field(description="Base rent for one period, without VAT.")
    currency: str = Field(description="ISO 4217 code of the rent amount, e.g. EUR.")
    period: RentPeriod


class RedFlag(BaseModel):
    type: RedFlagType = Field(
        description=(
            "landlord_repairs: the landlord bears repairs or maintenance beyond the "
            "structure of the building, e.g. building systems, facilities or "
            "normal wear and tear. "
            "service_charges_limited: the landlord bears operating costs "
            "(management fees, utilities, taxes, insurance), they are included in "
            "the rent, or the tenant's share is capped or may be refused. "
            "tenant_break_option: the tenant may terminate before the end date on "
            "its own decision, with or without notice or a penalty. Not the "
            "landlord's right to terminate for the tenant's breach, and not a "
            "termination that needs the landlord's consent. "
            "indexation_limited: the rent cannot be increased, increases are "
            "capped, or they require the tenant's agreement. "
            "sublease_permitted: the tenant may sublet or assign without the "
            "landlord's consent, the landlord may not refuse or unreasonably "
            "withhold consent, or certain subtenants are pre-approved."
        )
    )
    quote: str = Field(
        description="Verbatim text of the clause that raises the flag, copied exactly."
    )


class LeaseAbstract(BaseModel):
    """Key terms of a commercial lease and the clauses that are risky for the landlord."""

    document_type: DocumentType = Field(
        description="lease for a full lease agreement, amendment for an addendum "
        "or side letter changing an existing lease, other for anything else."
    )
    lessor: str | None = Field(description="Legal name of the landlord.")
    lessee: str | None = Field(description="Legal name of the tenant.")
    premises_address: str | None = Field(
        description="Address of the leased premises as written in the lease."
    )
    area: Area | None
    start_date: date | None = Field(description="Date the lease term begins.")
    end_date: date | None = Field(
        description="Date the lease term ends; compute it from the start date and "
        "the term if it is not stated explicitly."
    )
    rent: Rent | None
    indexation: Indexation | None = Field(
        description="How the rent changes over time: none, fixed steps or "
        "percentages, linked to an index such as CPI, or a market review."
    )
    red_flags: list[RedFlag] = Field(
        description="Clauses that weaken the landlord's position. One entry per "
        "clause; an empty list if there are none."
    )
