"""Password hashing, session tokens, at-rest encryption and the current-user dependency.

Two identity providers are supported:
- ``local`` (default): accounts live in the users table; we issue HS256 tokens.
- ``cognito``: accounts live in an Amazon Cognito user pool; the bearer token is
  the Cognito ID token, verified against the pool's JWKS. See ``cognito.py``.
"""

import base64
import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import jwt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import User

logger = logging.getLogger(__name__)

TOKEN_TTL = timedelta(days=7)
_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}
_bearer = HTTPBearer(auto_error=False)


def auth_provider() -> str:
    return os.getenv("AUTH_PROVIDER", "local").strip().lower()


def demo_enabled() -> bool:
    return auth_provider() == "local" and os.getenv("DEMO_MODE", os.getenv("SEED_DEMO", "false")).lower() == "true"


@lru_cache
def secret_key() -> str:
    configured = os.getenv("UNITASK_SECRET_KEY", "").strip()
    if configured:
        return configured
    # Development convenience: persist a random key next to the database so sessions
    # and encrypted Teams tokens survive restarts. Production sets UNITASK_SECRET_KEY.
    path = Path(__file__).resolve().parents[1] / ".secret_key"
    if path.is_file():
        return path.read_text().strip()
    key = secrets.token_urlsafe(48)
    path.write_text(key)
    logger.warning("UNITASK_SECRET_KEY is not set; generated a development key at %s", path)
    return key


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or not stored.startswith("scrypt$"):
        return False
    _, salt_b64, digest_b64 = stored.split("$", 2)
    digest = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), **_SCRYPT)
    return hmac.compare_digest(digest, base64.b64decode(digest_b64))


def issue_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user.id), "role": user.role, "iat": now, "exp": now + TOKEN_TTL}
    return jwt.encode(payload, secret_key(), algorithm="HS256")


def _fernet() -> Fernet:
    key = hashlib.sha256(f"unitask-at-rest:{secret_key()}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str | None:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        logger.warning("Could not decrypt a stored secret; the server key may have changed.")
        return None


def _unauthorized(detail: str = "Sign in to continue.") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise _unauthorized()
    token = credentials.credentials
    if auth_provider() == "cognito":
        from .cognito import verify_id_token

        claims = verify_id_token(token)
        if claims is None:
            raise _unauthorized("Your session has expired. Sign in again.")
        user = db.scalar(select(User).where(User.cognito_sub == claims["sub"]))
    else:
        try:
            claims = jwt.decode(token, secret_key(), algorithms=["HS256"])
        except jwt.PyJWTError:
            raise _unauthorized("Your session has expired. Sign in again.") from None
        user = db.get(User, int(claims["sub"]))
    if user is None:
        raise _unauthorized("This account no longer exists.")
    return user


def require_teacher(user: User = Depends(get_current_user)) -> User:
    if user.role != "teacher":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only teachers can do this.")
    return user


def require_student(user: User = Depends(get_current_user)) -> User:
    if user.role != "student":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only students can do this.")
    return user
