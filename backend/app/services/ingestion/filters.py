from __future__ import annotations

import re

SKIP_LINE_PATTERNS = (
    r"\bopening balance\b",
    r"\bclosing balance\b",
    r"\bavailable credit\b",
    r"\btotal debits?\b",
    r"\btotal credits?\b",
    r"\bstatement total\b",
    r"\bminimum amount due\b",
    r"\bpayment due date\b",
    r"\bcredit limit\b",
    r"\baccount number\b",
    r"\bcard number\b",
    r"\bcustomer id\b",
    r"\bpage \d+ of \d+\b",
    r"\bstatement period\b",
    r"\bcontinued\b",
    r"\bgrand total\b",
)

SKIP_LINE_RE = re.compile("|".join(SKIP_LINE_PATTERNS), re.IGNORECASE)


def is_summary_or_header_line(text: str) -> bool:
    cleaned = " ".join(text.split()).strip()
    if not cleaned:
        return True
    if SKIP_LINE_RE.search(cleaned):
        return True
    if re.fullmatch(r"[\d\s\-/|]+", cleaned):
        return True
    return False


def looks_like_account_or_reference_number(text: str) -> bool:
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 12 and len(digits) <= 19:
        return True
    return False
