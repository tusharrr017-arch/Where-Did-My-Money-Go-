from __future__ import annotations

from dataclasses import dataclass

DATE_HEADERS = {
    "date",
    "transaction date",
    "txn date",
    "posting date",
    "value date",
    "trans date",
}
DESCRIPTION_HEADERS = {
    "description",
    "narration",
    "particulars",
    "merchant",
    "payee",
    "transaction details",
    "reference",
    "details",
    "remarks",
}
MERCHANT_HEADERS = {
    "merchant",
    "payee",
    "beneficiary",
}
AMOUNT_HEADERS = {
    "amount",
    "transaction amount",
    "value",
    "txn amount",
}
DEBIT_HEADERS = {
    "debit",
    "debit amount",
    "withdrawal",
    "withdrawals",
    "withdraw",
    "dr",
}
CREDIT_HEADERS = {
    "credit",
    "credit amount",
    "deposit",
    "deposits",
    "cr",
}
TYPE_HEADERS = {
    "type",
    "transaction type",
    "transaction_type",
    "dr/cr",
    "debit/credit",
}


@dataclass
class ColumnMapping:
    date: int | None = None
    description: int | None = None
    merchant: int | None = None
    amount: int | None = None
    debit: int | None = None
    credit: int | None = None
    txn_type: int | None = None


def normalize_header(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def detect_header_row(rows: list[list[str]]) -> tuple[int, ColumnMapping] | None:
    for index, row in enumerate(rows[:20]):
        headers = [normalize_header(cell) for cell in row]
        if not any(headers):
            continue
        mapping = map_headers(headers)
        if mapping.date is not None and (
            mapping.description is not None
            or mapping.merchant is not None
            or mapping.amount is not None
            or mapping.debit is not None
            or mapping.credit is not None
        ):
            return index, mapping
    return None


def map_headers(headers: list[str]) -> ColumnMapping:
    mapping = ColumnMapping()
    for index, header in enumerate(headers):
        if not header:
            continue
        if header in DATE_HEADERS and mapping.date is None:
            mapping.date = index
        elif header in MERCHANT_HEADERS and mapping.merchant is None:
            mapping.merchant = index
        elif header in DESCRIPTION_HEADERS and mapping.description is None:
            mapping.description = index
        elif header in AMOUNT_HEADERS and mapping.amount is None:
            mapping.amount = index
        elif header in DEBIT_HEADERS and mapping.debit is None:
            mapping.debit = index
        elif header in CREDIT_HEADERS and mapping.credit is None:
            mapping.credit = index
        elif header in TYPE_HEADERS and mapping.txn_type is None:
            mapping.txn_type = index
    return mapping
