import json
import os

from dotenv import load_dotenv
from openai import APIStatusError, OpenAI

load_dotenv()

AI_QUOTA_EXCEEDED_MESSAGE = (
    "AI normalization is temporarily unavailable because the AI usage "
    "limit has been reached."
)


class AIQuotaExceededError(Exception):
    def __init__(self, message: str = AI_QUOTA_EXCEEDED_MESSAGE) -> None:
        super().__init__(message)
        self.message = message

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

CATEGORIES = [
    "Food",
    "Transport",
    "Shopping",
    "Entertainment",
    "Subscriptions",
    "Bills",
    "Healthcare",
    "Travel",
    "Other",
]


def ask_llm(prompt: str, max_tokens: int = 1000) -> str:
    try:
        response = client.chat.completions.create(
            model="openai/gpt-4.1-mini",
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
    except APIStatusError as error:
        if error.status_code == 402:
            raise AIQuotaExceededError() from error
        raise

    return response.choices[0].message.content or ""


def categorize_transaction(
    merchant: str,
    amount: float | None = None,
    description: str | None = None,
) -> dict:
    prompt = f"""
You are a financial transaction categorizer.

Choose exactly ONE category from this list:

{", ".join(CATEGORIES)}

Transaction:
Merchant: {merchant}
Amount: ₹{amount or "None"} 
Description: {description or "None"}

Return ONLY valid JSON:

{{
  "category": "Food",
  "confidence": 0.95,
  "reason": "Brief explanation"
}}

Rules:
- category must be exactly one of the allowed categories
- confidence must be between 0 and 1
- do not invent categories
- keep the reason concise
"""

    raw_response = ask_llm(prompt)

    result = json.loads(raw_response)

    if result["category"] not in CATEGORIES:
        raise ValueError("Invalid category returned by LLM.")

    confidence = float(result["confidence"])

    if not 0 <= confidence <= 1:
        raise ValueError("Invalid confidence returned by LLM.")

    return {
        "category": result["category"],
        "confidence": confidence,
        "reason": result["reason"],
    }
def normalize_transactions_batch(
    transactions: list[dict],
) -> list[dict]:

    transaction_text = ""

    for index, transaction in enumerate(transactions):
        transaction_text += f"""
Transaction {index}:
Merchant: {transaction["merchant"]}
Amount: {transaction["amount"]}
Bank transaction type: {transaction["transaction_type"]}
Description: {transaction.get("description")}
"""

    prompt = f"""
You are a financial transaction normalization system.

You are given EXACTLY {len(transactions)} transactions.

Your job is to return EXACTLY {len(transactions)} separate
transaction objects.

IMPORTANT:
- Transaction 0 must produce result with index 0.
- Transaction 1 must produce result with index 1.
- Continue for every transaction.
- NEVER combine transactions.
- NEVER omit a transaction.
- NEVER return a single object for the entire batch.

Transactions:

{transaction_text}

For EVERY transaction determine:

1. merchant: canonical merchant name
2. category
3. economic transaction type
4. confidence from 0 to 1
5. short reason

IMPORTANT FINANCIAL RULES:

- DEBIT does not automatically mean PURCHASE.
- CREDIT does not automatically mean INCOME.

- "PAYMENT RECEIVED", "CARD PAYMENT", "BILL PAYMENT"
  or similar credit-card payment entries are PAYMENT.

- Refunds, reversals, cashback adjustments and surcharge
  waivers are REFUND.

- Salary, wages, freelance income or clearly identifiable
  earnings are INCOME.

- Transfers to individuals are TRANSFER.

- Bank/card fees are FEE.

- Interest charges are INTEREST.

- Normal purchases are PURCHASE.

Allowed categories:

Food
Transport
Shopping
Entertainment
Subscriptions
Bills
Healthcare
Travel
Other

Allowed economic transaction types:

PURCHASE
PAYMENT
REFUND
TRANSFER
FEE
INTEREST
INCOME
OTHER

Do not invent categories or transaction types.

Return ONLY this JSON structure:

{{
  "transactions": [
    {{
      "index": 0,
      "merchant": "canonical merchant name",
      "category": "Food",
      "transaction_type": "PURCHASE",
      "confidence": 0.95,
      "reason": "Short explanation"
    }},
    {{
      "index": 1,
      "merchant": "canonical merchant name",
      "category": "Shopping",
      "transaction_type": "PURCHASE",
      "confidence": 0.95,
      "reason": "Short explanation"
    }}
  ]
}}

The example above only demonstrates the format.

YOU MUST RETURN EXACTLY {len(transactions)} OBJECTS
inside the transactions array.
"""
    
    raw_response = ask_llm(prompt, max_tokens=1000)

    raw_response = raw_response.strip()

    if raw_response.startswith("```"):
        raw_response = raw_response.replace("```json", "")
        raw_response = raw_response.replace("```", "")
        raw_response = raw_response.strip()

    result = json.loads(raw_response)

    ai_transactions = result["transactions"]

    if len(ai_transactions) != len(transactions):
        raise ValueError(
            f"AI returned {len(ai_transactions)} results "
            f"for {len(transactions)} transactions."
        )

    ALLOWED_CATEGORIES = {
        "Food",
        "Transport",
        "Shopping",
        "Entertainment",
        "Subscriptions",
        "Bills",
        "Healthcare",
        "Travel",
        "Other",
    }

    ALLOWED_ECONOMIC_TYPES = {
        "PURCHASE",
        "PAYMENT",
        "REFUND",
        "TRANSFER",
        "FEE",
        "INTEREST",
        "INCOME",
        "OTHER",
    }

    validated = []

    for original, ai_result in zip(
        transactions,
        ai_transactions
    ):

        category = ai_result["category"]
        economic_type = ai_result["transaction_type"]

        if category not in ALLOWED_CATEGORIES:
            category = "Other"

        if economic_type not in ALLOWED_ECONOMIC_TYPES:
            economic_type = "OTHER"

        confidence = float(
            ai_result["confidence"]
        )

        confidence = max(
            0.0,
            min(1.0, confidence)
        )

        description = (
            original.get("description") or ""
        ).upper()

        # Credit-card payment received
        if any(
            keyword in description
            for keyword in [
                "PAYMENT RECEIVED",
                "CARD PAYMENT",
                "BILL PAYMENT",
            ]
        ):
            economic_type = "PAYMENT"

        # Refunds / reversals / waivers
        elif any(
            keyword in description
            for keyword in [
                "REFUND",
                "REVERSAL",
                "SURCHARGE WAIVER",
                "CASHBACK",
            ]
        ):
            economic_type = "REFUND"

        # A debit cannot be income
        elif (
            original["transaction_type"] == "DEBIT"
            and economic_type == "INCOME"
        ):
            economic_type = "PURCHASE"

        # Be conservative with credit transactions
        elif (
            original["transaction_type"] == "CREDIT"
            and economic_type == "INCOME"
        ):
            economic_type = "OTHER"

        validated.append({
            **ai_result,
            "category": category,
            "transaction_type": economic_type,
            "confidence": confidence,
        })

    return validated