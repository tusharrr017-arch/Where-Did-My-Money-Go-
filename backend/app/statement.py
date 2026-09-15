from datetime import date
from typing import Any

from app.ai_service import normalize_transactions_batch
from app.services.ingestion.pipeline import IngestionResult, parse_document
from app.services.duplicates import generate_transaction_fingerprint


ALLOWED_EXTENSIONS = {".pdf", ".csv", ".xlsx", ".docx"}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024


def validate_upload(filename: str | None, contents: bytes) -> str:
    if not filename:
        raise ValueError("Missing filename.")

    from pathlib import Path

    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError(
            "Unsupported file type. Supported formats: PDF, CSV, XLSX, DOCX."
        )

    if not contents:
        raise ValueError("The uploaded file is empty.")

    if len(contents) > MAX_UPLOAD_BYTES:
        raise ValueError("File is too large. Maximum size is 8 MB.")

    return filename


def parse_uploaded_statement(filename: str, contents: bytes) -> list[dict[str, Any]]:
    return parse_uploaded_statement_result(filename, contents).transactions


def parse_uploaded_statement_result(
    filename: str,
    contents: bytes,
) -> IngestionResult:
    result = parse_document(filename, contents)

    for original in result.transactions:
        original["transaction_fingerprint"] = generate_transaction_fingerprint(
            original
        )
        if isinstance(original.get("date"), date):
            original["date"] = original["date"]

    return result


def apply_ai_to_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []

    ai_transactions: list[dict[str, Any]] = []
    batch_size = 10

    for start in range(0, len(rows), batch_size):
        batch = rows[start:start + batch_size]
        ai_batch = normalize_transactions_batch(batch)
        if len(ai_batch) != len(batch):
            raise ValueError(
                f"AI returned {len(ai_batch)} transactions "
                f"for {len(batch)} parsed transactions."
            )
        ai_transactions.extend(ai_batch)

    merged: list[dict[str, Any]] = []
    for original, ai_result in zip(rows, ai_transactions):
        merged.append(
            {
                "date": original["date"],
                "amount": original["amount"],
                "transaction_type": original["transaction_type"],
                "merchant": original["merchant"],
                "description": original.get("description"),
                "transaction_fingerprint": original["transaction_fingerprint"],
                "category": ai_result.get("category", "Other"),
                "economic_type": ai_result.get("economic_type", "OTHER"),
                "confidence": ai_result.get("confidence", 0.0),
                "reason": ai_result.get("reason", ""),
            }
        )
    return merged


def serialize_parsed(row: dict[str, Any]) -> dict[str, Any]:
    value = dict(row)
    if isinstance(value.get("date"), date):
        value["date"] = value["date"].isoformat()
    return value
