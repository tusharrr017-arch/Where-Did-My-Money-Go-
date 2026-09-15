from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.ai_service import ask_llm
from app import finance


ALLOWED_INTENTS = {
    "MONTHLY_SPENDING",
    "CATEGORY_SPENDING",
    "MERCHANT_SPENDING",
    "LARGEST_TRANSACTION",
    "TOP_TRANSACTIONS",
    "MONTH_COMPARISON",
    "TRANSACTION_SEARCH",
    "CASH_FLOW",
    "GENERAL_FINANCIAL_SUMMARY",
    "OFF_TOPIC",
}

OFF_TOPIC_REPLY = (
    "I can only help with your finances — spending, income, merchants, "
    "categories, and cash flow from your statements. Try asking how much "
    "you spent on food, your biggest purchase, or a month comparison."
)

_FINANCE_HINTS = (
    "spend",
    "spent",
    "spending",
    "money",
    "rupee",
    "₹",
    "transaction",
    "merchant",
    "category",
    "salary",
    "income",
    "cash",
    "bill",
    "refund",
    "purchase",
    "bought",
    "paid",
    "debit",
    "credit",
    "statement",
    "budget",
    "saving",
    "expense",
    "subscription",
    "rent",
    "grocery",
    "groceries",
    "transfer",
    "balance",
    "upi",
    "wallet",
    "loan",
    "emi",
    "tax",
    "gst",
    "food",
    "uber",
    "zomato",
    "swiggy",
    "amazon",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "how much",
    "biggest",
    "largest",
    "compare",
    "cash flow",
    "cashflow",
    "overview",
    "summary",
    "total",
    "where did",
)


def is_off_topic_question(question: str) -> bool:
    text = question.strip().lower()
    if not text:
        return True
    if any(hint in text for hint in _FINANCE_HINTS):
        return False
    return True


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


def classify_intent(question: str, default_year: int, default_month: int) -> dict:
    prompt = f"""
You classify personal-finance questions into ONE intent.

Question: {question}

Today's default period if the user says "this month" or omits a month:
year={default_year}, month={default_month}

Return ONLY JSON:
{{
  "intent": "MONTHLY_SPENDING",
  "year": {default_year},
  "month": {default_month},
  "year_b": null,
  "month_b": null,
  "category": null,
  "merchant": null,
  "search": null,
  "limit": 5
}}

intent must be one of:
MONTHLY_SPENDING
CATEGORY_SPENDING
MERCHANT_SPENDING
LARGEST_TRANSACTION
TOP_TRANSACTIONS
MONTH_COMPARISON
TRANSACTION_SEARCH
CASH_FLOW
GENERAL_FINANCIAL_SUMMARY
OFF_TOPIC

Rules:
- Use OFF_TOPIC for anything that is not about the user's money, spending, income, merchants, categories, cash flow, or statement
- Programming, definitions, news, recipes, jokes, and general knowledge are OFF_TOPIC
- month is 1-12 or null
- year is a 4-digit year or null
- For MONTH_COMPARISON, year/month is the first period, year_b/month_b the second
- category must be one of: Food, Transport, Shopping, Entertainment, Subscriptions, Bills, Healthcare, Travel, Other
- Do not invent SQL
- Do not answer the user's question yourself
"""
    result = _parse_json(ask_llm(prompt))
    intent = str(result.get("intent") or "OFF_TOPIC").upper()
    if intent not in ALLOWED_INTENTS:
        intent = "OFF_TOPIC"

    year = result.get("year") or default_year
    month = result.get("month") or default_month
    try:
        year = int(year)
        month = int(month)
    except (TypeError, ValueError):
        year, month = default_year, default_month

    if month < 1 or month > 12:
        month = default_month

    year_b = result.get("year_b")
    month_b = result.get("month_b")
    try:
        year_b = int(year_b) if year_b is not None else None
        month_b = int(month_b) if month_b is not None else None
    except (TypeError, ValueError):
        year_b, month_b = None, None

    limit = result.get("limit") or 5
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 5

    return {
        "intent": intent,
        "year": year,
        "month": month,
        "year_b": year_b,
        "month_b": month_b,
        "category": result.get("category"),
        "merchant": result.get("merchant"),
        "search": result.get("search") or question,
        "limit": limit,
    }


def run_intent(db: Session, user_id: int, intent: dict) -> dict:
    name = intent["intent"]
    year = intent["year"]
    month = intent["month"]

    if name == "MONTHLY_SPENDING":
        return finance.monthly_spending(db, user_id, year, month)

    if name == "CATEGORY_SPENDING":
        category = intent.get("category") or "Other"
        return finance.category_spending(db, user_id, str(category), year, month)

    if name == "MERCHANT_SPENDING":
        merchant = str(intent.get("merchant") or intent.get("search") or "")
        return finance.merchant_spending(db, user_id, merchant, year, month)

    if name == "LARGEST_TRANSACTION":
        category = intent.get("category")
        return finance.largest_transaction(
            db, user_id, year, month, str(category) if category else None
        )

    if name == "TOP_TRANSACTIONS":
        category = intent.get("category")
        return finance.top_transactions(
            db,
            user_id,
            intent.get("limit") or 5,
            year,
            month,
            str(category) if category else None,
        )

    if name == "MONTH_COMPARISON":
        year_b = intent.get("year_b") or year
        month_b = intent.get("month_b") or month
        prev_year, prev_month = finance.previous_month(year, month)
        if intent.get("year_b") is None:
            year_b, month_b = year, month
            year, month = prev_year, prev_month
        return finance.month_comparison(db, user_id, year, month, year_b, month_b)

    if name == "TRANSACTION_SEARCH":
        return finance.transaction_search(
            db, user_id, str(intent.get("search") or "")
        )

    if name == "CASH_FLOW":
        return finance.build_cashflow(db, user_id, year, month)

    if name == "OFF_TOPIC":
        return {"off_topic": True}

    return finance.general_summary(db, user_id)


def narrate_answer(question: str, facts: dict) -> str:
    prompt = f"""
You are a personal finance assistant.

The user asked:
{question}

These numbers were computed by the application from the user's own transactions.
Use ONLY these facts. Do not invent amounts, merchants, or dates.

Facts JSON:
{json.dumps(facts, default=str)}

Return ONLY JSON:
{{
  "answer": "A concise natural-language answer using the rupee symbol ₹."
}}

Rules:
- Answer only from the facts about the user's transactions.
- Never explain technologies, news, people, or general knowledge.
- If the question is not about the user's money, say you can only help with their finances.
- If totals are 0 or lists are empty, say you did not find matching spending.
- Never treat PAYMENT or TRANSFER as purchases.
- Keep the answer to 1-3 sentences.
"""
    result = _parse_json(ask_llm(prompt))
    answer = str(result.get("answer") or "").strip()
    if not answer:
        return "I could not build an answer from your transactions."
    return answer


def ask_assistant(db: Session, user_id: int, question: str) -> dict:
    if is_off_topic_question(question):
        return {"answer": OFF_TOPIC_REPLY, "intent": "OFF_TOPIC"}

    default_year, default_month = finance.current_month_from_data(db, user_id)
    intent = classify_intent(question, default_year, default_month)
    if intent["intent"] == "OFF_TOPIC":
        return {"answer": OFF_TOPIC_REPLY, "intent": "OFF_TOPIC"}

    facts = run_intent(db, user_id, intent)
    answer = narrate_answer(question, {"intent": intent, "result": facts})
    return {
        "answer": answer,
        "intent": intent["intent"],
    }
