from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.tools.claims import ClaimsRepository, get_claim_status, submit_claim
from tests.conftest import REAL_SEED

VALID = {
    "policy_number": "POL-1092",
    "claim_type": "Water Damage",
    "amount": 1250.5,
    "description": "Kitchen pipe burst overnight",
}


def _records(path: Path) -> list[dict]:
    return json.loads(path.read_text())


# --- get_claim_status ---------------------------------------------------------------
def test_status_found(repo: ClaimsRepository) -> None:
    result = get_claim_status(repo, "CLM-8821")
    assert result.found is True
    assert result.claim is not None
    assert result.claim["claim_id"] == "CLM-8821"
    assert result.claim["policy_number"] == "POL-1092"
    assert result.claim["claim_type"] == "Water Damage"
    assert result.claim["status"] == "Approved"
    assert result.claim["amount"] == 3500.00
    assert result.claim["amount_formatted"] == "$3,500.00"


def test_status_is_case_and_whitespace_insensitive(repo: ClaimsRepository) -> None:
    assert get_claim_status(repo, "  clm-9014 ").found is True


def test_status_not_found_is_a_result_not_an_exception(repo: ClaimsRepository) -> None:
    result = get_claim_status(repo, "CLM-0000")
    assert result.found is False
    assert result.claim is None
    assert "CLM-0000" in result.message and "not found" in result.message.lower()


@pytest.mark.parametrize("bad_id", ["8821", "CLM-", "CLM-ABC", "CLM8821", "", "CLM-12 34", "'; DROP TABLE--"])
def test_status_invalid_id_format(repo: ClaimsRepository, bad_id: str) -> None:
    result = get_claim_status(repo, bad_id)
    assert result.found is False
    assert "CLM-1234" in result.message


# --- submit_claim -------------------------------------------------------------------
def test_submit_valid_claim_persists_record(repo: ClaimsRepository, claims_file: Path) -> None:
    result = submit_claim(repo, **VALID)

    assert result.success is True
    assert result.claim_id == "CLM-9015"  # max existing (9014) + 1
    assert result.claim is not None
    assert result.claim["status"] == "Submitted"
    assert result.claim["amount"] == 1250.5

    stored = _records(claims_file)
    assert len(stored) == 3
    assert stored[-1] == {
        "claim_id": "CLM-9015",
        "policy_number": "POL-1092",
        "claim_type": "Water Damage",
        "status": "Submitted",
        "amount": 1250.5,
        "description": "Kitchen pipe burst overnight",
    }
    assert stored[:2] == _records(REAL_SEED)  # seed records untouched


def test_submitted_claim_can_be_looked_up(repo: ClaimsRepository) -> None:
    claim_id = submit_claim(repo, **VALID).claim_id
    assert claim_id is not None
    found = get_claim_status(repo, claim_id)
    assert found.found and found.claim and found.claim["status"] == "Submitted"


def test_claim_ids_are_unique(repo: ClaimsRepository) -> None:
    ids = {submit_claim(repo, **VALID).claim_id for _ in range(5)}
    assert len(ids) == 5


def test_normalizes_inputs(repo: ClaimsRepository, claims_file: Path) -> None:
    result = submit_claim(
        repo,
        policy_number=" pol-3341 ",
        claim_type="personal   property",
        amount="$1,200.00",
        description="  Stolen laptop  ",
    )
    assert result.success
    last = _records(claims_file)[-1]
    assert (last["policy_number"], last["claim_type"], last["amount"], last["description"]) == (
        "POL-3341",
        "Personal Property",
        1200.0,
        "Stolen laptop",
    )


@pytest.mark.parametrize(
    ("override", "expected_fragment"),
    [
        ({"amount": -50}, "greater than 0"),
        ({"amount": 0}, "greater than 0"),
        ({"amount": "abc"}, "amount must be a positive number"),
        ({"amount": 10.123}, "2 decimal places"),
        ({"amount": float("nan")}, "amount"),
        ({"amount": 5_000_000}, "cannot exceed"),
        ({"amount": True}, "must be a number"),
        ({"policy_number": "ABC123"}, "POL-1234"),
        ({"policy_number": "POL-"}, "POL-1234"),
        ({"policy_number": "POL-12AB"}, "POL-1234"),
        ({"claim_type": "Fire"}, "Water Damage, Personal Property"),
        ({"description": "   "}, "Description is required"),
        ({"description": ""}, "Description is required"),
        ({"description": "x" * 501}, "Description is required"),
    ],
)
def test_submit_rejects_invalid_input_and_writes_nothing(
    repo: ClaimsRepository, claims_file: Path, override: dict, expected_fragment: str
) -> None:
    before = claims_file.read_text()
    result = submit_claim(repo, **{**VALID, **override})

    assert result.success is False
    assert result.claim_id is None and result.claim is None
    assert any(expected_fragment.lower() in e.lower() for e in result.errors), result.errors
    assert claims_file.read_text() == before


def test_submit_reports_every_invalid_field(repo: ClaimsRepository) -> None:
    result = submit_claim(repo, policy_number="X", claim_type="Fire", amount=-1, description="")
    assert len(result.errors) == 4


def test_repository_seeds_missing_working_file(tmp_path: Path) -> None:
    target = tmp_path / "new" / "claims.json"
    ClaimsRepository(target, REAL_SEED).initialize()
    assert _records(target) == _records(REAL_SEED)
    # Re-initialising must not clobber existing data.
    repo = ClaimsRepository(target, REAL_SEED)
    submit_claim(repo, **VALID)
    repo.initialize()
    assert len(_records(target)) == 3


def test_concurrent_submissions_do_not_lose_records(repo: ClaimsRepository, claims_file: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(lambda _: submit_claim(repo, **VALID).claim_id, range(20)))
    assert len(set(ids)) == 20
    assert len(_records(claims_file)) == 22
