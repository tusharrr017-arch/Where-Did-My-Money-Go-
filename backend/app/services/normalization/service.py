import re
from datetime import datetime


TRANSACTION_PATTERN = re.compile(
    r"^(\d{2}\s+[A-Za-z]{3}\s+\d{2})\s+(.+?)\s+([\d,]+\.\d{2})\s+([CD])$"
)


def parse_statement_transactions(text: str) -> list[dict]:
    transactions = []

    for line in text.splitlines():
        line = line.strip()

        if not line:
            continue

        match = TRANSACTION_PATTERN.match(line)

        if not match:
            continue

        date_text, description, amount_text, transaction_code = match.groups()

        transaction_date = datetime.strptime(
            date_text,
            "%d %b %y"
        ).date()

        amount = float(amount_text.replace(",", ""))

        transaction_type = (
            "DEBIT"
            if transaction_code == "D"
            else "CREDIT"
        )

        transactions.append(
            {
                "date": transaction_date,
                "merchant": description.strip(),
                "amount": amount,
                "transaction_type": transaction_type,
                "description": description.strip(),
            }
        )

    return transactions