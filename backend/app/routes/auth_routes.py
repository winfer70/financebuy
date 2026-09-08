"""
auth_routes.py — Authentication endpoints and user dependency for TickerTap.

Provides /auth/register, /auth/login, /auth/forgot-password, /auth/reset-password
as well as the canonical get_current_user, get_current_admin, and
get_current_user_or_bot dependencies that all other route modules should use
(via dependencies.py re-export).

Security measures applied in this module:
  - Rate limiting: login 5/minute, register 3/minute (via SlowAPI)
  - Password reset tokens stored as SHA-256 hashes (raw token only in email)
  - Failed login attempts logged to audit_log
  - Constant-time password comparison via argon2-cffi

Environment variables:
  BOT_API_KEY   — shared secret checked against the X-Bot-Api-Key request header;
                  required for bot authentication (get_current_user_or_bot).
  BOT_USER_ID   — user_id placed in the bot identity dict returned by
                  get_current_user_or_bot when bot auth succeeds (optional).
"""

import asyncio
import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Union

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from ..auth import hash_password, verify_password, create_access_token, decode_access_token
from ..db import AsyncSessionLocal, get_db
from ..email import (
    send_deletion_cancellation_email,
    send_email_change_verification,
    send_password_reset_email,
    send_reactivation_email,
    send_verification_email,
)
from ..limiter import limiter
from ..models import AuditLog, EmailVerificationToken, PasswordResetToken, RefreshToken, User
from ..schemas import (
    AccountDeleteRequest,
    DeactivateRequest,
    EmailChangeRequest,
    ForgotPasswordRequest,
    ProfileUpdateRequest,
    ReactivationRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenActionRequest,
    UserCreate,
    UserOut,
    UserLogin,
    UserPreferences,
    UserPreferencesUpdate,
    UserProfileOut,
    TokenResponse,
    SUPPORTED_CURRENCIES,
    SUPPORTED_LANGUAGES,
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

# Optional variant used by get_current_user_or_bot — auto_error=False prevents
# FastAPI from raising 401 automatically when the Authorization header is absent,
# which is the normal case for bot requests that carry X-Bot-Api-Key instead.
_oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


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


async def get_current_user(
    token: str = Depends(oauth2_scheme),
) -> User:
    """FastAPI dependency that decodes the JWT and returns the active User.

    Opens a scoped session that closes immediately after the DB lookup so the
    connection is returned to the pool before any slow follow-on I/O (e.g.
    yfinance calls in market endpoints) begins.

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

    # Scoped session — connection is returned to the pool as soon as this
    # block exits, before the endpoint handler performs any yfinance I/O.
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user not found or inactive",
        )
    # Bind user_id to structlog context vars so all downstream log lines
    # within this request carry the authenticated user's identity.
    structlog.contextvars.bind_contextvars(user_id=str(user.user_id))
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


async def get_current_user_or_bot(
    request: Request,
    token: Optional[str] = Depends(_oauth2_scheme_optional),
) -> Union[User, dict]:
    """FastAPI dependency accepting either a bot API key or a JWT bearer token.

    Checks for an X-Bot-Api-Key header first.  If present and valid, returns a
    minimal bot identity dict without performing a database lookup.  If absent,
    falls through to standard JWT authentication and returns the User ORM object
    with an ``is_bot=False`` attribute appended as a dynamic Python attribute.

    Bot-related env vars consumed here:
      BOT_API_KEY  — required; shared secret expected in X-Bot-Api-Key header.
      BOT_USER_ID  — optional; user_id surfaced in the bot identity dict.

    Args:
        request: FastAPI Request — used to read the X-Bot-Api-Key header.
        token:   Optional Bearer token from the OAuth2 scheme (auto_error
                 disabled so the header may be absent on bot requests).

    Returns:
        dict with keys ``user_id`` and ``is_bot=True`` when bot auth succeeds,
        or a User ORM instance with ``is_bot=False`` set as a dynamic attribute
        when JWT auth succeeds.

    Raises:
        HTTP 401: Bot key present but invalid, or BOT_API_KEY env var not set.
        HTTP 401: No bot header and JWT token is missing, invalid, or expired.
    """
    bot_key_header = request.headers.get("X-Bot-Api-Key")

    if bot_key_header is not None:
        expected = os.getenv("BOT_API_KEY")
        if not expected or bot_key_header != expected:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid bot API key",
            )
        return {"user_id": os.getenv("BOT_USER_ID", ""), "is_bot": True}

    # No bot header — require a valid JWT and delegate to standard auth.
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await get_current_user(token=token)
    user.is_bot = False  # type: ignore[attr-defined]
    return user


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
        # Return the same response shape as a successful registration to prevent
        # email enumeration — but don't create a duplicate user or send an email.
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "message": "check your email to verify your account",
            },
        )

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone=payload.phone,
    )
    # Override model default — new registrations require email verification.
    user.email_verified = False

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

    # Generate a cryptographically-secure email verification token.
    # Only the SHA-256 hash is stored; the raw token is sent via email.
    raw_token = secrets.token_urlsafe(48)
    token_hash = _hash_token(raw_token)
    verification_record = EmailVerificationToken(
        user_id=user.user_id,
        token=token_hash,
        token_type="email_verify",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )

    db.add(user)
    db.add(audit)
    db.add(verification_record)
    await db.commit()
    await db.refresh(user)

    # Build the verification URL and attempt to send the email.
    app_url = os.getenv("APP_URL", "https://localhost")
    verify_url = f"{app_url}?verify_email={raw_token}"
    try:
        # send_verification_email(to_email, verify_url) — sends an HTML email
        # with a one-click verification button to the new user.
        await send_verification_email(user.email, verify_url)
    except Exception as exc:
        # Don't expose SMTP errors to the client, but log for debugging.
        logger.error("Failed to send verification email to %s: %s", user.email, exc)

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

    if not user:
        # Consume time equivalent to argon2 verify to prevent timing oracle
        # that could reveal whether an email is registered.
        try:
            verify_password("$argon2id$v=19$m=65536,t=3,p=4$dummy$dummy", payload.password)
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )

    # ── Account lockout check ───────────────────────────────────────────────
    if user.locked_until is not None:
        if user.locked_until > datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Account temporarily locked. Try again later.",
            )
        else:
            # Lock period has expired — reset counters.
            user.locked_until = None
            user.failed_login_attempts = 0

    # Allow deactivated and deletion-scheduled users to log in so the
    # frontend can display the correct account state.  Block only truly
    # disabled accounts (is_active=False without a recoverable reason).
    if (
        not user.is_active
        and user.deactivated_at is None
        and user.deletion_scheduled_at is None
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )

    if not verify_password(user.password_hash, payload.password):
        # Increment failed login counter and lock account after 10 failures.
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= 10:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)

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

    # ── Post-password checks (before issuing tokens) ─────────────────────

    # Reset failed login counter on successful authentication.
    user.failed_login_attempts = 0
    user.locked_until = None

    # A. Email verification gate — unverified accounts cannot authenticate.
    if not user.email_verified:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "email_not_verified", "email": user.email},
        )

    # B. Deactivation flag — allow login but inform frontend.
    account_deactivated = True if user.deactivated_at is not None else None

    # C. Deletion schedule flag — pass ISO timestamp to frontend.
    deletion_iso = (
        user.deletion_scheduled_at.isoformat()
        if user.deletion_scheduled_at is not None
        else None
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
        preferences=user.preferences or {},
        account_deactivated=account_deactivated,
        deletion_scheduled_at=deletion_iso,
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
    if not user:
        await db.delete(record)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user not found or inactive",
        )
    # Block truly disabled accounts but allow deactivated / deletion-scheduled
    # users to refresh so the frontend can display the correct account state.
    if (
        not user.is_active
        and user.deactivated_at is None
        and user.deletion_scheduled_at is None
    ):
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

    # Determine account state flags for the response.
    account_deactivated = True if user.deactivated_at is not None else None
    deletion_iso = (
        user.deletion_scheduled_at.isoformat()
        if user.deletion_scheduled_at is not None
        else None
    )

    return TokenResponse(
        access_token=new_access_token,
        user_id=user.user_id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        preferences=user.preferences or {},
        account_deactivated=account_deactivated,
        deletion_scheduled_at=deletion_iso,
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


# ── Profile & Preferences ────────────────────────────────────────────────────

@router.get("/me", response_model=UserProfileOut)
async def get_profile(current_user: User = Depends(get_current_user)):
    """Return the authenticated user's profile including preferences.

    The preferences JSONB column is merged with defaults so missing keys
    (e.g. for users created before the preferences migration) are populated.

    Returns:
        UserProfileOut with user identity fields and preferences.
    """
    raw = current_user.preferences or {}
    prefs = UserPreferences(**{
        "currency": raw.get("currency", "USD"),
        "language": raw.get("language", "en"),
        "sidebar_collapsed": raw.get("sidebar_collapsed", False),
        "tutorial_done": raw.get("tutorial_done", False),
    })
    return UserProfileOut(
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        phone=current_user.phone,
        user_id=current_user.user_id,
        kyc_status=current_user.kyc_status,
        is_active=current_user.is_active,
        preferences=prefs,
    )


@router.patch("/preferences", response_model=UserPreferences)
async def update_preferences(
    payload: UserPreferencesUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update the authenticated user's preferences.

    Only provided fields are merged into the existing preferences JSON.
    Validates that currency and language values are in the supported sets.

    Args:
        payload: Partial preferences update (currency and/or language).

    Returns:
        Updated UserPreferences object.

    Raises:
        HTTPException 400: If currency or language value is not supported.
    """
    if payload.currency and payload.currency not in SUPPORTED_CURRENCIES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported currency. Must be one of: {', '.join(sorted(SUPPORTED_CURRENCIES))}",
        )
    if payload.language and payload.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language. Must be one of: {', '.join(sorted(SUPPORTED_LANGUAGES))}",
        )

    existing = dict(current_user.preferences or {})
    if payload.currency:
        existing["currency"] = payload.currency
    if payload.language:
        existing["language"] = payload.language
    if payload.sidebar_collapsed is not None:
        existing["sidebar_collapsed"] = payload.sidebar_collapsed
    if payload.tutorial_done is not None:
        existing["tutorial_done"] = payload.tutorial_done

    current_user.preferences = existing
    await db.commit()
    await db.refresh(current_user)

    raw = current_user.preferences or {}
    return UserPreferences(
        currency=raw.get("currency", "USD"),
        language=raw.get("language", "en"),
        sidebar_collapsed=raw.get("sidebar_collapsed", False),
        tutorial_done=raw.get("tutorial_done", False),
    )


# ── Email Verification ───────────────────────────────────────────────────────

@router.post("/verify-email", status_code=200)
async def verify_email(
    payload: TokenActionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Consume an email verification token and mark the user as verified.

    The incoming raw token is hashed with SHA-256 before the database
    lookup so that a compromised database cannot be used to verify
    arbitrary accounts.

    Args:
        payload: TokenActionRequest containing the raw verification token.
        db: AsyncSession — injected database session.

    Returns:
        dict: {"detail": "Email verified successfully"}

    Raises:
        HTTP 400: Invalid, expired, or already-used verification token.
    """
    # Hash the incoming raw token to match what is stored in the database.
    incoming_hash = _hash_token(payload.token)
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token == incoming_hash,
            EmailVerificationToken.token_type == "email_verify",
            EmailVerificationToken.used == False,  # noqa: E712 — SQLAlchemy filter
            EmailVerificationToken.expires_at > now,
        )
    )
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token",
        )

    # Look up the owning user and flip the verification flag.
    user_result = await db.execute(
        select(User).where(User.user_id == record.user_id)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token",
        )

    record.used = True
    user.email_verified = True
    await db.commit()

    logger.info("Email verified for user %s", user.user_id)
    return {"detail": "Email verified successfully"}


@router.post("/resend-verification", status_code=200)
@limiter.limit("2/minute")
async def resend_verification(
    payload: ResendVerificationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Send a fresh verification email to an unverified account.

    Rate-limited to 2 requests per minute per IP to prevent abuse.
    Always returns 200 regardless of whether the email exists or is
    already verified, to prevent email enumeration.

    Args:
        payload: ResendVerificationRequest containing the email address.
        request: FastAPI Request — required by the rate limiter.
        db: AsyncSession — injected database session.

    Returns:
        dict: Generic success message (same for all cases).
    """
    _ANTI_ENUM_MSG = "If this email exists and is unverified, a new link has been sent"

    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    # Anti-enumeration: return the same 200 whether or not the user exists
    # or is already verified.
    if not user or user.email_verified:
        return {"detail": _ANTI_ENUM_MSG}

    # Generate a fresh verification token.
    raw_token = secrets.token_urlsafe(48)
    token_hash = _hash_token(raw_token)
    verification_record = EmailVerificationToken(
        user_id=user.user_id,
        token=token_hash,
        token_type="email_verify",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.add(verification_record)
    await db.commit()

    app_url = os.getenv("APP_URL", "https://localhost")
    verify_url = f"{app_url}?verify_email={raw_token}"
    try:
        # send_verification_email(to_email, verify_url) — sends HTML email
        # with a one-click verification button.
        await send_verification_email(user.email, verify_url)
    except Exception as exc:
        logger.error("Failed to resend verification email to %s: %s", user.email, exc)

    return {"detail": _ANTI_ENUM_MSG}


# ── Account Deactivation / Reactivation ──────────────────────────────────────

@router.post("/deactivate", status_code=200)
async def deactivate_account(
    payload: DeactivateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Deactivate the authenticated user's account.

    The user must confirm their password before deactivation.  The account
    becomes inactive and is timestamped so that it can be reactivated later
    via the /auth/request-reactivation flow.

    Args:
        payload: DeactivateRequest containing the current password.
        request: FastAPI Request — for audit logging.
        db: AsyncSession — injected database session.
        current_user: User — the authenticated user (from JWT).

    Returns:
        dict: {"detail": "Account deactivated"}

    Raises:
        HTTP 401: Incorrect password.
    """
    if not verify_password(current_user.password_hash, payload.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )

    current_user.is_active = False
    current_user.deactivated_at = datetime.now(timezone.utc)

    audit = AuditLog(
        user_id=current_user.user_id,
        action="account_deactivated",
        table_name="users",
        record_id=current_user.user_id,
        old_values={"is_active": True},
        new_values={"is_active": False},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(audit)
    await db.commit()

    logger.info("Account deactivated for user %s", current_user.user_id)
    return {"detail": "Account deactivated"}


@router.post("/request-reactivation", status_code=200)
@limiter.limit("3/minute")
async def request_reactivation(
    payload: ReactivationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Send a reactivation email to a deactivated account.

    Rate-limited to 3 requests per minute per IP.  Always returns 200
    regardless of whether the email exists or the account is deactivated,
    to prevent email enumeration.

    Args:
        payload: ReactivationRequest containing the email address.
        request: FastAPI Request — required by the rate limiter.
        db: AsyncSession — injected database session.

    Returns:
        dict: Generic success message (same for all cases).
    """
    _ANTI_ENUM_MSG = (
        "If this email is associated with a deactivated account, "
        "a reactivation link has been sent"
    )

    result = await db.execute(
        select(User).where(
            User.email == payload.email,
            User.deactivated_at.isnot(None),
        )
    )
    user = result.scalar_one_or_none()

    # Anti-enumeration: return the same 200 whether or not we found a match.
    if not user:
        return {"detail": _ANTI_ENUM_MSG}

    # Generate a one-time reactivation token (1 hour expiry).
    raw_token = secrets.token_urlsafe(48)
    token_hash = _hash_token(raw_token)
    reactivation_record = EmailVerificationToken(
        user_id=user.user_id,
        token=token_hash,
        token_type="reactivate",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(reactivation_record)
    await db.commit()

    app_url = os.getenv("APP_URL", "https://localhost")
    reactivate_url = f"{app_url}?reactivate={raw_token}"
    try:
        # send_reactivation_email(to_email, reactivate_url) — sends HTML email
        # with a one-click reactivation button.
        await send_reactivation_email(user.email, reactivate_url)
    except Exception as exc:
        logger.error("Failed to send reactivation email to %s: %s", user.email, exc)

    return {"detail": _ANTI_ENUM_MSG}


@router.post("/reactivate", status_code=200)
async def reactivate_account(
    payload: TokenActionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Consume a reactivation token and restore the user's account.

    The incoming raw token is hashed with SHA-256 before lookup.  On
    success the account is set back to active and the deactivated_at
    timestamp is cleared.

    Args:
        payload: TokenActionRequest containing the raw reactivation token.
        db: AsyncSession — injected database session.

    Returns:
        dict: {"detail": "Account reactivated successfully"}

    Raises:
        HTTP 400: Invalid, expired, or already-used reactivation token.
    """
    incoming_hash = _hash_token(payload.token)
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token == incoming_hash,
            EmailVerificationToken.token_type == "reactivate",
            EmailVerificationToken.used == False,  # noqa: E712
            EmailVerificationToken.expires_at > now,
        )
    )
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reactivation token",
        )

    user_result = await db.execute(
        select(User).where(User.user_id == record.user_id)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reactivation token",
        )

    user.is_active = True
    user.deactivated_at = None
    record.used = True
    await db.commit()

    logger.info("Account reactivated for user %s", user.user_id)
    return {"detail": "Account reactivated successfully"}


# ── Account Deletion ─────────────────────────────────────────────────────────

@router.post("/delete-account", status_code=200)
async def delete_account(
    payload: AccountDeleteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete the authenticated user's account (permanent or soft).

    Requires password re-confirmation.  Two modes are supported:

    - **permanent**: The user record and all cascaded data are deleted
      immediately.  This action is irreversible.
    - **soft**: The account is deactivated and scheduled for purging in
      30 days.  A cancellation email is sent so the user can undo the
      request within the grace period.

    Args:
        payload: AccountDeleteRequest with mode ("permanent"|"soft") and password.
        request: FastAPI Request — for audit logging.
        db: AsyncSession — injected database session.
        current_user: User — the authenticated user (from JWT).

    Returns:
        dict: Confirmation message (varies by mode).

    Raises:
        HTTP 401: Incorrect password.
    """
    if not verify_password(current_user.password_hash, payload.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )

    if payload.mode == "permanent":
        # Immediate irreversible deletion — CASCADE will clean up related rows.
        audit = AuditLog(
            user_id=current_user.user_id,
            action="account_deleted_permanent",
            table_name="users",
            record_id=current_user.user_id,
            old_values={"email": current_user.email},
            new_values=None,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.add(audit)
        await db.delete(current_user)
        await db.commit()

        logger.info("Account permanently deleted for user %s", current_user.user_id)
        return {"detail": "Account permanently deleted"}

    # ── Soft deletion: schedule purge in 30 days ─────────────────────────
    deletion_at = datetime.now(timezone.utc) + timedelta(days=30)
    current_user.deletion_scheduled_at = deletion_at
    current_user.is_active = False

    # Generate a cancellation token so the user can undo within 30 days.
    raw_token = secrets.token_urlsafe(48)
    token_hash = _hash_token(raw_token)
    cancel_record = EmailVerificationToken(
        user_id=current_user.user_id,
        token=token_hash,
        token_type="cancel_deletion",
        expires_at=deletion_at,  # Same 30-day window as the deletion schedule
    )

    audit = AuditLog(
        user_id=current_user.user_id,
        action="account_deletion_scheduled",
        table_name="users",
        record_id=current_user.user_id,
        old_values=None,
        new_values={"deletion_scheduled_at": deletion_at.isoformat()},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(cancel_record)
    db.add(audit)
    await db.commit()

    # Send the cancellation email so the user can reverse the decision.
    app_url = os.getenv("APP_URL", "https://localhost")
    cancel_url = f"{app_url}?cancel_deletion={raw_token}"
    try:
        # send_deletion_cancellation_email(to_email, cancel_url) — sends HTML
        # email with a one-click button to cancel the scheduled deletion.
        await send_deletion_cancellation_email(current_user.email, cancel_url)
    except Exception as exc:
        logger.error(
            "Failed to send deletion cancellation email to %s: %s",
            current_user.email,
            exc,
        )

    logger.info("Account deletion scheduled for user %s at %s", current_user.user_id, deletion_at)
    return {
        "detail": "Account scheduled for deletion in 30 days",
        "deletion_scheduled_at": deletion_at.isoformat(),
    }


@router.post("/cancel-deletion", status_code=200)
async def cancel_deletion(
    payload: TokenActionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Consume a cancellation token and restore a deletion-scheduled account.

    The incoming raw token is hashed with SHA-256 before lookup.  On
    success the account is reactivated and the deletion schedule is cleared.

    Args:
        payload: TokenActionRequest containing the raw cancellation token.
        db: AsyncSession — injected database session.

    Returns:
        dict: {"detail": "Account deletion cancelled"}

    Raises:
        HTTP 400: Invalid, expired, or already-used cancellation token.
    """
    incoming_hash = _hash_token(payload.token)
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token == incoming_hash,
            EmailVerificationToken.token_type == "cancel_deletion",
            EmailVerificationToken.used == False,  # noqa: E712
            EmailVerificationToken.expires_at > now,
        )
    )
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired cancellation token",
        )

    user_result = await db.execute(
        select(User).where(User.user_id == record.user_id)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired cancellation token",
        )

    user.is_active = True
    user.deletion_scheduled_at = None
    record.used = True
    await db.commit()

    logger.info("Account deletion cancelled for user %s", user.user_id)
    return {"detail": "Account deletion cancelled"}


# ── Profile Management ────────────────────────────────────────────────────────

@router.patch("/profile", response_model=UserProfileOut)
async def update_profile(
    payload: ProfileUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update the authenticated user's profile (first name, last name).

    Only non-None fields in the payload are applied, leaving other
    profile attributes unchanged.

    Args:
        payload: ProfileUpdateRequest with optional first_name and last_name.
        db: AsyncSession — injected database session.
        current_user: User — the authenticated user (from JWT).

    Returns:
        UserProfileOut — the full updated profile including preferences.
    """
    # Apply only the fields that were explicitly provided.
    if payload.first_name is not None:
        current_user.first_name = payload.first_name
    if payload.last_name is not None:
        current_user.last_name = payload.last_name

    await db.commit()
    await db.refresh(current_user)

    # Merge preferences with defaults (same pattern as GET /auth/me).
    raw = current_user.preferences or {}
    prefs = UserPreferences(**{
        "currency": raw.get("currency", "USD"),
        "language": raw.get("language", "en"),
        "sidebar_collapsed": raw.get("sidebar_collapsed", False),
        "tutorial_done": raw.get("tutorial_done", False),
    })
    return UserProfileOut(
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        phone=current_user.phone,
        user_id=current_user.user_id,
        kyc_status=current_user.kyc_status,
        is_active=current_user.is_active,
        preferences=prefs,
    )


# ── Email Change ──────────────────────────────────────────────────────────────

@router.post("/change-email", status_code=200)
async def change_email(
    payload: EmailChangeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Initiate an email address change for the authenticated user.

    Requires password re-confirmation.  A verification email is sent to
    the NEW address; the actual email swap only happens when the user
    clicks the link and calls /auth/confirm-email-change.

    Args:
        payload: EmailChangeRequest with new_email and current password.
        request: FastAPI Request — for audit logging.
        db: AsyncSession — injected database session.
        current_user: User — the authenticated user (from JWT).

    Returns:
        dict: {"detail": "Verification email sent to new address"}

    Raises:
        HTTP 401: Incorrect password.
        HTTP 400: New email is already in use by another account.
    """
    if not verify_password(current_user.password_hash, payload.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )

    # Ensure the new email is not already registered to another user.
    existing = await db.execute(
        select(User).where(User.email == payload.new_email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already in use",
        )

    # Generate a token with the new_email stored alongside it.
    raw_token = secrets.token_urlsafe(48)
    token_hash = _hash_token(raw_token)
    change_record = EmailVerificationToken(
        user_id=current_user.user_id,
        token=token_hash,
        token_type="email_change",
        new_email=payload.new_email,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    audit = AuditLog(
        user_id=current_user.user_id,
        action="email_change_requested",
        table_name="users",
        record_id=current_user.user_id,
        old_values={"email": current_user.email},
        new_values={"new_email": payload.new_email},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(change_record)
    db.add(audit)
    await db.commit()

    # Send verification to the NEW email address.
    app_url = os.getenv("APP_URL", "https://localhost")
    verify_url = f"{app_url}?confirm_email_change={raw_token}"
    try:
        # send_email_change_verification(to_email, verify_url) — sends HTML
        # email to the new address with a confirmation button.
        await send_email_change_verification(payload.new_email, verify_url)
    except Exception as exc:
        logger.error(
            "Failed to send email change verification to %s: %s",
            payload.new_email,
            exc,
        )

    return {"detail": "Verification email sent to new address"}


@router.post("/confirm-email-change", status_code=200)
async def confirm_email_change(
    payload: TokenActionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Consume an email-change token and update the user's email address.

    The new email is stored on the token record itself (new_email column)
    so that the swap is atomic and tamper-proof — the user cannot change
    the destination after requesting the change.

    Args:
        payload: TokenActionRequest containing the raw email-change token.
        db: AsyncSession — injected database session.

    Returns:
        dict: {"detail": "Email changed successfully"}

    Raises:
        HTTP 400: Invalid, expired, or already-used email-change token.
    """
    incoming_hash = _hash_token(payload.token)
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token == incoming_hash,
            EmailVerificationToken.token_type == "email_change",
            EmailVerificationToken.used == False,  # noqa: E712
            EmailVerificationToken.expires_at > now,
        )
    )
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired email change token",
        )

    # Retrieve the new email from the token record.
    new_email = record.new_email
    if not new_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired email change token",
        )

    user_result = await db.execute(
        select(User).where(User.user_id == record.user_id)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired email change token",
        )

    user.email = new_email
    record.used = True
    await db.commit()

    logger.info("Email changed for user %s to %s", user.user_id, new_email)
    return {"detail": "Email changed successfully"}


# ── Deletion Purge Background Task ───────────────────────────────────────────

async def _deletion_purge_loop():
    """Runs daily.  Deletes users whose deletion_scheduled_at is in the past.

    This background coroutine sleeps for 24 hours between each sweep.
    It opens its own database session (independent of any request) and
    queries for users whose soft-deletion grace period has expired,
    then removes them via CASCADE.
    """
    while True:
        # Sleep first so the app has time to finish startup before the
        # first purge cycle.
        await asyncio.sleep(86400)  # 24 hours

        try:
            async with AsyncSessionLocal() as session:
                now = datetime.now(timezone.utc)
                result = await session.execute(
                    select(User).where(
                        User.deletion_scheduled_at.isnot(None),
                        User.deletion_scheduled_at <= now,
                    )
                )
                expired_users = result.scalars().all()

                for user in expired_users:
                    logger.info(
                        "Purging deletion-scheduled user %s (scheduled at %s)",
                        user.user_id,
                        user.deletion_scheduled_at,
                    )
                    await session.delete(user)

                await session.commit()
                logger.info("Deletion purge cycle complete — %d users removed", len(expired_users))
        except Exception as exc:
            # Never crash the background loop; log and retry next cycle.
            logger.error("Deletion purge cycle failed: %s", exc)


def register_deletion_purge(app):
    """Register the daily deletion-purge background task on app startup.

    Call this function from main.py (or wherever the FastAPI app is
    assembled) to enable automatic purging of soft-deleted accounts.

    Args:
        app: The FastAPI application instance.
    """

    @app.on_event("startup")
    async def _start_purge():
        """Launch the deletion purge loop as a fire-and-forget background task."""
        asyncio.create_task(_deletion_purge_loop())

