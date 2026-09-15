from datetime import date

from pydantic import BaseModel, Field


class TransactionCreate(BaseModel):
    merchant: str
    amount: float
    category: str
    transaction_type: str
    date: date
    description: str | None = None
    economic_type: str | None = None
    transaction_fingerprint: str | None = None
    category_confidence: float | None = None
    category_reason: str | None = None
    source_file: str | None = None


class TransactionCategorize(BaseModel):
    merchant: str
    amount: float | None = None
    description: str | None = None


class TransactionNormalizeRequest(BaseModel):
    merchant: str
    amount: float | None = None
    transaction_type: str
    description: str | None = None


class AuthRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)


class AssistantRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)


class PreviewImportRequest(BaseModel):
    transactions: list[TransactionCreate]
    source_file: str | None = None
