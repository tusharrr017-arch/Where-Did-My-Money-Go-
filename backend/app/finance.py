from datetime import date
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Transaction

NOT_SPENDING = {"PAYMENT", "TRANSFER", "REFUND"}
SPENDING_TYPES = {"PURCHASE", "FEE", "INTEREST", "OTHER"}


def month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start, end


def previous_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def owned(user_id: int):
    return Transaction.user_id == user_id


def spending_sql():
    return (
        Transaction.transaction_type == "DEBIT",
        or_(
            Transaction.economic_type.in_(list(SPENDING_TYPES)),
            Transaction.economic_type.is_(None),
        ),
        or_(
            Transaction.economic_type.is_(None),
            Transaction.economic_type.notin_(list(NOT_SPENDING)),
        ),
    )


def is_spending(row: Any) -> bool:
    if isinstance(row, dict):
        transaction_type = row.get("transaction_type")
        economic_type = row.get("economic_type")
        amount = row.get("amount")
    else:
        transaction_type = row.transaction_type
        economic_type = row.economic_type
        amount = row.amount

    if transaction_type != "DEBIT":
        return False
    if amount is None:
        return False
    return (economic_type or "OTHER") not in NOT_SPENDING


def load_user_transactions(
    db: Session,
    user_id: int,
    start: date | None = None,
    end: date | None = None,
) -> list[Transaction]:
    query = select(Transaction).where(owned(user_id))

    if start is not None:
        query = query.where(Transaction.date >= start)
    if end is not None:
        query = query.where(Transaction.date < end)

    return list(
        db.execute(
            query.order_by(Transaction.date.desc(), Transaction.id.desc())
        ).scalars().all()
    )


def sum_spending(rows: list[Any]) -> float:
    return round(
        sum(float(row.amount if not isinstance(row, dict) else row["amount"]) for row in rows if is_spending(row)),
        2,
    )


def build_summary(db: Session, user_id: int, year: int, month: int) -> dict:
    start, end = month_bounds(year, month)
    prev_year, prev_month = previous_month(year, month)
    prev_start, prev_end = month_bounds(prev_year, prev_month)
    filters = spending_sql()

    selected = db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            owned(user_id),
            Transaction.date >= start,
            Transaction.date < end,
            *filters,
        )
    ).scalar()

    previous = db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            owned(user_id),
            Transaction.date >= prev_start,
            Transaction.date < prev_end,
            *filters,
        )
    ).scalar()

    category_rows = db.execute(
        select(
            Transaction.category,
            func.sum(Transaction.amount).label("amount"),
        )
        .where(
            owned(user_id),
            Transaction.date >= start,
            Transaction.date < end,
            *filters,
        )
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
    ).all()

    category_breakdown = [
        {"category": category, "amount": float(amount)}
        for category, amount in category_rows
    ]

    largest = db.execute(
        select(Transaction)
        .where(
            owned(user_id),
            Transaction.date >= start,
            Transaction.date < end,
            *filters,
        )
        .order_by(Transaction.amount.desc())
        .limit(1)
    ).scalar_one_or_none()

    return {
        "year": year,
        "month": month,
        "selected_month_spending": float(selected or 0),
        "previous_month_spending": float(previous or 0),
        "category_breakdown": category_breakdown,
        "top_category": category_breakdown[0] if category_breakdown else None,
        "largest_transaction": serialize_transaction(largest) if largest else None,
    }


def build_cashflow(db: Session, user_id: int, year: int, month: int) -> dict:
    start, end = month_bounds(year, month)
    rows = load_user_transactions(db, user_id, start, end)

    spending = sum_spending(rows)
    income = round(
        sum(
            float(t.amount)
            for t in rows
            if t.transaction_type == "CREDIT" and t.economic_type == "INCOME"
        ),
        2,
    )
    refunds = round(
        sum(
            float(t.amount)
            for t in rows
            if t.transaction_type == "CREDIT" and t.economic_type == "REFUND"
        ),
        2,
    )
    transfers_in = round(
        sum(
            float(t.amount)
            for t in rows
            if t.transaction_type == "CREDIT" and t.economic_type == "TRANSFER"
        ),
        2,
    )
    transfers_out = round(
        sum(
            float(t.amount)
            for t in rows
            if t.transaction_type == "DEBIT" and t.economic_type == "TRANSFER"
        ),
        2,
    )

    return {
        "year": year,
        "month": month,
        "money_in": income,
        "refunds": refunds,
        "money_out": spending,
        "transfers_in": transfers_in,
        "transfers_out": transfers_out,
        "net_cash_flow": round(income + refunds - spending, 2),
    }


def serialize_transaction(row: Transaction) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "merchant": row.merchant,
        "amount": float(row.amount),
        "category": row.category,
        "transaction_type": row.transaction_type,
        "economic_type": row.economic_type,
        "date": str(row.date),
        "description": row.description,
        "category_confidence": row.category_confidence,
        "category_reason": row.category_reason,
        "source_file": row.source_file,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def monthly_spending(db: Session, user_id: int, year: int, month: int) -> dict:
    start, end = month_bounds(year, month)
    rows = [row for row in load_user_transactions(db, user_id, start, end) if is_spending(row)]
    return {
        "year": year,
        "month": month,
        "total": sum_spending(rows),
        "count": len(rows),
    }


def category_spending(
    db: Session,
    user_id: int,
    category: str,
    year: int | None,
    month: int | None,
) -> dict:
    query = select(Transaction).where(
        owned(user_id),
        func.lower(Transaction.category) == category.lower(),
        *spending_sql(),
    )
    if year and month:
        start, end = month_bounds(year, month)
        query = query.where(Transaction.date >= start, Transaction.date < end)

    rows = list(db.execute(query).scalars().all())
    return {
        "category": category,
        "year": year,
        "month": month,
        "total": round(sum(float(row.amount) for row in rows), 2),
        "count": len(rows),
    }


def merchant_spending(
    db: Session,
    user_id: int,
    merchant: str,
    year: int | None,
    month: int | None,
) -> dict:
    pattern = f"%{merchant.lower()}%"
    query = select(Transaction).where(
        owned(user_id),
        or_(
            func.lower(Transaction.merchant).like(pattern),
            func.lower(func.coalesce(Transaction.description, "")).like(pattern),
        ),
        *spending_sql(),
    )
    if year and month:
        start, end = month_bounds(year, month)
        query = query.where(Transaction.date >= start, Transaction.date < end)

    rows = list(db.execute(query).scalars().all())
    return {
        "merchant": merchant,
        "year": year,
        "month": month,
        "total": round(sum(float(row.amount) for row in rows), 2),
        "count": len(rows),
        "transactions": [serialize_transaction(row) for row in rows[:10]],
    }


def largest_transaction(
    db: Session,
    user_id: int,
    year: int | None,
    month: int | None,
    category: str | None = None,
) -> dict:
    query = select(Transaction).where(owned(user_id), *spending_sql())
    if year and month:
        start, end = month_bounds(year, month)
        query = query.where(Transaction.date >= start, Transaction.date < end)
    if category:
        query = query.where(func.lower(Transaction.category) == category.lower())

    row = db.execute(query.order_by(Transaction.amount.desc()).limit(1)).scalar_one_or_none()
    return {
        "transaction": serialize_transaction(row) if row else None,
    }


def top_transactions(
    db: Session,
    user_id: int,
    limit: int = 5,
    year: int | None = None,
    month: int | None = None,
    category: str | None = None,
) -> dict:
    query = select(Transaction).where(owned(user_id), *spending_sql())
    if year and month:
        start, end = month_bounds(year, month)
        query = query.where(Transaction.date >= start, Transaction.date < end)
    if category:
        query = query.where(func.lower(Transaction.category) == category.lower())

    rows = list(
        db.execute(
            query.order_by(Transaction.amount.desc()).limit(max(1, min(limit, 20)))
        ).scalars().all()
    )
    return {"transactions": [serialize_transaction(row) for row in rows]}


def month_comparison(
    db: Session,
    user_id: int,
    year_a: int,
    month_a: int,
    year_b: int,
    month_b: int,
) -> dict:
    first = monthly_spending(db, user_id, year_a, month_a)
    second = monthly_spending(db, user_id, year_b, month_b)
    return {
        "first": first,
        "second": second,
        "difference": round(second["total"] - first["total"], 2),
    }


def transaction_search(
    db: Session,
    user_id: int,
    query_text: str,
) -> dict:
    pattern = f"%{query_text.lower()}%"
    rows = list(
        db.execute(
            select(Transaction)
            .where(
                owned(user_id),
                or_(
                    func.lower(Transaction.merchant).like(pattern),
                    func.lower(func.coalesce(Transaction.description, "")).like(pattern),
                    func.lower(Transaction.category).like(pattern),
                ),
            )
            .order_by(Transaction.date.desc())
            .limit(20)
        ).scalars().all()
    )
    return {"transactions": [serialize_transaction(row) for row in rows]}


def general_summary(db: Session, user_id: int) -> dict:
    rows = load_user_transactions(db, user_id)
    if not rows:
        return {"count": 0, "total_spending": 0, "range": None}

    spending_rows = [row for row in rows if is_spending(row)]
    dates = [row.date for row in rows]
    return {
        "count": len(rows),
        "total_spending": round(sum(float(row.amount) for row in spending_rows), 2),
        "first_date": str(min(dates)),
        "last_date": str(max(dates)),
    }


def build_fallback_insights(rows: list[Any], year: int, month: int) -> dict:
    spending_rows = [row for row in rows if is_spending(row)]
    total_spending = sum_spending(rows)
    income = round(
        sum(
            float(row.amount if not isinstance(row, dict) else row["amount"])
            for row in rows
            if (row.transaction_type if not isinstance(row, dict) else row["transaction_type"])
            == "CREDIT"
            and (row.economic_type if not isinstance(row, dict) else row["economic_type"])
            == "INCOME"
        ),
        2,
    )

    category_totals: dict[str, float] = {}
    for row in spending_rows:
        category = row.category if not isinstance(row, dict) else row["category"]
        amount = float(row.amount if not isinstance(row, dict) else row["amount"])
        category_totals[category or "Other"] = category_totals.get(category or "Other", 0) + amount

    top_category = max(category_totals, key=category_totals.get) if category_totals else None
    insights: list[str] = []
    if top_category:
        insights.append(
            f"Your top spending category was {top_category} "
            f"at ₹{category_totals[top_category]:.0f}."
        )
    if income > 0:
        insights.append(f"Recorded income this month: ₹{income:.0f}.")
    if len(spending_rows) > 0:
        avg = total_spending / len(spending_rows)
        insights.append(
            f"You logged {len(spending_rows)} spending transactions "
            f"with an average of ₹{avg:.0f}."
        )
    if not insights:
        insights.append("Add more transactions to unlock richer spending insights.")

    summary = (
        f"In {year}-{month:02d}, you had {len(rows)} transactions with "
        f"₹{total_spending:.0f} in tracked spending."
    )
    recommendation = (
        f"Review {top_category} spending first."
        if top_category
        else "Import a full statement to get personalized recommendations."
    )

    return {
        "summary": summary,
        "insights": insights[:3],
        "recommendation": recommendation,
        "ai_fallback": True,
    }


def current_month_from_data(db: Session, user_id: int) -> tuple[int, int]:
    latest = db.execute(
        select(Transaction.date)
        .where(owned(user_id))
        .order_by(Transaction.date.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest is None:
        today = date.today()
        return today.year, today.month
    return latest.year, latest.month
