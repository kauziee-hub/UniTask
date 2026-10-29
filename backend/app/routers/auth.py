import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import AuthConfig, AuthResponse, ConfirmRequest, DemoLogin, LoginRequest, RegisterRequest, UserRead
from ..security import auth_provider, get_current_user, hash_password, issue_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.email) == email.lower()))


DEMO_ACCOUNTS = {"student": "riya.sharma@example.edu", "teacher": "meera.iyer@example.edu"}


def _demo_user(db: Session, role: str) -> User | None:
    """The synthetic demo accounts (names end in "(Demo)"), if this server has them. Never real users."""
    if auth_provider() != "local" or os.getenv("DEMO_LOGIN", "true").lower() == "false":
        return None
    user = _user_by_email(db, DEMO_ACCOUNTS[role])
    return user if user is not None and user.name.endswith("(Demo)") and user.role == role else None


@router.get("/config", response_model=AuthConfig)
def config(db: Session = Depends(get_db)) -> AuthConfig:
    return AuthConfig(provider=auth_provider(), demo=_demo_user(db, "student") is not None)


@router.post("/demo-login", response_model=AuthResponse)
def demo_login(payload: DemoLogin, db: Session = Depends(get_db)) -> AuthResponse:
    """One-click entry to the synthetic demo workspace for presentations."""
    user = _demo_user(db, payload.role)
    if user is None:
        raise HTTPException(404, "There is no demo workspace on this server.")
    return AuthResponse(token=issue_token(user), user=UserRead.model_validate(user))


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> AuthResponse:
    email = payload.email.lower()
    if _user_by_email(db, email):
        raise HTTPException(409, "An account with this email already exists. Sign in instead.")
    user = User(email=email, name=payload.name.strip(), role=payload.role)

    if auth_provider() == "cognito":
        from ..cognito import CognitoError, sign_up

        try:
            user.cognito_sub = sign_up(email, payload.password, user.name)
        except CognitoError as exc:
            raise HTTPException(400, str(exc)) from exc
        db.add(user)
        db.commit()
        return AuthResponse(
            needs_confirmation=True,
            message="We emailed you a verification code from Amazon Cognito. Enter it to finish creating your account.",
        )

    user.password_hash = hash_password(payload.password)
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "An account with this email already exists.") from exc
    db.refresh(user)
    return AuthResponse(token=issue_token(user), user=UserRead.model_validate(user))


@router.post("/confirm", response_model=AuthResponse)
def confirm(payload: ConfirmRequest) -> AuthResponse:
    if auth_provider() != "cognito":
        raise HTTPException(400, "Email confirmation is only used with Amazon Cognito.")
    from ..cognito import CognitoError, confirm_sign_up

    try:
        confirm_sign_up(payload.email.lower(), payload.code.strip())
    except CognitoError as exc:
        raise HTTPException(400, str(exc)) from exc
    return AuthResponse(message="Email verified. You can sign in now.")


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = _user_by_email(db, payload.email)
    if auth_provider() == "cognito":
        from ..cognito import CognitoError, sign_in

        try:
            token = sign_in(payload.email.lower(), payload.password)
        except CognitoError as exc:
            if exc.code == "UserNotConfirmedException":
                return AuthResponse(needs_confirmation=True, message="Verify your email first.")
            raise HTTPException(401, "Email or password is incorrect.") from exc
        if user is None:
            raise HTTPException(401, "This Cognito account has no UniTask profile. Register first.")
        return AuthResponse(token=token, user=UserRead.model_validate(user))

    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Email or password is incorrect.")
    return AuthResponse(token=issue_token(user), user=UserRead.model_validate(user))


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)) -> User:
    return user
