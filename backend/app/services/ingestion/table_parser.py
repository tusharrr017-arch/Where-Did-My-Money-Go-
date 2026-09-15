from __future__ import annotations

from app.services.ingestion.amounts import parse_amount_value
from app.services.ingestion.column_mapper import detect_header_row
from app.services.ingestion.dates import parse_date_value
from app.services.ingestion.directions import normalize_transaction_type
from app.services.ingestion.filters import is_summary_or_header_line
from app.services.ingestion.types import TransactionCandidate
from app.services.ingestion.validators import validate_candidate


def parse_table_rows(
    rows: list[list[str]],
    default_year: int | None = None,
) -> tuple[list[TransactionCandidate], int, list[str]]:
    if not rows:
        return [], 0, []

    normalized_rows = [
        [str(cell).strip() if cell is not None else "" for cell in row]
        for row in rows
        if any(str(cell).strip() for cell in row if cell is not None)
    ]
    if not normalized_rows:
        return [], 0, []

    header_info = detect_header_row(normalized_rows)
    if not header_info:
        return [], len(normalized_rows), ["Could not detect table headers."]

    header_index, mapping = header_info
    data_rows = normalized_rows[header_index + 1 :]

    transactions: list[TransactionCandidate] = []
    ignored = header_index + 1
    review: list[str] = []

    for row in data_rows:
        joined = " ".join(cell for cell in row if cell).strip()
        if not joined or is_summary_or_header_line(joined):
            ignored += 1
            continue

        date_value = (
            parse_date_value(row[mapping.date], default_year=default_year)
            if mapping.date is not None and mapping.date < len(row)
            else None
        )
        description = ""
        if mapping.description is not None and mapping.description < len(row):
            description = row[mapping.description]
        merchant = ""
        if mapping.merchant is not None and mapping.merchant < len(row):
            merchant = row[mapping.merchant]
        if not merchant:
            merchant = description

        debit_amount = None
        credit_amount = None
        amount = None
        txn_type = None

        if mapping.debit is not None and mapping.debit < len(row):
            debit_amount = parse_amount_value(row[mapping.debit])
        if mapping.credit is not None and mapping.credit < len(row):
            credit_amount = parse_amount_value(row[mapping.credit])
        if mapping.amount is not None and mapping.amount < len(row):
            amount = parse_amount_value(row[mapping.amount])
        if mapping.txn_type is not None and mapping.txn_type < len(row):
            txn_type = normalize_transaction_type(row[mapping.txn_type])

        if debit_amount and debit_amount > 0:
            amount = debit_amount
            txn_type = txn_type or "DEBIT"
        elif credit_amount and credit_amount > 0:
            amount = credit_amount
            txn_type = txn_type or "CREDIT"
        elif amount is not None:
            txn_type = txn_type or normalize_transaction_type(None, amount)

        if date_value is None or amount is None or not merchant:
            ignored += 1
            review.append(joined)
            continue

        if amount < 0:
            txn_type = txn_type or "DEBIT"
        elif amount > 0 and txn_type is None:
            txn_type = "CREDIT"

        candidate = TransactionCandidate(
            date=date_value,
            merchant=merchant.strip(),
            amount=abs(amount),
            transaction_type=txn_type or "DEBIT",
            description=(description or merchant).strip(),
            source_line=joined,
        )
        if validate_candidate(candidate):
            transactions.append(candidate)
        else:
            ignored += 1
            review.append(joined)

    return transactions, ignored, review
