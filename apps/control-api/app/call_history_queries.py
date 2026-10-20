"""Scoped history queries with bounded cursor and numbered pagination."""

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.call_history_schemas import (
    CallHistoryItem,
    CallHistoryPage,
    CallSignalItem,
    CallSignalPage,
    HistoryFilters,
    utc,
)
from app.models import CallRecord, CallSignal


@dataclass(frozen=True)
class HistoryAccess:
    organization_id: str
    partner_app_id: str | None = None
    include_imported: bool = False


def scoped_calls(access: HistoryAccess):
    query = select(CallRecord).where(CallRecord.organization_id == access.organization_id)
    if access.partner_app_id is not None:
        query = query.where(CallRecord.partner_app_id == access.partner_app_id)
    elif not access.include_imported:
        query = query.where(CallRecord.partner_app_id.is_not(None))
    return query


def encode_cursor(row: CallRecord) -> str:
    value = json.dumps([utc(row.created_at).isoformat(), row.call_id]).encode()
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def decode_cursor(value: str) -> tuple[datetime, str]:
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        decoded = json.loads(raw)
        if (
            not isinstance(decoded, list) or len(decoded) != 2
            or not all(isinstance(item, str) for item in decoded)
        ):
            raise ValueError
        timestamp, call_id = decoded
        when = datetime.fromisoformat(timestamp)
        if when.tzinfo is None:
            raise ValueError
        return utc(when), str(UUID(call_id))
    except (ValueError, TypeError, binascii.Error, UnicodeError):
        raise HTTPException(422, "Invalid history cursor") from None


def list_history(session: Session, access: HistoryAccess, filters: HistoryFilters) -> CallHistoryPage:
    query = scoped_calls(access)
    if filters.agent_slug:
        query = query.where(CallRecord.agent_slug == filters.agent_slug)
    if filters.status:
        query = query.where(CallRecord.status == filters.status)
    if filters.direction:
        query = query.where(CallRecord.direction == filters.direction)
    if filters.started_after:
        query = query.where(CallRecord.created_at >= filters.started_after)
    if filters.started_before:
        query = query.where(CallRecord.created_at <= filters.started_before)
    if filters.page is not None:
        total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = session.scalars(
            query.order_by(CallRecord.created_at.desc(), CallRecord.call_id.desc())
            .offset((filters.page - 1) * filters.limit).limit(filters.limit)
        )
        return CallHistoryPage(
            items=[CallHistoryItem.model_validate(row) for row in rows],
            next_cursor=None, page=filters.page, page_size=filters.limit,
            total=total, total_pages=max(1, (total + filters.limit - 1) // filters.limit),
        )
    if filters.cursor:
        when, call_id = decode_cursor(filters.cursor)
        query = query.where(or_(
            CallRecord.created_at < when,
            and_(CallRecord.created_at == when, CallRecord.call_id < call_id),
        ))
    query = query.order_by(CallRecord.created_at.desc(), CallRecord.call_id.desc())
    rows = list(session.scalars(query.limit(filters.limit + 1)))
    page = rows[:filters.limit]
    return CallHistoryPage(
        items=[CallHistoryItem.model_validate(row) for row in page],
        next_cursor=encode_cursor(page[-1]) if len(rows) > filters.limit else None,
    )


def list_history_agents(session: Session, access: HistoryAccess) -> list[str]:
    query = scoped_calls(access).with_only_columns(CallRecord.agent_slug).where(
        CallRecord.agent_slug.is_not(None)
    ).distinct().order_by(CallRecord.agent_slug)
    return list(session.scalars(query))


def get_history(session: Session, access: HistoryAccess, call_id: str) -> CallRecord:
    row = session.scalar(scoped_calls(access).where(CallRecord.call_id == call_id))
    if row is None:
        raise HTTPException(404, "Call not found")
    return row


def list_signals(
    session: Session, access: HistoryAccess, call_id: str, limit: int, cursor: str | None
) -> CallSignalPage:
    get_history(session, access, call_id)
    sequence = 0
    if cursor is not None:
        if not cursor.isascii() or not cursor.isdigit() or len(cursor) > 12:
            raise HTTPException(422, "Invalid signal cursor")
        sequence = int(cursor)
    query = select(CallSignal).where(
        CallSignal.call_id == call_id, CallSignal.sequence > sequence
    ).order_by(CallSignal.sequence).limit(limit + 1)
    rows = list(session.scalars(query))
    page = rows[:limit]
    return CallSignalPage(
        items=[CallSignalItem.model_validate(row) for row in page],
        next_cursor=str(page[-1].sequence) if len(rows) > limit else None,
    )
