from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.services.duplicates import (
    generate_transaction_fingerprint,
    partition_new_and_duplicate_transactions,
    refresh_stored_fingerprints,
)
from app.statement import apply_ai_to_rows


def _as_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def save_transactions_for_user(
    db: Session,
    user_id: int,
    incoming: list[dict[str, Any]],
    source_file: str | None,
    already_normalized: bool,
) -> tuple[int, int]:
    if not incoming:
        return 0, 0

    for row in incoming:
        if not row.get("transaction_fingerprint"):
            row["transaction_fingerprint"] = generate_transaction_fingerprint(row)
        row["date"] = _as_date(row.get("date"))

    existing = list(
        db.execute(
            select(models.Transaction)
            .where(models.Transaction.user_id == user_id)
            .order_by(models.Transaction.id)
        ).scalars().all()
    )

    try:
        with db.begin_nested():
            refresh_stored_fingerprints(db, existing)
    except IntegrityError:
        db.expire_all()
        existing = list(
            db.execute(
                select(models.Transaction)
                .where(models.Transaction.user_id == user_id)
                .order_by(models.Transaction.id)
            ).scalars().all()
        )

    new_rows, duplicate_count = partition_new_and_duplicate_transactions(
        incoming,
        existing,
    )

    if not new_rows:
        db.commit()
        return 0, duplicate_count

    if already_normalized:
        rows_to_insert = new_rows
    else:
        rows_to_insert = apply_ai_to_rows(new_rows)

    pending = [
        row["transaction_fingerprint"]
        for row in rows_to_insert
        if row.get("transaction_fingerprint")
    ]

    already_inserted = set()
    if pending:
        already_inserted = set(
            db.execute(
                select(models.Transaction.transaction_fingerprint).where(
                    models.Transaction.user_id == user_id,
                    models.Transaction.transaction_fingerprint.in_(pending),
                )
            ).scalars().all()
        )
        already_inserted.discard(None)

    imported_count = 0

    for row in rows_to_insert:
        fingerprint = row.get("transaction_fingerprint")
        if fingerprint in already_inserted:
            duplicate_count += 1
            continue

        db_transaction = models.Transaction(
            user_id=user_id,
            merchant=row["merchant"],
            amount=row["amount"],
            category=row.get("category") or "Other",
            transaction_type=row["transaction_type"],
            economic_type=row.get("economic_type"),
            date=_as_date(row["date"]),
            description=row.get("description"),
            category_confidence=row.get("confidence") or row.get("category_confidence"),
            category_reason=row.get("reason") or row.get("category_reason"),
            source_file=source_file or row.get("source_file"),
            transaction_fingerprint=fingerprint,
        )

        try:
            with db.begin_nested():
                db.add(db_transaction)
                db.flush()
        except IntegrityError:
            duplicate_count += 1
            continue

        if fingerprint:
            already_inserted.add(fingerprint)
        imported_count += 1

    db.commit()
    return imported_count, duplicate_count
