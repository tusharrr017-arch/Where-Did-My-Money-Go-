import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)


class Base(DeclarativeBase):
    pass
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema() -> None:
    """
    Additive schema updates for existing Neon databases.
    Does not delete transactions or assign orphan rows to a user.
    """
    statements = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE
        )
        """,
        "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS user_id INTEGER",
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'transactions_user_id_fkey'
            ) THEN
                ALTER TABLE transactions
                ADD CONSTRAINT transactions_user_id_fkey
                FOREIGN KEY (user_id) REFERENCES users(id);
            END IF;
        END $$;
        """,
        "CREATE INDEX IF NOT EXISTS ix_transactions_user_id ON transactions (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_users_username ON users (username)",
        "DROP INDEX IF EXISTS ix_transactions_transaction_fingerprint",
        "DROP INDEX IF EXISTS uq_transactions_transaction_fingerprint",
        "ALTER TABLE transactions DROP CONSTRAINT IF EXISTS transactions_transaction_fingerprint_key",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_transactions_user_fingerprint
        ON transactions (user_id, transaction_fingerprint)
        WHERE user_id IS NOT NULL AND transaction_fingerprint IS NOT NULL
        """,
    ]

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))