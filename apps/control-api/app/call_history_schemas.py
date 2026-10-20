"""Public metadata contracts for durable call history."""

from datetime import UTC, datetime
from typing import Literal

from fastapi import HTTPException, Query
from pydantic import BaseModel, ConfigDict, field_validator

CallStatus = Literal[
    "dialing", "ringing", "answered", "completed", "busy", "no_answer",
    "rejected", "unavailable", "failed", "cancelled",
]


class CallHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    call_id: str
    partner_app_id: str | None
    agent_slug: str | None
    direction: str
    source: str
    status: str
    terminal: bool
    answered: bool
    reason: str | None
    hangup_cause: int | None
    dial_status: str | None
    sequence: int
    created_at: datetime
    updated_at: datetime
    answered_at: datetime | None
    ended_at: datetime | None
    duration_seconds: float | None
    talk_seconds: float | None
    history_complete: bool

    @field_validator("created_at", "updated_at", "answered_at", "ended_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime | None) -> datetime | None:
        return utc(value) if value else None


class BrowserCallHistoryDetail(CallHistoryItem):
    """CMS-only detail fields omitted from partner and list contracts."""

    called_number: str | None
    routing_context: str | None


class CallSignalItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    type: str = "call.status"
    call_id: str
    status: str
    sequence: int
    terminal: bool
    answered: bool
    reason: str | None
    hangup_cause: int | None
    dial_status: str | None
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def timestamp_is_utc(cls, value: datetime) -> datetime:
        return utc(value)


class CallHistoryPage(BaseModel):
    items: list[CallHistoryItem]
    next_cursor: str | None
    page: int | None = None
    page_size: int | None = None
    total: int | None = None
    total_pages: int | None = None


class CallHistoryAgents(BaseModel):
    items: list[str]


class CallSignalPage(BaseModel):
    items: list[CallSignalItem]
    next_cursor: str | None


class HistoryFilters:
    def __init__(
        self,
        limit: int = Query(default=50, ge=1, le=100),
        cursor: str | None = Query(default=None, max_length=200),
        page: int | None = Query(default=None, ge=1, le=2147483647),
        agent_slug: str | None = Query(default=None, min_length=1, max_length=80),
        status: CallStatus | None = None,
        direction: Literal["inbound", "outbound", "unknown"] | None = None,
        started_after: datetime | None = None,
        started_before: datetime | None = None,
    ):
        if page is not None and cursor is not None:
            raise HTTPException(422, "Use either page or cursor pagination")
        for value in (started_after, started_before):
            if value and value.tzinfo is None:
                raise HTTPException(422, "History timestamps must include a timezone")
        if started_after and started_before and started_after > started_before:
            raise HTTPException(422, "started_after must not exceed started_before")
        self.limit, self.cursor = limit, cursor
        self.page, self.agent_slug = page, agent_slug
        self.status, self.direction = status, direction
        self.started_after, self.started_before = started_after, started_before


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
