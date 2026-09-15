import io
import unittest
from datetime import date

from openpyxl import Workbook

from app.services.duplicates import generate_transaction_fingerprint
from app.services.ingestion.pipeline import parse_document
from app.services.ingestion.text_parser import parse_text_lines


class IngestionParserTests(unittest.TestCase):
    def _parse_text(self, text: str):
        candidates, ignored, review = parse_text_lines(text.splitlines(), default_year=2026)
        return candidates, ignored, review

    def test_sbi_single_line_format(self):
        candidates, ignored, _ = self._parse_text("05 Jul 26 UPI-SWIGGY 290.00 D")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].merchant, "UPI-SWIGGY")
        self.assertEqual(candidates[0].amount, 290.0)
        self.assertEqual(candidates[0].transaction_type, "DEBIT")
        self.assertEqual(ignored, 0)

    def test_multiline_pdf_format(self):
        text = "\n".join(
            [
                "05 Jul 26",
                "UPI-SWIGGY",
                "290.00",
                "Debit",
            ]
        )
        candidates, _, _ = self._parse_text(text)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].merchant, "UPI-SWIGGY")
        self.assertEqual(candidates[0].transaction_type, "DEBIT")

    def test_csv_date_description_amount(self):
        csv_text = (
            "Date,Description,Amount\n"
            "05/07/2026,UPI-SWIGGY,-290.00\n"
            "06/07/2026,SALARY CREDIT,50000.00\n"
        )
        result = parse_document("statement.csv", csv_text.encode("utf-8"))
        self.assertEqual(result.detected, 2)
        self.assertEqual(result.transactions[0]["merchant"], "UPI-SWIGGY")
        self.assertEqual(result.transactions[0]["transaction_type"], "DEBIT")

    def test_csv_debit_credit_columns(self):
        csv_text = (
            "Transaction Date,Narration,Debit,Credit\n"
            "05/07/2026,UPI-SWIGGY,290.00,\n"
            "06/07/2026,SALARY CREDIT,,50000.00\n"
        )
        result = parse_document("statement.csv", csv_text.encode("utf-8"))
        self.assertEqual(result.detected, 2)
        self.assertEqual(result.transactions[0]["transaction_type"], "DEBIT")
        self.assertEqual(result.transactions[1]["transaction_type"], "CREDIT")

    def test_xlsx_different_column_order(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Debit", "Credit", "Transaction Date", "Narration"])
        sheet.append(["150.00", "", "05/07/2026", "UBER INDIA"])
        sheet.append(["", "50000.00", "06/07/2026", "SALARY CREDIT"])
        buffer = io.BytesIO()
        workbook.save(buffer)

        result = parse_document("statement.xlsx", buffer.getvalue())
        self.assertEqual(result.detected, 2)
        self.assertEqual(result.transactions[0]["merchant"], "UBER INDIA")
        self.assertEqual(result.transactions[1]["transaction_type"], "CREDIT")

    def test_pdf_negative_amount(self):
        candidates, _, _ = self._parse_text("05/07/2026 UPI-SWIGGY -290.00")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].transaction_type, "DEBIT")

    def test_pdf_separate_debit_credit_columns(self):
        text = "\n".join(
            [
                "Date | Narration | Withdrawal | Deposit",
                "05/07/2026 | UPI-SWIGGY | 290.00 |",
                "06/07/2026 | SALARY CREDIT | | 50000.00",
            ]
        )
        candidates, _, _ = self._parse_text(text)
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].transaction_type, "DEBIT")

    def test_currency_formatted_amount(self):
        candidates, _, _ = self._parse_text("05 Jul 26 AMAZON INDIA ₹45,000.00 C")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].amount, 45000.0)

    def test_different_date_formats(self):
        formats = [
            "05 Jul 26 UPI-ZOMATO 120.00 D",
            "05/07/2026 UPI-ZOMATO 120.00 D",
            "2026-07-05 UPI-ZOMATO 120.00 D",
        ]
        for line in formats:
            candidates, _, _ = self._parse_text(line)
            self.assertEqual(len(candidates), 1, msg=line)
            self.assertEqual(candidates[0].date, date(2026, 7, 5), msg=line)

    def test_summary_lines_are_ignored(self):
        text = "\n".join(
            [
                "Opening Balance 10,000.00",
                "05 Jul 26 UPI-SWIGGY 290.00 D",
                "Closing Balance 9,710.00",
                "Minimum Amount Due 1,000.00",
            ]
        )
        candidates, ignored, _ = self._parse_text(text)
        self.assertEqual(len(candidates), 1)
        self.assertGreaterEqual(ignored, 2)

    def test_multiple_consecutive_transactions(self):
        text = "\n".join(
            [
                "05 Jul 26 UPI-SWIGGY 290.00 D",
                "06 Jul 26 AMAZON INDIA 1200.00 D",
                "07 Jul 26 SALARY CREDIT 50000.00 C",
            ]
        )
        candidates, _, _ = self._parse_text(text)
        self.assertEqual(len(candidates), 3)

    def test_wrapped_description(self):
        text = "\n".join(
            [
                "05 Jul 26 DECATHLON EVENT",
                "BANGALORE",
                "890.00 D",
            ]
        )
        candidates, _, _ = self._parse_text(text)
        self.assertEqual(len(candidates), 1)
        self.assertIn("DECATHLON", candidates[0].merchant)

    def test_duplicate_fingerprints_for_identical_rows(self):
        row = {
            "date": date(2026, 7, 5),
            "merchant": "UPI-SWIGGY",
            "amount": 290.0,
            "transaction_type": "DEBIT",
            "description": "UPI-SWIGGY",
        }
        first = generate_transaction_fingerprint(row)
        second = generate_transaction_fingerprint(dict(row))
        self.assertEqual(first, second)

    def test_real_world_like_statement(self):
        lines = ["Date,Description,Amount"]
        merchants = [
            "UPI-SWIGGY",
            "AMAZON INDIA",
            "UBER INDIA",
            "DECATHLON EVENT",
            "ZOMATO",
            "ATM CASH WITHDRAWAL",
        ]
        for day in range(1, 25):
            merchant = merchants[day % len(merchants)]
            amount = 100 + day * 37
            lines.append(f"2026-08-{day:02d},{merchant},{amount}.00")
        result = parse_document("august.csv", "\n".join(lines).encode("utf-8"))
        self.assertEqual(result.detected, 24)
        self.assertGreater(result.ignored, 0)


if __name__ == "__main__":
    unittest.main()
