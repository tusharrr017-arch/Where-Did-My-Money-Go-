from datetime import date
import csv
import io
import json
import traceback

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import Base, engine, SessionLocal, get_db, ensure_schema
from app import models, schemas, finance, persist, statement, assistant
from app.models import User
from app.auth import (
    create_access_token,
    find_user_by_username,
    get_current_user,
    hash_password,
    validate_credentials,
    verify_password,
)
from app.ai_service import (
    AIQuotaExceededError,
    ask_llm,
    categorize_transaction,
    normalize_transactions_batch,
)
from app.services.normalization.service import (
    parse_statement_file,
    parse_statement_transactions,
)
from app.services.extraction.service import extract_document
from app.statement import (
    apply_ai_to_rows,
    parse_uploaded_statement,
    parse_uploaded_statement_result,
    serialize_parsed,
    validate_upload,
)


app = FastAPI(
    title="Where Did My Money Go?",
    description="AI-powered personal finance analyzer",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)
ensure_schema()


def http_error(status: int, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail=message)


@app.get("/")
def root():
    return {
        "message": "Where Did My Money Go? API is running."
    }


@app.post("/auth/signup")
def signup(
    payload: schemas.AuthRequest,
    db: Session = Depends(get_db),
):
    username = validate_credentials(payload.username, payload.password)

    if find_user_by_username(db, username):
        raise http_error(409, "That username is already taken.")

    user = User(
        username=username,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "token": create_access_token(user),
        "user": {"id": user.id, "username": user.username},
    }


@app.post("/auth/login")
def login(
    payload: schemas.AuthRequest,
    db: Session = Depends(get_db),
):
    username = validate_credentials(payload.username, payload.password)
    user = find_user_by_username(db, username)

    if user is None or not verify_password(payload.password, user.password_hash):
        raise http_error(401, "Invalid username or password.")

    return {
        "token": create_access_token(user),
        "user": {"id": user.id, "username": user.username},
    }


@app.get("/auth/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "username": user.username}


@app.get("/database-test")
def database_test(user: User = Depends(get_current_user)):
    with SessionLocal() as db:
        result = db.execute(
            select(func.count(models.Transaction.id)).where(
                models.Transaction.user_id == user.id
            )
        ).scalar()

    return {
        "message": "Successfully connected to Neon PostgreSQL!",
        "result": result,
    }


@app.post("/transactions")
def create_transaction(
    transaction: schemas.TransactionCreate,
    user: User = Depends(get_current_user),
):
    with SessionLocal() as db:
        db_transaction = models.Transaction(
            user_id=user.id,
            merchant=transaction.merchant,
            amount=transaction.amount,
            category=transaction.category,
            transaction_type=transaction.transaction_type,
            economic_type=transaction.economic_type,
            date=transaction.date,
            description=transaction.description,
            transaction_fingerprint=transaction.transaction_fingerprint,
            category_confidence=transaction.category_confidence,
            category_reason=transaction.category_reason,
            source_file=transaction.source_file,
        )
        db.add(db_transaction)
        db.commit()
        db.refresh(db_transaction)
        return finance.serialize_transaction(db_transaction)


@app.get("/transactions")
def get_transactions(user: User = Depends(get_current_user)):
    with SessionLocal() as db:
        transactions = finance.load_user_transactions(db, user.id)
        return [finance.serialize_transaction(row) for row in transactions]


@app.delete("/transactions")
def delete_all_transactions(user: User = Depends(get_current_user)):
    with SessionLocal() as db:
        rows = finance.load_user_transactions(db, user.id)
        deleted = len(rows)
        for row in rows:
            db.delete(row)
        db.commit()
    return {"deleted": deleted}


@app.post("/transactions/import-preview")
def import_preview_transactions(
    payload: schemas.PreviewImportRequest,
    user: User = Depends(get_current_user),
):
    incoming = [item.model_dump() for item in payload.transactions]
    with SessionLocal() as db:
        imported, duplicates = persist.save_transactions_for_user(
            db,
            user.id,
            incoming,
            payload.source_file,
            already_normalized=True,
        )
    return {
        "message": "Document processed successfully.",
        "count": imported,
        "imported": imported,
        "duplicates": duplicates,
        "total_found": len(incoming),
    }


@app.post("/transactions/import")
async def import_transactions(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    contents = await file.read()
    text = contents.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    incoming = []

    for row in rows:
        incoming.append(
            {
                "merchant": row["merchant"],
                "amount": float(row["amount"]),
                "category": row["category"],
                "transaction_type": row["transaction_type"],
                "date": date.fromisoformat(row["date"]),
                "description": row.get("description"),
                "source_file": file.filename,
            }
        )

    with SessionLocal() as db:
        imported, duplicates = persist.save_transactions_for_user(
            db,
            user.id,
            incoming,
            file.filename,
            already_normalized=True,
        )

    return {
        "message": "Transactions imported successfully.",
        "filename": file.filename,
        "count": imported,
        "imported": imported,
        "duplicates": duplicates,
    }


@app.get("/summary")
def get_summary(
    year: int | None = None,
    month: int | None = None,
    user: User = Depends(get_current_user),
):
    today = date.today()
    if year is None:
        year = today.year
    if month is None:
        month = today.month
    if month < 1 or month > 12:
        return {"error": "Month must be between 1 and 12."}

    with SessionLocal() as db:
        return finance.build_summary(db, user.id, year, month)


@app.get("/cashflow")
def get_cashflow(
    year: int,
    month: int,
    user: User = Depends(get_current_user),
):
    if month < 1 or month > 12:
        return {"error": "Month must be between 1 and 12."}

    with SessionLocal() as db:
        return finance.build_cashflow(db, user.id, year, month)


@app.get("/ai-test")
def ai_test():
    result = ask_llm(
        """
        Return ONLY valid JSON.

        {
          "message": "AI connection is working"
        }
        """
    )
    try:
        return json.loads(result)
    except json.JSONDecodeError:
        return {"message": result}


@app.post("/categorize")
def categorize(
    merchant: str,
    amount: float | None = None,
    description: str | None = None,
    user: User = Depends(get_current_user),
):
    return categorize_transaction(
        merchant=merchant,
        amount=amount,
        description=description,
    )


@app.post("/documents/extract")
async def extract_document_endpoint(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    contents = await file.read()
    extracted_text = extract_document(
        filename=file.filename,
        contents=contents,
    )
    return {
        "filename": file.filename,
        "text": extracted_text,
    }


@app.post("/documents/parse-transactions")
async def parse_document_transactions(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    contents = await file.read()
    parsed = parse_statement_file(file.filename or "statement.txt", contents)
    return {
        "filename": file.filename,
        "count": parsed["detected"],
        "detected": parsed["detected"],
        "ignored": parsed["ignored"],
        "review": parsed["review"],
        "parser": parsed["parser"],
        "transactions": parsed["transactions"],
    }


@app.post("/documents/normalize-transactions")
async def normalize_document_transactions(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    contents = await file.read()
    extracted_text = extract_document(
        filename=file.filename,
        contents=contents,
    )
    transactions = parse_statement_transactions(extracted_text)
    if not transactions:
        return {
            "filename": file.filename,
            "count": 0,
            "transactions": [],
        }

    try:
        normalized_transactions = apply_ai_to_rows(transactions)
    except AIQuotaExceededError as error:
        raise http_error(503, error.message)
    return {
        "filename": file.filename,
        "count": len(normalized_transactions),
        "transactions": normalized_transactions,
    }


@app.post("/documents/preview")
async def preview_document(file: UploadFile = File(...)):
    """
    Anonymous analysis only. Parsed transactions are returned to the
    client and are never written to PostgreSQL.
    """
    contents = await file.read()
    try:
        filename = validate_upload(file.filename, contents)
        parsed_result = parse_uploaded_statement_result(filename, contents)
        parsed = parsed_result.transactions
        if not parsed:
            return {
                "filename": filename,
                "count": 0,
                "detected": 0,
                "ignored": parsed_result.ignored,
                "review": parsed_result.review,
                "transactions": [],
            }
        normalized = apply_ai_to_rows(parsed)
        return {
            "filename": filename,
            "count": len(normalized),
            "detected": parsed_result.detected,
            "ignored": parsed_result.ignored,
            "review": parsed_result.review,
            "transactions": [serialize_parsed(row) for row in normalized],
        }
    except ValueError as error:
        raise http_error(400, str(error))
    except AIQuotaExceededError as error:
        raise http_error(503, error.message)
    except Exception:
        traceback.print_exc()
        raise http_error(500, "Could not process that statement.")


@app.post("/documents/import")
async def import_document(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    contents = await file.read()
    try:
        filename = validate_upload(file.filename, contents)
        parsed_result = parse_uploaded_statement_result(filename, contents)
        parsed = parsed_result.transactions
        if not parsed:
            return {
                "message": "No transactions found in the document.",
                "filename": filename,
                "count": 0,
                "imported": 0,
                "duplicates": 0,
                "total_found": 0,
                "detected": 0,
                "ignored": parsed_result.ignored,
                "review": parsed_result.review,
            }

        with SessionLocal() as db:
            imported, duplicates = persist.save_transactions_for_user(
                db,
                user.id,
                parsed,
                filename,
                already_normalized=False,
            )

        return {
            "message": "Document processed successfully.",
            "filename": filename,
            "count": imported,
            "imported": imported,
            "duplicates": duplicates,
            "total_found": len(parsed),
            "detected": parsed_result.detected,
            "ignored": parsed_result.ignored,
            "review": parsed_result.review,
        }
    except ValueError as error:
        raise http_error(400, str(error))
    except AIQuotaExceededError as error:
        raise http_error(503, error.message)
    except Exception:
        traceback.print_exc()
        raise http_error(500, "Could not import that statement.")


@app.get("/insights")
def get_insights(
    year: int,
    month: int,
    user: User = Depends(get_current_user),
):
    if month < 1 or month > 12:
        return {"error": "Month must be between 1 and 12."}

    start_date, end_date = finance.month_bounds(year, month)

    with SessionLocal() as db:
        transactions = db.execute(
            select(models.Transaction)
            .where(
                models.Transaction.user_id == user.id,
                models.Transaction.date >= start_date,
                models.Transaction.date < end_date,
            )
            .order_by(models.Transaction.date)
        ).scalars().all()

    if not transactions:
        return {
            "summary": "No transactions found for this month.",
            "insights": [],
            "recommendation": "",
        }

    transaction_data = [
        {
            "date": str(t.date),
            "merchant": t.merchant,
            "amount": float(t.amount),
            "category": t.category,
            "bank_type": t.transaction_type,
            "economic_type": t.economic_type,
            "description": t.description,
        }
        for t in transactions
    ]

    prompt = f"""
You are a personal finance analyst.

Analyze these real financial transactions for
{year}-{month:02d}.

Transactions:

{transaction_data}

IMPORTANT FINANCIAL RULES:

Bank transaction type:

- DEBIT means money left the account/card.
- CREDIT means money came into the account/card.

Economic type explains what the transaction
actually means:

- PURCHASE = actual spending
- PAYMENT = payment toward a card/account balance
- REFUND = returned money
- TRANSFER = movement of money between accounts
- FEE = bank/service fee
- INTEREST = interest charge or interest credit
- INCOME = actual income
- OTHER = unknown/other

For spending analysis:

1. Count DEBIT + PURCHASE as actual spending.
2. Count DEBIT + FEE as spending.
3. Count DEBIT + INTEREST as spending.
4. Do NOT count PAYMENT as spending.
5. Do NOT count REFUND as spending.
6. Do NOT count TRANSFER as spending.
7. Do NOT treat a large CREDIT PAYMENT as income.
8. Do NOT treat an ordinary CREDIT REFUND as income.
9. CREDIT + INCOME can be considered actual income.

Focus primarily on actual spending behavior.

Return ONLY valid JSON in exactly this format:

{{
  "summary": "2-3 sentence summary of actual spending.",
  "insights": [
    "Insight 1",
    "Insight 2",
    "Insight 3"
  ],
  "recommendation": "One practical recommendation."
}}

Rules:
- Use only the provided transactions.
- Do not invent transactions, amounts, or merchants.
- Do not treat card payments as spending.
"""

    raw_response = ask_llm(prompt)
    try:
        result = json.loads(raw_response)
    except json.JSONDecodeError:
        raise http_error(502, "AI returned invalid JSON.")

    if not isinstance(result, dict):
        raise http_error(502, "AI response must be a JSON object.")

    insights = result.get("insights")
    if not isinstance(insights, list):
        insights = []

    return {
        "summary": str(result.get("summary") or ""),
        "insights": [str(item) for item in insights],
        "recommendation": str(result.get("recommendation") or ""),
    }


@app.post("/assistant/ask")
def assistant_ask(
    payload: schemas.AssistantRequest,
    user: User = Depends(get_current_user),
):
    question = payload.question.strip()
    if not question:
        raise http_error(400, "Ask a question about your finances.")

    try:
        with SessionLocal() as db:
            return assistant.ask_assistant(db, user.id, question)
    except json.JSONDecodeError:
        raise http_error(502, "The assistant could not parse that request.")
    except Exception:
        traceback.print_exc()
        raise http_error(502, "The assistant could not answer right now.")
