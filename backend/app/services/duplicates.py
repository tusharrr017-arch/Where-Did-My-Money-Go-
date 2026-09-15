"""
Deterministic duplicate detection for imported bank transactions.

WHY THE PREVIOUS IMPLEMENTATION FAILED
--------------------------------------
The unique column `transaction_fingerprint` only prevents inserts when the
*hash* already exists. That is not enough if:

1. The fingerprint algorithm changed, but existing rows were only backfilled
   when `transaction_fingerprint` was NULL. Rows that already had an OLD hash
   kept that old hash, so the unique constraint never fired.

2. The hash included raw merchant + description. Those strings are not
   stable financial facts:
   - first import may have stored an AI-normalized merchant
     ("Dmart Avenue Supermarket Ltd")
   - a later import of the same PDF uses the original statement text
     ("UPI-DMART AVENUE SUPERM LTD")
   Those two strings hash differently, so 17 "new" rows were inserted.

3. `create_all()` does not add a UNIQUE constraint to a column that already
   exists in Neon. Application-level checks must be correct even if the
   database constraint is missing.

WHAT COUNTS AS THE SAME TRANSACTION
-----------------------------------
Identity is built ONLY from original statement facts, never from AI output:

- date
- amount (rounded to 2 decimal places)
- transaction_type (DEBIT / CREDIT)
- a canonical merchant token set derived from merchant AND description

AI fields (category, economic_type, confidence, reason, canonical merchant
name) are ignored for identity.

We do NOT use date + amount + debit/credit alone, because two legitimate
payments of ₹100 on the same day to different merchants must both be kept.

Merchant text is canonicalized so formatting variants of the SAME payee
collapse to the same token set, for example:

    "UPI-DMART AVENUE SUPERM LTD"  ==  "Dmart Avenue Supermarket Ltd"
    "UPI-AVENUE FOOD PLAZA PTD"    ==  "Avenue Food Plaza"
    "ASSPL IN"                     ==  "ASSPL"

STRATEGY
--------
1. Fingerprint (unique-constraint safety layer):
   sha256(date | amount | DEBIT/CREDIT | sorted canonical tokens)

2. Application-level skip:
   exact fingerprint match OR same date/amount/type plus overlapping
   merchant tokens (covers remaining AI-shortened names).

3. Intra-file duplicates use the same rules, so the same line twice in
   one PDF is imported once.

4. IntegrityError on insert is treated as a duplicate, not a 500.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable


# Stem length makes "superm" and "supermarket" compare equal without
# treating unrelated merchants as the same.
TOKEN_STEM_LENGTH = 6

# Channel prefixes that appear at the start of Indian bank descriptions.
# These are payment rails, not merchant identity.
CHANNEL_PREFIX_TOKENS = {
    "upi",
    "pos",
    "neft",
    "imps",
    "rtgs",
    "ift",
    "nft",
    "mmt",
    "card",
    "nb",
    "atm",
    "visa",
    "mastercard",
    "mc",
    "rupay",
    "paytm",
    "gpay",
    "googlepay",
    "phonepe",
    "bhim",
    "bharatpe",
    "amazonpay",
}

# Legal / filler words that differ between statement text and AI names.
NOISE_TOKENS = {
    "ltd",
    "limited",
    "pvt",
    "pvtltd",
    "private",
    "pty",
    "ptd",
    "inc",
    "llc",
    "llp",
    "co",
    "com",
    "company",
    "corp",
    "corporation",
    "the",
    "and",
    "of",
    "at",
    "to",
    "for",
    "from",
    "with",
}

# Trailing / extra country codes such as "ASSPL IN".
COUNTRY_TOKENS = {
    "in",
    "uk",
    "us",
    "ae",
    "sg",
    "hk",
    "uae",
}

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def normalize_date(value: object) -> str:
    """Return YYYY-MM-DD regardless of date / datetime / string input."""
    if hasattr(value, "isoformat"):
        return value.isoformat()[:10]
    return str(value or "").strip()[:10]


def normalize_amount(value: object) -> str:
    """Bank amounts are compared at 2 decimal places, never as raw floats."""
    try:
        return f"{round(float(value or 0), 2):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def normalize_transaction_type(value: object) -> str:
    return str(value or "").strip().upper()


def _tokenize(value: object) -> list[str]:
    text = _NON_ALNUM_RE.sub(" ", str(value or "").strip().lower())
    return [token for token in text.split() if token]


def _tokens_from_one_field(value: object) -> list[str]:
    """Canonicalize a single merchant or description string."""
    tokens = _tokenize(value)

    while tokens and tokens[0] in CHANNEL_PREFIX_TOKENS:
        tokens.pop(0)

    cleaned: list[str] = []
    for token in tokens:
        if token in CHANNEL_PREFIX_TOKENS:
            continue
        if token in NOISE_TOKENS:
            continue
        if token in COUNTRY_TOKENS:
            continue
        # Drop UPI/UTR-style reference numbers; keep short numbers that
        # might be part of a trade name (e.g. "cafe 24").
        if token.isdigit() and len(token) >= 4:
            continue
        if len(token) <= 1:
            continue
        cleaned.append(token[:TOKEN_STEM_LENGTH])

    return cleaned


def canonical_merchant_tokens(*values: object) -> frozenset[str]:
    """
    Build a stable merchant identity from one or more statement strings.

    Each field is canonicalized on its own, then the token sets are
    UNIONED. That way a stored AI name ("Dmart Avenue Supermarket Ltd")
    still matches the original statement line
    ("UPI-DMART AVENUE SUPERM LTD"), and a repeated UPI prefix in both
    merchant and description cannot leak into the fingerprint.
    """
    tokens: set[str] = set()
    for value in values:
        tokens.update(_tokens_from_one_field(value))
    return frozenset(tokens)


def identity_key(transaction: dict[str, Any]) -> tuple[str, str, str]:
    """Financial facts only: date, amount, debit/credit."""
    return (
        normalize_date(transaction.get("date")),
        normalize_amount(transaction.get("amount")),
        normalize_transaction_type(transaction.get("transaction_type")),
    )


def merchant_tokens_from_transaction(transaction: dict[str, Any]) -> frozenset[str]:
    return canonical_merchant_tokens(
        transaction.get("merchant"),
        transaction.get("description"),
    )


def generate_transaction_fingerprint(transaction: dict[str, Any]) -> str:
    """
    SHA-256 identity used as the unique-constraint safety layer.

    The hash is 64 hex characters so it still fits the existing
    VARCHAR(64) column. It is computed from original statement facts
    after merchant canonicalization, never from AI output.
    """
    date_value, amount_value, transaction_type = identity_key(transaction)
    tokens = merchant_tokens_from_transaction(transaction)
    token_value = " ".join(sorted(tokens))

    raw = "|".join(
        [
            date_value,
            amount_value,
            transaction_type,
            token_value,
        ]
    )

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def merchants_are_same_transaction(
    left_tokens: frozenset[str],
    right_tokens: frozenset[str],
) -> bool:
    """
    True when two canonical token sets likely name the same payee.

    Equal sets cover formatting variants that the fingerprint already
    unifies. Subset / Jaccard covers leftover cases such as an AI name
    shortened to "Dmart" while the statement still says
    "UPI-DMART AVENUE SUPERM LTD".

    Empty token sets are NOT treated as a match: that would collapse
    every same-day, same-amount, same-type transaction into one row.
    """
    if not left_tokens or not right_tokens:
        return False

    if left_tokens == right_tokens:
        return True

    smaller, larger = (
        (left_tokens, right_tokens)
        if len(left_tokens) <= len(right_tokens)
        else (right_tokens, left_tokens)
    )

    if smaller <= larger:
        return any(len(token) >= 4 for token in smaller)

    intersection = left_tokens & right_tokens
    union = left_tokens | right_tokens
    if not union:
        return False

    return (
        len(intersection) / len(union) >= 0.5
        and any(len(token) >= 4 for token in intersection)
    )


def is_duplicate_transaction(
    incoming: dict[str, Any],
    existing: dict[str, Any],
) -> bool:
    """Exact fingerprint or same financial facts + same canonical payee."""
    incoming_fp = incoming.get("transaction_fingerprint") or generate_transaction_fingerprint(
        incoming
    )
    existing_fp = existing.get("transaction_fingerprint") or generate_transaction_fingerprint(
        existing
    )
    if incoming_fp == existing_fp:
        return True

    if identity_key(incoming) != identity_key(existing):
        return False

    return merchants_are_same_transaction(
        merchant_tokens_from_transaction(incoming),
        merchant_tokens_from_transaction(existing),
    )


def row_to_identity(row: Any) -> dict[str, Any]:
    """Map a SQLAlchemy Transaction row to the identity dict."""
    return {
        "date": row.date,
        "amount": row.amount,
        "transaction_type": row.transaction_type,
        "merchant": row.merchant,
        "description": row.description,
        "transaction_fingerprint": row.transaction_fingerprint,
    }


def refresh_stored_fingerprints(db: Any, rows: Iterable[Any]) -> None:
    """
    Recompute fingerprints for EVERY stored row using the current algorithm.

    Filling only NULL fingerprints leaves old hashes in place, which is
    exactly how re-uploading the same PDF produced new inserts.

    Historical duplicates (two stored rows that now hash identically) are
    not deleted. The earliest row keeps the canonical fingerprint; later
    rows get NULL so they cannot violate the unique constraint. They are
    still detected as duplicates by merchant-token matching until the
    user cleans them manually.

    Updates are flushed in two phases (NULL, then new hash) so a live
    UNIQUE constraint cannot collide with a fingerprint another row
    still holds.
    """
    rows = list(rows)
    assigned: dict[str, int] = {}
    planned: list[tuple[Any, str | None]] = []

    for row in sorted(rows, key=lambda item: item.id):
        new_fingerprint = generate_transaction_fingerprint(row_to_identity(row))

        if new_fingerprint in assigned:
            # Extra historical copy of a transaction we already assigned.
            planned.append((row, None))
            continue

        assigned[new_fingerprint] = row.id
        if row.transaction_fingerprint != new_fingerprint:
            planned.append((row, new_fingerprint))

    if not planned:
        return

    for row, _fingerprint in planned:
        row.transaction_fingerprint = None
    db.flush()

    for row, fingerprint in planned:
        if fingerprint is None:
            continue
        row.transaction_fingerprint = fingerprint
    db.flush()


def partition_new_and_duplicate_transactions(
    incoming_transactions: list[dict[str, Any]],
    existing_rows: Iterable[Any],
) -> tuple[list[dict[str, Any]], int]:
    """
    Split one import batch into rows to insert vs rows to skip.

    existing_rows should already have refreshed fingerprints.
    """
    existing_identities = [row_to_identity(row) for row in existing_rows]
    existing_fingerprints = {
        identity["transaction_fingerprint"]
        for identity in existing_identities
        if identity["transaction_fingerprint"]
    }

    new_transactions: list[dict[str, Any]] = []
    accepted_identities: list[dict[str, Any]] = []
    seen_fingerprints: set[str] = set()
    duplicate_count = 0

    for transaction in incoming_transactions:
        fingerprint = transaction["transaction_fingerprint"]

        if fingerprint in existing_fingerprints or fingerprint in seen_fingerprints:
            duplicate_count += 1
            continue

        if any(
            is_duplicate_transaction(transaction, existing)
            for existing in existing_identities
        ) or any(
            is_duplicate_transaction(transaction, accepted)
            for accepted in accepted_identities
        ):
            duplicate_count += 1
            continue

        seen_fingerprints.add(fingerprint)
        accepted_identities.append(transaction)
        new_transactions.append(transaction)

    return new_transactions, duplicate_count
