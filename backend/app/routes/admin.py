from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Account, AuditLog, User
from ..schemas import AuditLogOut, AccountOut, UserOut
from .auth_routes import get_current_admin


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[UserOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return result.scalars().all()


@router.post("/users/{user_id}/lock", response_model=UserOut)
async def lock_user(
    user_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    result = await db.execute(select(User).where(User.user_id == user_id).with_for_update())
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

    old_values = {"is_active": target.is_active}
    target.is_active = False

    audit = AuditLog(
        user_id=admin.user_id,
        action="user_lock",
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


@router.post("/users/{user_id}/unlock", response_model=UserOut)
async def unlock_user(
    user_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    result = await db.execute(select(User).where(User.user_id == user_id).with_for_update())
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

    old_values = {"is_active": target.is_active}
    target.is_active = True

    audit = AuditLog(
        user_id=admin.user_id,
        action="user_unlock",
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


@router.post("/accounts/{account_id}/lock", response_model=AccountOut)
async def lock_account(
    account_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    result = await db.execute(
        select(Account).where(Account.account_id == account_id).with_for_update()
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")

    old_values = {"status": account.status}
    account.status = "locked"

    audit = AuditLog(
        user_id=admin.user_id,
        action="account_lock",
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


@router.post("/accounts/{account_id}/unlock", response_model=AccountOut)
async def unlock_account(
    account_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    result = await db.execute(
        select(Account).where(Account.account_id == account_id).with_for_update()
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")

    old_values = {"status": account.status}
    account.status = "active"

    audit = AuditLog(
        user_id=admin.user_id,
        action="account_unlock",
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


@router.get("/audit-logs", response_model=list[AuditLogOut])
async def list_audit_logs(
    user_id: Optional[UUID] = Query(default=None),
    action: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    query = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)

    if user_id is not None:
        query = query.where(AuditLog.user_id == user_id)
    if action is not None:
        query = query.where(AuditLog.action == action)

    result = await db.execute(query)
    return result.scalars().all()

