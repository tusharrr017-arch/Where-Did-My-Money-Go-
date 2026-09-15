from __future__ import annotations

from app.services.ingestion.extractors import extract_structured
from app.services.ingestion.table_parser import parse_table_rows
from app.services.ingestion.text_parser import parse_text_lines
from app.services.ingestion.types import IngestionResult
from app.services.ingestion.validators import candidate_to_dict


def parse_document(filename: str, contents: bytes) -> IngestionResult:
    extracted = extract_structured(filename, contents)
    default_year = extracted.statement_year

    if extracted.file_type in {"csv", "xlsx"} and extracted.table_rows:
        candidates, ignored, review = parse_table_rows(
            extracted.table_rows,
            default_year=default_year,
        )
        parser = f"table-{extracted.file_type}"
    elif extracted.table_rows and extracted.file_type == "docx":
        candidates, ignored, review = parse_table_rows(
            extracted.table_rows,
            default_year=default_year,
        )
        if not candidates:
            candidates, ignored, review = parse_text_lines(
                extracted.text_lines,
                default_year=default_year,
            )
            parser = "text-docx"
        else:
            parser = "table-docx"
    else:
        candidates, ignored, review = parse_text_lines(
            extracted.text_lines,
            default_year=default_year,
        )
        parser = f"text-{extracted.file_type}"

    transactions = [candidate_to_dict(candidate) for candidate in candidates]
    return IngestionResult(
        transactions=transactions,
        detected=len(transactions),
        ignored=ignored,
        review=review[:25],
        parser=parser,
    )
