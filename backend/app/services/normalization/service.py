from __future__ import annotations

from app.services.ingestion.pipeline import parse_document
from app.services.ingestion.text_parser import parse_text_lines
from app.services.ingestion.validators import candidate_to_dict


def parse_statement_transactions(text: str) -> list[dict]:
    candidates, _, _ = parse_text_lines(text.splitlines())
    return [candidate_to_dict(candidate) for candidate in candidates]


def parse_statement_file(filename: str, contents: bytes) -> dict:
    result = parse_document(filename, contents)
    return {
        "transactions": result.transactions,
        "detected": result.detected,
        "ignored": result.ignored,
        "review": result.review,
        "parser": result.parser,
    }
