import json
import os
import time

from dotenv import load_dotenv
from openai import APIStatusError, OpenAI

load_dotenv()

AI_QUOTA_EXCEEDED_MESSAGE = (
    "AI normalization is temporarily unavailable because the AI usage "
    "limit has been reached."
)
AI_RATE_LIMIT_MESSAGE = (
    "AI normalization is temporarily busy because the free model is "
    "rate-limited. Please wait a minute and try again."
)
OPENROUTER_MAX_RETRIES = max(1, int(os.getenv("OPENROUTER_MAX_RETRIES", "4")))
OPENROUTER_RETRY_SECONDS = float(os.getenv("OPENROUTER_RETRY_SECONDS", "2"))


class AIQuotaExceededError(Exception):
    def __init__(self, message: str = AI_QUOTA_EXCEEDED_MESSAGE) -> None:
        super().__init__(message)
        self.message = message


DEFAULT_OPENROUTER_MODEL = "google/gemma-4-31b-it:free"


def _ai_config() -> tuple[OpenAI, str]:
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not openrouter_key:
        raise ValueError("Set OPENROUTER_API_KEY in the environment.")

    model = os.getenv("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL).strip()
    return (
        OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=openrouter_key,
        ),
        model or DEFAULT_OPENROUTER_MODEL,
    )


def _supports_json_mode(model: str) -> bool:
    return ":free" not in model.lower()


def _clean_json_response(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.replace("```json", "").replace("```", "").strip()
    return raw


client, AI_MODEL = _ai_config()

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

_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Food": ("swiggy", "zomato", "restaurant", "cafe", "food", "dominos", "mcdonald"),
    "Transport": ("uber", "ola", "metro", "fuel", "petrol", "parking", "irctc", "rapido"),
    "Shopping": ("amazon", "flipkart", "myntra", "mart", "store", "shop"),
    "Entertainment": ("netflix", "spotify", "movie", "cinema", "game"),
    "Subscriptions": ("subscription", "renewal", "membership"),
    "Bills": ("electric", "water", "gas", "broadband", "mobile", "recharge", "bill"),
    "Healthcare": ("pharmacy", "medical", "hospital", "clinic", "apollo"),
    "Travel": ("hotel", "flight", "airline", "booking", "makemytrip"),
}


def _guess_category(merchant: str, description: str) -> str:
    text = f"{merchant} {description}".lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return category
    return "Other"


def _guess_economic_type(transaction: dict) -> str:
    description = (transaction.get("description") or "").upper()
    if any(
        keyword in description
        for keyword in ("PAYMENT RECEIVED", "CARD PAYMENT", "BILL PAYMENT")
    ):
        return "PAYMENT"
    if any(
        keyword in description
        for keyword in ("REFUND", "REVERSAL", "CASHBACK", "SURCHARGE WAIVER")
    ):
        return "REFUND"
    if any(keyword in description for keyword in ("SALARY", "WAGE", "PAYROLL")):
        return "INCOME"
    if any(keyword in description for keyword in ("FEE", "CHARGE", "PENALTY")):
        return "FEE"
    if "INTEREST" in description:
        return "INTEREST"
    if transaction.get("transaction_type") == "CREDIT":
        return "OTHER"
    return "PURCHASE"


def fallback_normalize_batch(transactions: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for index, transaction in enumerate(transactions):
        description = transaction.get("description") or ""
        normalized.append(
            {
                "index": index,
                "merchant": transaction.get("merchant") or "Unknown",
                "category": _guess_category(
                    str(transaction.get("merchant") or ""),
                    str(description),
                ),
                "transaction_type": _guess_economic_type(transaction),
                "confidence": 0.35,
                "reason": "Basic keyword categorization while AI is unavailable.",
            }
        )
    return normalized


def _is_credit_limit_error(error: APIStatusError) -> bool:
    err_text = str(error).lower()
    return "insufficient" in err_text or "credit" in err_text


def _is_rate_limit_error(error: APIStatusError) -> bool:
    return error.status_code == 429 and not _is_credit_limit_error(error)


def ask_llm(prompt: str, max_tokens: int = 600) -> str:
    request_kwargs: dict = {
        "model": AI_MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "max_tokens": max_tokens,
    }
    if _supports_json_mode(AI_MODEL):
        request_kwargs["response_format"] = {"type": "json_object"}

    last_error: APIStatusError | None = None
    for attempt in range(OPENROUTER_MAX_RETRIES):
        try:
            response = client.chat.completions.create(**request_kwargs)
            return _clean_json_response(response.choices[0].message.content or "")
        except APIStatusError as error:
            last_error = error
            if error.status_code == 402:
                raise AIQuotaExceededError() from error
            if _is_credit_limit_error(error):
                raise AIQuotaExceededError() from error
            if _is_rate_limit_error(error) and attempt < OPENROUTER_MAX_RETRIES - 1:
                time.sleep(OPENROUTER_RETRY_SECONDS * (2**attempt))
                continue
            if _is_rate_limit_error(error):
                raise AIQuotaExceededError(AI_RATE_LIMIT_MESSAGE) from error
            raise

    if last_error is not None:
        raise last_error
    raise RuntimeError("OpenRouter request failed without a response.")


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

    raw_response = ask_llm(prompt, max_tokens=200)

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
    
    raw_response = ask_llm(prompt, max_tokens=700)

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