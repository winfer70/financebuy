"""
auth_routes.py — Authentication endpoints and user dependency for TickerTap.

Provides /auth/register, /auth/login, /auth/forgot-password, /auth/reset-password
as well as the canonical get_current_user and get_current_admin dependencies that
all other route modules should use (via dependencies.py re-export).

Security measures applied in this module:
  - Rate limiting: login 5/minute, register 3/minute (via SlowAPI)
  - Password reset tokens stored as SHA-256 hashes (raw token only in email)
  - Failed login attempts logged to audit_log
  - Constant-time password comparison via argon2-cffi
"""

import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from ..auth import hash_password, verify_password, create_access_token, decode_access_token
from ..db import get_db
from ..email import send_password_reset_email
from ..limiter import limiter
from ..models import AuditLog, PasswordResetToken, User
from ..schemas import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    UserCreate,
    UserOut,
    UserLogin,
    TokenResponse,
)

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/auth", tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def _is_admin(user: User) -> bool:
    raw = os.getenv("ADMIN_EMAILS", "")
    emails = {e.strip().lower() for e in raw.split(",") if e.strip()}
    return user.email.lower() in emails


def _hash_token(raw_token: str) -> str:
    """Return the SHA-256 hex digest of a raw token string.

    Only the hash is persisted to the database; the raw token is sent to the
    user via email and never stored, so a compromised DB cannot be used to
    consume pending reset links.
    """
    return hashlib.sha256(raw_token.encode()).hexdigest()


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("3/minute")
async def register_user(
    payload: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user account.

    Rate-limited to 3 attempts per minute per IP to mitigate account-creation
    abuse and credential stuffing pre-registration.
    """
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user with this email already exists",
        )

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone=payload.phone,
    )

    audit = AuditLog(
        user_id=user.user_id,
        action="user_register",
        table_name="users",
        record_id=user.user_id,
        old_values=None,
        new_values={"email": user.email},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.add(user)
    db.add(audit)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(
    payload: UserLogin,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate a user and return a JWT access token.

    Rate-limited to 5 attempts per minute per IP to prevent brute-force
    attacks against login credentials.  Both user-not-found and wrong-password
    paths return the same 401 to avoid email enumeration.
    """
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )

    if not verify_password(user.password_hash, payload.password):
        # Log failed login for anomaly detection / brute-force alerting.
        failed_audit = AuditLog(
            user_id=user.user_id,
            action="login_failed",
            table_name="users",
            record_id=user.user_id,
            old_values=None,
            new_values={"email": user.email, "reason": "wrong_password"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.add(failed_audit)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )

    token = create_access_token(str(user.user_id))

    audit = AuditLog(
        user_id=user.user_id,
        action="login_success",
        table_name="users",
        record_id=user.user_id,
        old_values=None,
        new_values={"email": user.email},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(audit)
    await db.commit()

    return TokenResponse(
        access_token=token,
        user_id=user.user_id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
    )


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Initiate a password reset flow.

    Generates a cryptographically-random token, stores its SHA-256 hash in
    the database (never the raw token), and emails the raw token to the user.
    Always returns 200 regardless of whether the email exists, to prevent
    email enumeration.
    """
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    # Always return 200 to avoid leaking whether an email exists.
    if not user or not user.is_active:
        return {"detail": "If that email is registered you will receive a reset link shortly."}

    # Generate a high-entropy raw token — only ever sent to the user via email.
    raw_token = secrets.token_urlsafe(48)
    # Store the SHA-256 hash — a compromised DB cannot redeem pending links.
    token_hash = _hash_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    reset_record = PasswordResetToken(
        user_id=user.user_id,
        token=token_hash,   # hash stored, never the raw token
        expires_at=expires_at,
    )
    db.add(reset_record)
    await db.commit()

    app_url = os.getenv("APP_URL", "https://ticker-tap.com")
    # Raw token embedded in the URL sent to the user's inbox.
    reset_url = f"{app_url}?reset_token={raw_token}"

    try:
        await send_password_reset_email(user.email, reset_url)
    except Exception as exc:
        # Don't expose SMTP errors to the client, but log for debugging.
        logger.error("Failed to send password reset email to %s: %s", user.email, exc)

    return {"detail": "If that email is registered you will receive a reset link shortly."}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Consume a password reset token and update the user's password.

    The incoming raw token is hashed before the DB lookup — the database
    only ever contains hashes, so this comparison is safe even if the
    token column is somehow leaked.
    """
    # Hash the incoming raw token to match what is stored in the database.
    incoming_hash = _hash_token(payload.token)

    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token == incoming_hash)
    )
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token.")

    now = datetime.now(timezone.utc)
    if record.used or record.expires_at < now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token.")

    user_result = await db.execute(select(User).where(User.user_id == record.user_id))
    user = user_result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token.")

    user.password_hash = hash_password(payload.new_password)
    record.used = True
    await db.commit()

    return {"detail": "Password updated successfully."}


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency that decodes the JWT and returns the active User.

    Raises HTTP 401 if the token is missing, invalid, or the user is inactive.
    Import this via dependencies.py to keep route modules decoupled from the
    specific auth implementation.
    """
    subject = decode_access_token(token)
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token",
        )

    try:
        user_id = UUID(subject)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token subject",
        )

    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user not found or inactive",
        )
    return user


async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    """FastAPI dependency that requires admin privileges.

    Raises HTTP 403 if the authenticated user's email is not listed in the
    ADMIN_EMAILS environment variable.
    """
    if not _is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin privileges required",
        )
    return current_user
