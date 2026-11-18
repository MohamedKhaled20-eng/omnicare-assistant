"""Pydantic models for claim tools: inputs, stored records and results."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

ClaimType = Literal["Water Damage", "Personal Property"]
CLAIM_TYPES: tuple[str, ...] = ("Water Damage", "Personal Property")

CLAIM_ID_RE = re.compile(r"^CLM-[0-9]{1,10}$")
POLICY_NUMBER_RE = re.compile(r"^POL-[0-9]{1,10}$")
MAX_DESCRIPTION_LENGTH = 500
MAX_CLAIM_AMOUNT = Decimal("1000000.00")


class GetClaimStatusInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    claim_id: str

    @field_validator("claim_id", mode="after")
    @classmethod
    def _check_claim_id(cls, v: str) -> str:
        v = v.upper()
        if not CLAIM_ID_RE.match(v):
            raise ValueError("Claim ID must look like CLM-1234 ('CLM-' followed by digits).")
        return v


class SubmitClaimInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    policy_number: str
    claim_type: ClaimType
    amount: Annotated[Decimal, Field(gt=0, decimal_places=2, max_digits=12)]
    description: Annotated[str, Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH)]

    @field_validator("policy_number", mode="after")
    @classmethod
    def _check_policy_number(cls, v: str) -> str:
        v = v.upper()
        if not POLICY_NUMBER_RE.match(v):
            raise ValueError("Policy number must look like POL-1234 ('POL-' followed by digits).")
        return v

    @field_validator("claim_type", mode="before")
    @classmethod
    def _normalize_claim_type(cls, v: Any) -> Any:
        if isinstance(v, str):
            by_lower = {t.lower(): t for t in CLAIM_TYPES}
            return by_lower.get(" ".join(v.split()).lower(), v)
        return v

    @field_validator("amount", mode="before")
    @classmethod
    def _clean_amount(cls, v: Any) -> Any:
        if isinstance(v, bool):
            raise ValueError("Amount must be a number.")
        if isinstance(v, str):
            return re.sub(r"[\s$,]", "", v)
        return v

    @field_validator("amount", mode="after")
    @classmethod
    def _cap_amount(cls, v: Decimal) -> Decimal:
        if v > MAX_CLAIM_AMOUNT:
            raise ValueError(f"Amount cannot exceed ${MAX_CLAIM_AMOUNT:,.2f} per claim.")
        return v.quantize(Decimal("0.01"))


class ClaimRecord(BaseModel):
    claim_id: str
    policy_number: str
    claim_type: str
    status: str
    amount: float
    description: str | None = None  # only present on claims submitted through the assistant

    def to_public(self) -> dict[str, Any]:
        return {**self.model_dump(exclude_none=True), "amount_formatted": f"${self.amount:,.2f}"}


class ClaimStatusResult(BaseModel):
    found: bool
    message: str
    claim: dict[str, Any] | None = None


class SubmitClaimResult(BaseModel):
    success: bool
    message: str
    claim_id: str | None = None
    claim: dict[str, Any] | None = None
    errors: list[str] = Field(default_factory=list)


_FIELD_MESSAGES: dict[str, str] = {
    "claim_id": "Claim ID must look like CLM-1234 ('CLM-' followed by digits).",
    "policy_number": "Policy number must look like POL-1234 ('POL-' followed by digits).",
    "claim_type": f"Claim type must be one of: {', '.join(CLAIM_TYPES)}.",
    "description": f"Description is required (1-{MAX_DESCRIPTION_LENGTH} characters).",
}

_AMOUNT_MESSAGES: dict[str, str] = {
    "greater_than": "Amount must be greater than 0.",
    "decimal_max_places": "Amount can have at most 2 decimal places (e.g. 1250.00).",
    "decimal_max_digits": "Amount is too large.",
}


def friendly_errors(exc: ValidationError) -> list[str]:
    """Turn a pydantic ValidationError into short, user-facing sentences (deduplicated)."""
    messages: list[str] = []
    for err in exc.errors():
        field = str(err["loc"][0]) if err["loc"] else ""
        if field == "amount":
            if err["type"] == "value_error":
                msg = err["msg"].removeprefix("Value error, ")
            else:
                msg = _AMOUNT_MESSAGES.get(err["type"], "Amount must be a positive number, e.g. 1250.00.")
        elif field == "policy_number" and err["type"] == "value_error":
            msg = err["msg"].removeprefix("Value error, ")
        else:
            msg = _FIELD_MESSAGES.get(field, "Invalid input.")
        if msg not in messages:
            messages.append(msg)
    return messages
