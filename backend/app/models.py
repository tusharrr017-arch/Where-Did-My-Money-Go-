from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255)
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )


class Transaction(Base):
    __tablename__ = "transactions"

    # Fingerprints are unique per user, not globally, so two people
    # can import the same merchant/amount/date without colliding.
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "transaction_fingerprint",
            name="uq_user_fingerprint",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    merchant: Mapped[str] = mapped_column(
        String(255)
    )

    amount: Mapped[float] = mapped_column(
        Float
    )

    category: Mapped[str] = mapped_column(
        String(100)
    )

    # Bank transaction type
    # DEBIT / CREDIT
    transaction_type: Mapped[str] = mapped_column(
        String(30)
    )

    # Economic meaning of transaction
    # PURCHASE / PAYMENT / REFUND / TRANSFER /
    # FEE / INTEREST / INCOME / OTHER
    economic_type: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True
    )

    date: Mapped[date] = mapped_column(
        Date
    )

    description: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True
    )

    category_confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True
    )

    category_reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True
    )

    source_file: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    # Deterministic duplicate identity (sha256 hex, 64 chars).
    transaction_fingerprint: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )
