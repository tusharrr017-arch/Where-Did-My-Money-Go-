from __future__ import annotations

import re

from app.services.ingestion.amounts import extract_trailing_amount, parse_amount_value
from app.services.ingestion.column_mapper import detect_header_row
from app.services.ingestion.dates import extract_leading_date, infer_statement_year, parse_date_value
from app.services.ingestion.directions import (
    CREDIT_TOKENS,
    DEBIT_TOKENS,
    extract_trailing_direction,
    normalize_transaction_type,
)
from app.services.ingestion.filters import is_summary_or_header_line
from app.services.ingestion.table_parser import parse_table_rows
from app.services.ingestion.types import TransactionCandidate
from app.services.ingestion.validators import validate_candidate

SINGLE_LINE_PATTERNS = (
    re.compile(
        r"^(\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4})\s+(.+?)\s+(?:₹|INR\s*)?([\d,]+\.\d{2})\s+([CD])$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+\|\s*(.+?)\s+\|\s*(-?[\d,]+\.\d{2})\s*\|\s*([A-Za-z/]+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+(.+?)\s+(-?[\d,]+\.\d{2})$",
        re.IGNORECASE,
    ),
)


def parse_text_lines(
    lines: list[str],
    default_year: int | None = None,
) -> tuple[list[TransactionCandidate], int, list[str]]:
    if not lines:
        return [], 0, []

    statement_year = default_year or infer_statement_year("\n".join(lines))
    table_rows = _extract_text_table(lines)
    if table_rows:
        return parse_table_rows(table_rows, default_year=statement_year)

    transactions: list[TransactionCandidate] = []
    ignored = 0
    review: list[str] = []

    index = 0
    while index < len(lines):
        line = lines[index].strip()
        index += 1
        if not line or is_summary_or_header_line(line):
            ignored += 1
            continue

        single = _parse_single_line(line, statement_year)
        if single:
            transactions.append(single)
            continue

        block_lines = [line]
        while index < len(lines):
            peek = lines[index].strip()
            if not peek:
                index += 1
                break
            if _line_starts_transaction(peek, statement_year):
                break
            block_lines.append(peek)
            index += 1

        candidate = _parse_multiline_block(block_lines, statement_year)
        if candidate:
            transactions.append(candidate)
        else:
            ignored += len(block_lines)
            review.append(" | ".join(block_lines))

    return transactions, ignored, review


def _extract_text_table(lines: list[str]) -> list[list[str]] | None:
    table_lines = []
    for line in lines:
        if "|" in line:
            cells = [cell.strip() for cell in line.split("|")]
            if len(cells) >= 3:
                table_lines.append(cells)
        elif re.search(r"\s{2,}", line):
            cells = [cell.strip() for cell in re.split(r"\s{2,}", line.strip()) if cell.strip()]
            if len(cells) >= 3:
                table_lines.append(cells)

    if len(table_lines) < 2:
        return None

    header_info = detect_header_row(table_lines)
    if not header_info:
        return None
    return table_lines


def _parse_single_line(line: str, default_year: int | None) -> TransactionCandidate | None:
    for pattern in SINGLE_LINE_PATTERNS:
        match = pattern.match(line)
        if not match:
            continue
        groups = match.groups()
        date_value = parse_date_value(groups[0], default_year=default_year)
        if not date_value:
            continue
        if len(groups) == 4:
            description = groups[1].strip()
            amount = parse_amount_value(groups[2])
            txn_type = normalize_transaction_type(groups[3], amount)
        else:
            description = groups[1].strip()
            amount = parse_amount_value(groups[2])
            txn_type = normalize_transaction_type(None, amount)
        if amount is None:
            return None
        candidate = TransactionCandidate(
            date=date_value,
            merchant=description,
            amount=abs(amount),
            transaction_type=txn_type or ("DEBIT" if amount < 0 else "CREDIT"),
            description=description,
            source_line=line,
        )
        if validate_candidate(candidate):
            return candidate
    return None


def _line_starts_transaction(line: str, default_year: int | None) -> bool:
    date_value, _ = extract_leading_date(line, default_year=default_year)
    return date_value is not None


def _parse_multiline_block(
    block_lines: list[str],
    default_year: int | None,
) -> TransactionCandidate | None:
    first_line = block_lines[0]
    date_value, remainder = extract_leading_date(first_line, default_year=default_year)
    if date_value is None:
        return None

    description_parts = []
    if remainder:
        description_parts.append(remainder)

    amount = None
    txn_type = None

    for extra_line in block_lines[1:]:
        direction, cleaned = extract_trailing_direction(extra_line)
        if direction and not cleaned:
            txn_type = direction
            continue

        line_amount, line_remainder = extract_trailing_amount(cleaned or extra_line)
        if line_amount is not None:
            amount = line_amount
            txn_type = direction or txn_type
            if line_remainder:
                description_parts.append(line_remainder)
        elif cleaned:
            token = cleaned.strip().lower()
            if token in DEBIT_TOKENS:
                txn_type = "DEBIT"
            elif token in CREDIT_TOKENS:
                txn_type = "CREDIT"
            else:
                description_parts.append(cleaned)

    if amount is None and remainder:
        amount, desc_remainder = extract_trailing_amount(remainder)
        if desc_remainder:
            description_parts.insert(0, desc_remainder)
        txn_type = extract_trailing_direction(remainder)[0] or normalize_transaction_type(None, amount)

    description = " ".join(part for part in description_parts if part).strip()
    merchant = description
    if amount is None or not merchant:
        return None

    if txn_type is None:
        txn_type = normalize_transaction_type(None, amount)

    candidate = TransactionCandidate(
        date=date_value,
        merchant=merchant,
        amount=abs(amount),
        transaction_type=txn_type or ("DEBIT" if amount < 0 else "CREDIT"),
        description=description,
        source_line=" | ".join(block_lines),
    )
    if validate_candidate(candidate):
        return candidate
    return None
