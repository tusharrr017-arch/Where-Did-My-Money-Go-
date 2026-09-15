from __future__ import annotations

import re

AMOUNT_RE = re.compile(
    r"(?P<sign>-)?\s*(?:₹|INR\s*)?"
    r"(?P<amount>\d{1,3}(?:,\d{2,3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"
    r"\s*$",
    re.IGNORECASE,
)

INLINE_AMOUNT_RE = re.compile(
    r"(?P<sign>-)?\s*(?:₹|INR\s*)?"
    r"(?P<amount>\d{1,3}(?:,\d{2,3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"
)


def parse_amount_value(value: str) -> float | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    if re.fullmatch(r"\d{10,}", re.sub(r"\D", "", cleaned)):
        return None

    match = AMOUNT_RE.search(cleaned) or INLINE_AMOUNT_RE.search(cleaned)
    if not match:
        return None

    amount_text = match.group("amount").replace(",", "")
    try:
        amount = float(amount_text)
    except ValueError:
        return None

    if amount == 0:
        return None
    if match.group("sign") == "-" or cleaned.strip().startswith("-"):
        return -abs(amount)
    return abs(amount)


def extract_trailing_amount(text: str) -> tuple[float | None, str]:
    parts = re.split(r"\s+\|\s+|\t+|\s{2,}", text.strip())
    for index in range(len(parts) - 1, -1, -1):
        amount = parse_amount_value(parts[index])
        if amount is not None:
            remainder_parts = parts[:index] + parts[index + 1 :]
            remainder = " ".join(part for part in remainder_parts if part).strip()
            return amount, remainder
    match = INLINE_AMOUNT_RE.search(text)
    if match:
        amount = parse_amount_value(match.group(0))
        remainder = (text[: match.start()] + text[match.end() :]).strip(" |-")
        return amount, remainder
    return None, text
