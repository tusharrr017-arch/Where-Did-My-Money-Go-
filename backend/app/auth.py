import os
import re
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET", "").strip()
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 7

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")

bearer_scheme = HTTPBearer(auto_error=False)


def require_jwt_secret() -> str:
    if not JWT_SECRET or len(JWT_SECRET) < 16:
        raise HTTPException(
            status_code=500,
            detail="Server auth is not configured.",
        )
    return JWT_SECRET


def normalize_username(username: str) -> str:
    return username.strip()


def validate_credentials(username: str, password: str) -> str:
    cleaned = normalize_username(username)

    if not USERNAME_RE.match(cleaned):
        raise HTTPException(
            status_code=400,
            detail="Username must be 3–32 letters, numbers, or underscores.",
        )

    if len(password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters.",
        )

    return cleaned


def hash_password(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except ValueError:
        return False


def create_access_token(user: User) -> str:
    secret = require_jwt_secret()
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Please log in to continue.",
        )

    secret = require_jwt_secret()

    try:
        payload = jwt.decode(
            creds.credentials,
            secret,
            algorithms=[JWT_ALGORITHM],
        )
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=401,
            detail="Your session expired. Please log in again.",
        )

    user = db.execute(
        select(User).where(User.id == user_id)
    ).scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Your session expired. Please log in again.",
        )

    return user


def find_user_by_username(db: Session, username: str) -> User | None:
    return db.execute(
        select(User).where(func.lower(User.username) == username.lower())
    ).scalar_one_or_none()
