"""
admin.py — Admin-only routes for TickerTap.

Provides endpoints for user and account management, and audit log access.
All routes require the requesting user to be listed in ADMIN_EMAILS.

Shared helpers (P7.7-P7.8):
  _toggle_user_status  — centralised logic for locking/unlocking users
  _toggle_account_status — centralised logic for locking/unlocking accounts
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Account, AuditLog, User
from ..schemas import AccountOut, AuditLogOut, UserOut
from .auth_routes import get_current_admin


router = APIRouter(prefix="/admin", tags=["admin"])


# ── Shared helpers ────────────────────────────────────────────────────────────

async def _toggle_user_status(
    user_id: UUID,
    new_status: bool,
    action: str,
    admin: User,
    request: Request,
    db: AsyncSession,
) -> User:
    """Lock or unlock a user account atomically.

    Eliminates duplication between lock_user and unlock_user — both
    operations follow the same select-for-update → mutate → audit → commit
    pattern (P7.7).

    Args:
        user_id: UUID of the user to modify.
        new_status: True to activate, False to deactivate.
        action: Audit log action string, e.g. 'user_lock' or 'user_unlock'.
        admin: The admin User performing the action.
        request: FastAPI Request — captured for the audit log IP/agent.
        db: AsyncSession — injected database session.

    Returns:
        The updated User ORM instance.

    Raises:
        HTTPException(404): User not found.
    """
    result = await db.execute(select(User).where(User.user_id == user_id).with_for_update())
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

    old_values = {"is_active": target.is_active}
    target.is_active = new_status

    audit = AuditLog(
        user_id=admin.user_id,
        action=action,
        table_name="users",
        record_id=target.user_id,
        old_values=old_values,
        new_values={"is_active": target.is_active},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    async with db.begin():
        db.add(target)
        db.add(audit)

    await db.refresh(target)
    return target


async def _toggle_account_status(
    account_id: UUID,
    new_status: str,
    action: str,
    admin: User,
    request: Request,
    db: AsyncSession,
) -> Account:
    """Lock or unlock a brokerage account atomically.

    Eliminates duplication between lock_account and unlock_account (P7.8).

    Args:
        account_id: UUID of the account to modify.
        new_status: New status string, e.g. 'locked' or 'active'.
        action: Audit log action string, e.g. 'account_lock'.
        admin: The admin User performing the action.
        request: FastAPI Request — captured for the audit log IP/agent.
        db: AsyncSession — injected database session.

    Returns:
        The updated Account ORM instance.

    Raises:
        HTTPException(404): Account not found.
    """
    result = await db.execute(
        select(Account).where(Account.account_id == account_id).with_for_update()
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")

    old_values = {"status": account.status}
    account.status = new_status

    audit = AuditLog(
        user_id=admin.user_id,
        action=action,
        table_name="accounts",
        record_id=account.account_id,
        old_values=old_values,
        new_values={"status": account.status},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    async with db.begin():
        db.add(account)
        db.add(audit)

    await db.refresh(account)
    return account


# ── User management endpoints ─────────────────────────────────────────────────

@router.get("/users", response_model=list[UserOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """List all registered users, ordered newest-first.

    Args:
        db: AsyncSession — injected database session.
        admin: Authenticated admin user (from JWT + ADMIN_EMAILS check).

    Returns:
        List[UserOut] — all users ordered by creation date descending.
    """
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return result.scalars().all()


@router.post("/users/{user_id}/lock", response_model=UserOut)
async def lock_user(
    user_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Deactivate a user account, preventing further login.

    Existing JWT tokens remain valid until their 60-minute natural expiry.
    An audit log entry is created with the old and new is_active values.

    Args:
        user_id: UUID of the user to lock.
        request: FastAPI Request — captured for the audit log.
        db: AsyncSession — injected database session.
        admin: Authenticated admin user.

    Returns:
        UserOut — updated user with is_active=False.

    Raises:
        HTTPException(404): User not found.
    """
    return await _toggle_user_status(
        user_id=user_id,
        new_status=False,
        action="user_lock",
        admin=admin,
        request=request,
        db=db,
    )


@router.post("/users/{user_id}/unlock", response_model=UserOut)
async def unlock_user(
    user_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Reactivate a previously locked user account.

    Args:
        user_id: UUID of the user to unlock.
        request: FastAPI Request — captured for the audit log.
        db: AsyncSession — injected database session.
        admin: Authenticated admin user.

    Returns:
        UserOut — updated user with is_active=True.

    Raises:
        HTTPException(404): User not found.
    """
    return await _toggle_user_status(
        user_id=user_id,
        new_status=True,
        action="user_unlock",
        admin=admin,
        request=request,
        db=db,
    )


# ── Account management endpoints ──────────────────────────────────────────────

@router.post("/accounts/{account_id}/lock", response_model=AccountOut)
async def lock_account(
    account_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Set an account's status to 'locked', blocking trading operations.

    Args:
        account_id: UUID of the account to lock.
        request: FastAPI Request — captured for the audit log.
        db: AsyncSession — injected database session.
        admin: Authenticated admin user.

    Returns:
        AccountOut — updated account with status='locked'.

    Raises:
        HTTPException(404): Account not found.
    """
    return await _toggle_account_status(
        account_id=account_id,
        new_status="locked",
        action="account_lock",
        admin=admin,
        request=request,
        db=db,
    )


@router.post("/accounts/{account_id}/unlock", response_model=AccountOut)
async def unlock_account(
    account_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Restore an account's status to 'active', re-enabling trading.

    Args:
        account_id: UUID of the account to unlock.
        request: FastAPI Request — captured for the audit log.
        db: AsyncSession — injected database session.
        admin: Authenticated admin user.

    Returns:
        AccountOut — updated account with status='active'.

    Raises:
        HTTPException(404): Account not found.
    """
    return await _toggle_account_status(
        account_id=account_id,
        new_status="active",
        action="account_unlock",
        admin=admin,
        request=request,
        db=db,
    )


# ── Audit log endpoint ────────────────────────────────────────────────────────

@router.get("/audit-logs", response_model=list[AuditLogOut])
async def list_audit_logs(
    user_id: Optional[UUID] = Query(default=None, description="Filter by user UUID."),
    action: Optional[str] = Query(default=None, description="Filter by action name."),
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum entries to return."),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Retrieve audit log entries for admin review.

    Args:
        user_id: Optional — filter to a specific user's actions.
        action: Optional — filter to a specific action type.
        limit: Maximum entries to return (1–1000, default 100).
        db: AsyncSession — injected database session.
        admin: Authenticated admin user.

    Returns:
        List[AuditLogOut] — audit entries ordered newest-first.
    """
    query = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)

    if user_id is not None:
        query = query.where(AuditLog.user_id == user_id)
    if action is not None:
        query = query.where(AuditLog.action == action)

    result = await db.execute(query)
    return result.scalars().all()

