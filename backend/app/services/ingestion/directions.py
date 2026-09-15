from __future__ import annotations

import re

DEBIT_TOKENS = {
    "d",
    "dr",
    "debit",
    "withdrawal",
    "withdraw",
    "paid",
    "out",
}
CREDIT_TOKENS = {
    "c",
    "cr",
    "credit",
    "deposit",
    "received",
    "in",
}


def normalize_transaction_type(
    raw_type: str | None,
    amount: float | None = None,
) -> str | None:
    if raw_type:
        token = raw_type.strip().lower()
        if token in DEBIT_TOKENS:
            return "DEBIT"
        if token in CREDIT_TOKENS:
            return "CREDIT"
        if token in {"debit", "credit"}:
            return token.upper()

    if amount is None:
        return None
    if amount < 0:
        return "DEBIT"
    if amount > 0:
        return "CREDIT"
    return None


def extract_trailing_direction(text: str) -> tuple[str | None, str]:
    cleaned = text.strip()
    match = re.search(r"\b([A-Za-z/]+)\s*$", cleaned)
    if not match:
        return None, cleaned
    token = match.group(1).lower()
    if token in DEBIT_TOKENS or token in CREDIT_TOKENS:
        remainder = cleaned[: match.start()].strip(" |-")
        return normalize_transaction_type(token), remainder
    return None, cleaned
