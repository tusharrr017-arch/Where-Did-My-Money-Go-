from pathlib import Path

from app.services.ingestion.extractors import extract_structured


def extract_document(filename: str, contents: bytes) -> str:
    extracted = extract_structured(filename, contents)
    if extracted.table_rows:
        return "\n".join(" | ".join(row) for row in extracted.table_rows)
    return "\n".join(extracted.text_lines)