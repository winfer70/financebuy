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

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from ..auth import hash_password, verify_password, create_access_token, decode_access_token
from ..db import get_db
from ..email import send_password_reset_email
from ..limiter import limiter
from ..models import AuditLog, PasswordResetToken, RefreshToken, User
from ..schemas import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    UserCreate,
    UserOut,
    UserLogin,
    TokenResponse,
)

# ── Refresh token configuration ──────────────────────────────────────────────
# Lifetime of the long-lived refresh token (default: 7 days).
_REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# Cookie settings for the refresh token — must be httpOnly and Secure in prod.
_REFRESH_COOKIE_NAME = "tickertap_refresh"
_COOKIE_SECURE = os.getenv("ENVIRONMENT", "development").lower() == "production"
_COOKIE_SAMESITE = "strict"

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


def _create_refresh_token_record(user_id: UUID) -> tuple[str, "RefreshToken"]:
    """Generate a refresh token and its DB record.

    Generates a cryptographically-secure raw token, computes its SHA-256
    hash, and returns both.  Only the hash is stored in the database.

    Args:
        user_id: UUID of the user this token belongs to.

    Returns:
        Tuple of (raw_token_string, RefreshToken ORM instance).
        The raw token must be set as an httpOnly cookie; never stored.
    """
    raw_token = secrets.token_urlsafe(64)
    token_hash = _hash_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(days=_REFRESH_TOKEN_EXPIRE_DAYS)
    record = RefreshToken(
        user_id=user_id,
        token=token_hash,
        expires_at=expires_at,
    )
    return raw_token, record


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(
    payload: UserLogin,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate a user and return a JWT access token + refresh cookie.

    Rate-limited to 5 attempts per minute per IP to prevent brute-force
    attacks.  Both user-not-found and wrong-password paths return the same
    401 to avoid email enumeration.

    The refresh token is set as an httpOnly, Secure, SameSite=Strict cookie
    (P6.3).  It is never included in the JSON response body.

    Args:
        payload: UserLogin — email and password.
        request: FastAPI Request — used to capture IP for the audit log.
        response: FastAPI Response — used to set the refresh token cookie.
        db: AsyncSession — injected database session.

    Returns:
        TokenResponse — short-lived access token plus user metadata.

    Raises:
        HTTP 401: Invalid credentials (same message for both failure modes).
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

    access_token = create_access_token(str(user.user_id))
    raw_refresh, refresh_record = _create_refresh_token_record(user.user_id)

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
    db.add(refresh_record)
    db.add(audit)
    await db.commit()

    # Set the refresh token in an httpOnly cookie — browser stores it
    # automatically and sends it on /auth/refresh calls.
    response.set_cookie(
        key=_REFRESH_COOKIE_NAME,
        value=raw_refresh,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite=_COOKIE_SAMESITE,
        max_age=_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/v1/auth",  # Scope cookie to auth routes only
    )

    return TokenResponse(
        access_token=access_token,
        user_id=user.user_id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_access_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Issue a new access token using the httpOnly refresh token cookie (P6.3).

    The refresh token is rotated on every successful call — the old token is
    deleted from the database and a new one is set in the cookie.  This
    limits the blast radius of a stolen refresh cookie.

    Args:
        request: FastAPI Request — to read the refresh cookie.
        response: FastAPI Response — to set the rotated refresh cookie.
        db: AsyncSession — injected database session.

    Returns:
        TokenResponse — new short-lived access token plus user metadata.

    Raises:
        HTTP 401: Missing, invalid, or expired refresh token.
    """
    raw_token = request.cookies.get(_REFRESH_COOKIE_NAME)
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="refresh token missing — please log in again",
        )

    token_hash = _hash_token(raw_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token == token_hash)
    )
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid refresh token",
        )

    now = datetime.now(timezone.utc)
    if record.expires_at < now:
        # Clean up the expired record
        await db.delete(record)
        await db.commit()
        response.delete_cookie(_REFRESH_COOKIE_NAME)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="refresh token expired — please log in again",
        )

    # Fetch the user linked to this refresh token
    user_result = await db.execute(
        select(User).where(User.user_id == record.user_id)
    )
    user = user_result.scalar_one_or_none()
    if not user or not user.is_active:
        await db.delete(record)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user not found or inactive",
        )

    # Rotate: delete old token and create a fresh one
    await db.delete(record)
    new_access_token = create_access_token(str(user.user_id))
    raw_refresh_new, new_refresh_record = _create_refresh_token_record(user.user_id)
    db.add(new_refresh_record)
    await db.commit()

    response.set_cookie(
        key=_REFRESH_COOKIE_NAME,
        value=raw_refresh_new,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite=_COOKIE_SAMESITE,
        max_age=_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/v1/auth",
    )

    return TokenResponse(
        access_token=new_access_token,
        user_id=user.user_id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Invalidate the user's refresh token and clear the cookie.

    Args:
        request: FastAPI Request — to read the refresh cookie.
        response: FastAPI Response — to clear the refresh cookie.
        db: AsyncSession — injected database session.
        current_user: User — the authenticated user (from JWT).

    Returns:
        dict: {"detail": "logged out"}
    """
    raw_token = request.cookies.get(_REFRESH_COOKIE_NAME)
    if raw_token:
        token_hash = _hash_token(raw_token)
        result = await db.execute(
            select(RefreshToken).where(RefreshToken.token == token_hash)
        )
        record = result.scalar_one_or_none()
        if record:
            await db.delete(record)
            await db.commit()

    # Clear the cookie regardless of whether we found a DB record
    response.delete_cookie(_REFRESH_COOKIE_NAME, path="/api/v1/auth")
    return {"detail": "logged out"}


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
