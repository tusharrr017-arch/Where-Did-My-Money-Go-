from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class ExtractedDocument:
    file_type: str
    text_lines: list[str] = field(default_factory=list)
    table_rows: list[list[str]] = field(default_factory=list)
    statement_year: int | None = None


@dataclass
class TransactionCandidate:
    date: date
    merchant: str
    amount: float
    transaction_type: str
    description: str
    source_line: str = ""


@dataclass
class IngestionResult:
    transactions: list[dict[str, Any]]
    detected: int = 0
    ignored: int = 0
    review: list[str] = field(default_factory=list)
    parser: str = "adaptive"
