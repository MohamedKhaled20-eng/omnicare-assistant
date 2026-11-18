"""Mock claims backend: JSON-file store (file lock + atomic writes) and the two operational tools."""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from filelock import FileLock
from pydantic import ValidationError

from app.tools.schemas import (
    ClaimRecord,
    ClaimStatusResult,
    GetClaimStatusInput,
    SubmitClaimInput,
    SubmitClaimResult,
    friendly_errors,
)

logger = logging.getLogger(__name__)

INITIAL_STATUS = "Submitted"
LOCK_TIMEOUT_SECONDS = 10


class ClaimsStoreError(RuntimeError):
    """The claims file is unreadable or unwritable."""


class ClaimsRepository:
    """File-backed claims store. Safe for concurrent writers (inter-process lock + atomic replace)."""

    def __init__(self, path: Path, seed_path: Path | None = None) -> None:
        self.path = Path(path)
        self._seed_path = Path(seed_path) if seed_path else None
        self._lock = FileLock(f"{self.path}.lock", timeout=LOCK_TIMEOUT_SECONDS)

    def initialize(self) -> None:
        """Create the working file from the seed data when it does not exist yet."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            if self.path.exists():
                return
            if self._seed_path and self._seed_path.exists():
                shutil.copyfile(self._seed_path, self.path)
                logger.info("claims store seeded", extra={"path": str(self.path)})
            else:
                self._write([])

    def _read(self) -> list[dict[str, Any]]:
        try:
            records = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, json.JSONDecodeError) as exc:
            raise ClaimsStoreError("Claims data is unavailable.") from exc
        if not isinstance(records, list):
            raise ClaimsStoreError("Claims data is malformed.")
        return records

    def _write(self, records: list[dict[str, Any]]) -> None:
        descriptor, temporary_path = tempfile.mkstemp(
            dir=self.path.parent, prefix=".claims-", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as temporary_file:
                json.dump(records, temporary_file, indent=2)
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, self.path)
        except BaseException:
            Path(temporary_path).unlink(missing_ok=True)
            raise

    def get(self, claim_id: str) -> ClaimRecord | None:
        for record in self._read():
            if record.get("claim_id") == claim_id:
                return ClaimRecord.model_validate(record)
        return None

    def add(self, claim: SubmitClaimInput) -> ClaimRecord:
        with self._lock:
            records = self._read()
            record = ClaimRecord(
                claim_id=self._next_claim_id(records),
                policy_number=claim.policy_number,
                claim_type=claim.claim_type,
                status=INITIAL_STATUS,
                amount=float(claim.amount),
                description=claim.description,
            )
            records.append(record.model_dump(exclude_none=True))
            self._write(records)
            return record

    @staticmethod
    def _next_claim_id(records: list[dict[str, Any]]) -> str:
        existing_ids = [
            int(str(record["claim_id"]).removeprefix("CLM-"))
            for record in records
            if str(record.get("claim_id", "")).removeprefix("CLM-").isdigit()
        ]
        return f"CLM-{max(existing_ids, default=1000) + 1:04d}"


def get_claim_status(repository: ClaimsRepository, claim_id: str) -> ClaimStatusResult:
    """Look up a claim. Never raises for bad input: returns a structured result instead."""
    try:
        request = GetClaimStatusInput(claim_id=claim_id)
    except ValidationError as error:
        return ClaimStatusResult(found=False, message=" ".join(friendly_errors(error)))

    claim = repository.get(request.claim_id)
    if claim is None:
        return ClaimStatusResult(
            found=False,
            message=f"Claim {request.claim_id} was not found. Please double-check the ID and try again.",
        )
    return ClaimStatusResult(found=True, message="Claim found.", claim=claim.to_public())


def submit_claim(
    repository: ClaimsRepository,
    policy_number: Any,
    claim_type: Any,
    amount: Any,
    description: Any,
) -> SubmitClaimResult:
    """Validate and persist a new claim. Invalid input writes nothing and returns clear errors."""
    try:
        request = SubmitClaimInput(
            policy_number=policy_number, claim_type=claim_type, amount=amount, description=description
        )
    except ValidationError as error:
        errors = friendly_errors(error)
        logger.info("claim submission rejected", extra={"errors": errors})
        return SubmitClaimResult(
            success=False, message="The claim was not submitted: " + " ".join(errors), errors=errors
        )

    record = repository.add(request)
    logger.info("claim submitted", extra={"claim_id": record.claim_id, "claim_type": record.claim_type})
    return SubmitClaimResult(
        success=True,
        message=f"Claim submitted. Your confirmation ID is {record.claim_id}.",
        claim_id=record.claim_id,
        claim=record.to_public(),
    )
