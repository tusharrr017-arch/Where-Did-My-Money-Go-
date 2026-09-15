from __future__ import annotations

from app.services.ingestion.filters import looks_like_account_or_reference_number
from app.services.ingestion.types import TransactionCandidate


def candidate_to_dict(candidate: TransactionCandidate) -> dict:
    return {
        "date": candidate.date,
        "merchant": candidate.merchant,
        "amount": abs(candidate.amount),
        "transaction_type": candidate.transaction_type,
        "description": candidate.description,
    }


def validate_candidate(candidate: TransactionCandidate) -> bool:
    if not candidate.merchant or len(candidate.merchant.strip()) < 2:
        return False
    if candidate.amount <= 0:
        return False
    if looks_like_account_or_reference_number(candidate.merchant):
        return False
    if candidate.transaction_type not in {"DEBIT", "CREDIT"}:
        return False
    return True
