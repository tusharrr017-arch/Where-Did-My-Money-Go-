from __future__ import annotations

import re
from datetime import date, datetime

DATE_PATTERNS = (
    ("%d %b %y", re.compile(r"\b(\d{1,2}\s+[A-Za-z]{3}\s+\d{2})\b")),
    ("%d %b %Y", re.compile(r"\b(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\b")),
    ("%d/%m/%Y", re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")),
    ("%d-%m-%Y", re.compile(r"\b(\d{1,2}-\d{1,2}-\d{4})\b")),
    ("%d/%m/%y", re.compile(r"\b(\d{1,2}/\d{1,2}/\d{2})\b")),
    ("%d-%m-%y", re.compile(r"\b(\d{1,2}-\d{1,2}-\d{2})\b")),
    ("%Y-%m-%d", re.compile(r"\b(\d{4}-\d{1,2}-\d{1,2})\b")),
    ("%Y/%m/%d", re.compile(r"\b(\d{4}/\d{1,2}/\d{1,2})\b")),
)

STATEMENT_YEAR_RE = re.compile(
    r"\b(?:statement period|period|from|between)\b.*?(\d{4})",
    re.IGNORECASE,
)


def infer_statement_year(text: str) -> int | None:
    match = STATEMENT_YEAR_RE.search(text)
    if match:
        return int(match.group(1))
    years = re.findall(r"\b(20\d{2})\b", text)
    if years:
        return int(years[-1])
    return None


def parse_date_value(value: str, default_year: int | None = None) -> date | None:
    cleaned = value.strip()
    if not cleaned:
        return None

    for pattern, regex in DATE_PATTERNS:
        match = regex.search(cleaned)
        if not match:
            continue
        token = match.group(1)
        try:
            parsed = datetime.strptime(token, pattern).date()
        except ValueError:
            continue
        if parsed.year < 100 and default_year:
            century = default_year // 100
            parsed = parsed.replace(year=century * 100 + parsed.year)
        return parsed

    return None


def extract_leading_date(line: str, default_year: int | None = None) -> tuple[date | None, str]:
    for _, regex in DATE_PATTERNS:
        match = regex.match(line.strip())
        if not match:
            continue
        parsed = parse_date_value(match.group(1), default_year=default_year)
        if parsed:
            remainder = line[match.end():].strip(" |-")
            return parsed, remainder
    return None, line
