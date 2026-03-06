"""
routes/reports.py — User report endpoints for TickerTap.

Allows authenticated users to submit bug reports and feature suggestions,
and unauthenticated users to submit activation-bug reports (with email).

Admin endpoints provide listing, updating, and deleting reports.

Routes:
  POST   /api/v1/reports              — Submit a new report (auth optional for activation_bug)
  GET    /api/v1/reports              — Admin: list all reports with optional filters
  PATCH  /api/v1/reports/{report_id}  — Admin: update report status / admin notes
  DELETE /api/v1/reports/{report_id}  — Admin: permanently delete a report

Rate limiting:
  - POST /reports: 5 per minute per IP (SlowAPI)

Authentication:
  - POST uses optional JWT extraction — authenticated users auto-fill user_id
    and email; unauthenticated callers may only submit activation_bug reports
    and must provide reporter_email in the request body.
  - GET, PATCH, DELETE require admin privileges (get_current_admin dependency).
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import decode_access_token
from ..db import get_db
from ..email import send_admin_report_notification
from ..limiter import limiter
from ..models import User, UserReport
from ..routes.auth_routes import get_current_admin
from ..schemas import UserReportAdminUpdate, UserReportCreate, UserReportOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_optional_user(
    request: Request, db: AsyncSession
) -> Optional[User]:
    """Attempt to extract the authenticated user from the Authorization header.

    This is a *soft* dependency — it never raises.  If the header is missing,
    malformed, or the token is invalid/expired, the function silently returns
    None so that the calling endpoint can decide whether anonymous access is
    acceptable for the given report type.

    Args:
        request: The incoming FastAPI request (used to read headers).
        db:      Async database session for the user lookup.

    Returns:
        The authenticated User if the token is valid, or None otherwise.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        return None

    # decode_access_token returns the subject (user_id string) or None.
    subject = decode_access_token(token)
    if subject is None:
        return None

    try:
        user_id = UUID(subject)
    except ValueError:
        return None

    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()

    # Inactive users are treated as unauthenticated.
    if user and not user.is_active:
        return None

    return user


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("", response_model=UserReportOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def create_report(
    body: UserReportCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Submit a bug report, feature suggestion, or activation-bug report.

    Authentication behaviour varies by report type:
      - **bug** / **suggestion**: Requires a valid JWT.  The user's ID and
        email are pulled from the token automatically.
      - **activation_bug**: May be submitted without authentication, but
        ``reporter_email`` must be provided in the body.  If a valid JWT is
        present it will still be used.

    After persisting the report, a fire-and-forget email notification is
    dispatched to the admin inbox (ADMIN_EMAIL env var).

    Args:
        body:    UserReportCreate with report_type, subject, body, and
                 optional reporter_email / category.
        request: FastAPI request — used for rate-limiter key extraction and
                 optional Authorization header parsing.
        db:      Async database session.

    Returns:
        UserReportOut — the newly created report.

    Raises:
        HTTPException 401: If the report type requires authentication and no
                           valid token is provided.
        HTTPException 422: If activation_bug is submitted without
                           reporter_email and no valid token.
    """
    # Honeypot detection — bots auto-fill hidden fields; humans leave them empty.
    if body.website:
        # Silently accept but don't persist — makes the bot think it succeeded.
        logger.info("Honeypot triggered: discarding report from %s", request.client.host)
        return UserReport(
            report_id=uuid.uuid4(),
            reporter_email=body.reporter_email or "bot@example.com",
            report_type=body.report_type,
            subject=body.subject,
            body=body.body,
            status="new",
            created_at=datetime.now(timezone.utc),
        )

    # Attempt to extract the user from the Authorization header (optional).
    # _get_optional_user (defined above) returns User or None without raising.
    user = await _get_optional_user(request, db)

    # Determine user_id and reporter_email based on auth state.
    if user is not None:
        # Authenticated — use token-derived identity regardless of report type.
        user_id = user.user_id
        reporter_email = user.email
    else:
        # Unauthenticated — only activation_bug is allowed without a token.
        if body.report_type != "activation_bug":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required for bug reports and suggestions.",
            )
        if not body.reporter_email:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="reporter_email is required for unauthenticated activation bug reports.",
            )
        user_id = None
        reporter_email = body.reporter_email

    # Persist the report.
    report = UserReport(
        user_id=user_id,
        reporter_email=reporter_email,
        report_type=body.report_type,
        category=body.category,
        subject=body.subject,
        body=body.body,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    logger.info(
        "Report created: report_id=%s type=%s email=%s",
        report.report_id,
        report.report_type,
        reporter_email,
    )

    # Fire-and-forget admin notification — failures are logged inside the
    # send_admin_report_notification function and do not affect the response.
    asyncio.create_task(
        send_admin_report_notification(
            report_type=body.report_type,
            subject=body.subject,
            reporter_email=reporter_email,
        )
    )

    return report


@router.get("", response_model=List[UserReportOut])
async def list_reports(
    request: Request,
    status_filter: Optional[str] = Query(
        None,
        alias="status",
        description="Filter by report status: new, reviewed, resolved, dismissed.",
    ),
    report_type: Optional[str] = Query(
        None,
        description="Filter by report type: bug, suggestion, activation_bug.",
    ),
    limit: int = Query(50, ge=1, le=200, description="Max records to return."),
    offset: int = Query(0, ge=0, description="Number of records to skip."),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """List all user-submitted reports (admin only).

    Supports optional filtering by status and report_type, with pagination
    via limit/offset.  Results are ordered by creation date descending
    (most recent first).

    Args:
        request:       FastAPI request (required for dependency injection).
        status_filter: Optional status to filter on (query param ``status``).
        report_type:   Optional report type to filter on.
        limit:         Max number of records to return (1-200, default 50).
        offset:        Number of records to skip (default 0).
        db:            Async database session.
        _admin:        Authenticated admin user (injected, unused in body).

    Returns:
        List of UserReportOut ordered by created_at descending.
    """
    query = select(UserReport).order_by(UserReport.created_at.desc())

    if status_filter is not None:
        query = query.where(UserReport.status == status_filter)
    if report_type is not None:
        query = query.where(UserReport.report_type == report_type)

    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    reports = result.scalars().all()

    return reports


@router.patch("/{report_id}", response_model=UserReportOut)
async def update_report(
    report_id: UUID,
    body: UserReportAdminUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Update a report's status and/or admin notes (admin only).

    If the status is set to ``resolved``, the ``resolved_at`` timestamp is
    automatically populated with the current UTC time.  Setting the status
    back to a non-resolved value clears ``resolved_at``.

    Args:
        report_id: UUID of the report to update.
        body:      UserReportAdminUpdate with optional status and admin_notes.
        request:   FastAPI request (required for dependency injection).
        db:        Async database session.
        _admin:    Authenticated admin user (injected, unused in body).

    Returns:
        The updated UserReportOut.

    Raises:
        HTTPException 404: If no report with the given ID exists.
    """
    # Fetch the existing report.
    result = await db.execute(
        select(UserReport).where(UserReport.report_id == report_id)
    )
    report = result.scalar_one_or_none()

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found.",
        )

    # Apply provided fields.
    if body.status is not None:
        report.status = body.status

        # Auto-set resolved_at when status transitions to "resolved".
        if body.status == "resolved":
            report.resolved_at = datetime.now(timezone.utc)
        else:
            # Clear resolved_at if status moves away from resolved.
            report.resolved_at = None

    if body.admin_notes is not None:
        report.admin_notes = body.admin_notes

    await db.commit()
    await db.refresh(report)

    logger.info(
        "Report updated: report_id=%s new_status=%s",
        report.report_id,
        report.status,
    )

    return report


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    report_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Permanently delete a report (admin only).

    This is a hard delete — the report row is removed from the database
    entirely.  Use PATCH to set status to ``dismissed`` if soft-delete
    semantics are preferred.

    Args:
        report_id: UUID of the report to delete.
        request:   FastAPI request (required for dependency injection).
        db:        Async database session.
        _admin:    Authenticated admin user (injected, unused in body).

    Returns:
        HTTP 204 No Content on success.

    Raises:
        HTTPException 404: If no report with the given ID exists.
    """
    result = await db.execute(
        select(UserReport).where(UserReport.report_id == report_id)
    )
    report = result.scalar_one_or_none()

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found.",
        )

    await db.delete(report)
    await db.commit()

    logger.info("Report deleted: report_id=%s", report_id)

    return None
