"""Durable call records and ordered partner-safe status signals."""

import asyncio
import logging
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import CallRecord, CallSignal
from app.realtime_registry import ActiveCall

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _RecordPayload:
    call_id: str
    organization_id: str | None
    partner_app_id: str | None
    agent_slug: str | None
    called_number: str | None
    routing_context: str | None
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
    duration_seconds: int | None
    talk_seconds: int | None
    history_complete: bool = True


def _as_datetime(value: object, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return fallback
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return fallback


def _optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _snapshot_from_call(call: ActiveCall) -> dict[str, object]:
    terminal = call.status in {
        "completed", "busy", "no_answer", "rejected", "unavailable", "failed", "cancelled"
    }
    return {
        "status": call.status,
        "terminal": terminal,
        "answered": call.answered,
        "reason": call.reason,
        "hangup_cause": call.hangup_cause,
        "dial_status": call.dial_status,
        "sequence": call.sequence,
        "updated_at": call.updated_at,
    }


def _payload(call: ActiveCall, snapshot: dict[str, object]) -> _RecordPayload:
    now = datetime.now(UTC)
    status = str(snapshot.get("status") or call.status)
    terminal = bool(snapshot.get("terminal", status in {
        "completed", "busy", "no_answer", "rejected", "unavailable", "failed", "cancelled"
    }))
    answered = bool(snapshot.get("answered", call.answered))
    answered_at = call.answered_at
    ended_at = call.ended_at
    return _RecordPayload(
        call_id=call.id,
        organization_id=call.organization_id,
        partner_app_id=call.partner_app_id,
        agent_slug=call.agent_slug,
        called_number=call.called_number,
        routing_context=call.routing_context,
        direction=call.direction,
        source=call.source,
        status=status,
        terminal=terminal,
        answered=answered,
        reason=str(snapshot["reason"]) if snapshot.get("reason") is not None else call.reason,
        hangup_cause=_optional_int(snapshot.get("hangup_cause", call.hangup_cause)),
        dial_status=(
            str(snapshot["dial_status"])
            if snapshot.get("dial_status") is not None
            else call.dial_status
        ),
        sequence=int(snapshot.get("sequence", call.sequence)),
        created_at=_as_datetime(call.created_at, now),
        updated_at=_as_datetime(snapshot.get("updated_at", call.updated_at), now),
        answered_at=answered_at,
        ended_at=ended_at,
        duration_seconds=call.duration_seconds,
        talk_seconds=call.talk_seconds,
    )


class CallHistoryStore:
    """Async facade over the synchronous SQLAlchemy session factory.

    `start` is strict because an outbound call must never be originated without
    a durable owner. Later status writes retry a bounded number of times and
    remain pending when the database is unavailable so media cleanup can finish.
    """

    def __init__(
        self,
        session_factory: Callable[[], Session] | None = None,
        *,
        retry_attempts: int = 3,
        pending_limit: int = 1024,
    ) -> None:
        self.session_factory = session_factory or SessionLocal
        self.retry_attempts = max(1, retry_attempts)
        self.pending_limit = max(1, pending_limit)
        self._pending: OrderedDict[tuple[str, int], _RecordPayload] = OrderedDict()
        self._operation_lock = asyncio.Lock()

    async def start(self, call: ActiveCall) -> None:
        payload = _payload(call, _snapshot_from_call(call))
        try:
            async with self._operation_lock:
                await self._retry(lambda: self._start_sync(payload), "start")
        except Exception:
            logger.exception("call history start failed call_id=%s", call.id)
            raise RuntimeError("Call history is unavailable") from None

    async def record(self, call: ActiveCall, snapshot: dict[str, object]) -> bool:
        payload = _payload(call, snapshot)
        try:
            async with self._operation_lock:
                await self._retry(lambda: self._record_sync(payload), "record")
            return True
        except ValueError:
            logger.exception(
                "call history identity mismatch rejected call_id=%s sequence=%s",
                payload.call_id,
                payload.sequence,
            )
            return False
        except Exception:
            logger.exception(
                "call history signal queued after database failure call_id=%s sequence=%s",
                payload.call_id,
                payload.sequence,
            )
            self._queue_pending(payload)
            return False

    async def recover_interrupted(self) -> int:
        """Close records left active by a previous gateway process.

        Recovery records the observed restart time in `updated_at` but leaves
        ended and duration fields unset because no exact hangup was observed.
        """
        async with self._operation_lock:
            return await asyncio.to_thread(self._recover_sync)

    async def flush_pending(self) -> int:
        async with self._operation_lock:
            flushed = 0
            while self._pending:
                key, payload = next(iter(self._pending.items()))
                try:
                    await self._retry(lambda: self._record_sync(payload), "flush")
                except Exception:
                    logger.exception(
                        "pending call history signal remains unsaved call_id=%s sequence=%s",
                        payload.call_id,
                        payload.sequence,
                    )
                    break
                self._pending.pop(key, None)
                flushed += 1
            return flushed

    async def _retry(self, operation: Callable[[], Any], operation_name: str) -> Any:
        for attempt in range(self.retry_attempts):
            try:
                return await asyncio.to_thread(operation)
            except Exception:
                if attempt + 1 >= self.retry_attempts:
                    raise
                logger.warning(
                    "call history %s retry attempt=%s/%s",
                    operation_name,
                    attempt + 1,
                    self.retry_attempts - 1,
                )
                await asyncio.sleep(0.05 * (attempt + 1))
        raise RuntimeError("unreachable")

    def _queue_pending(self, payload: _RecordPayload) -> None:
        key = (payload.call_id, payload.sequence)
        self._pending[key] = payload
        self._pending.move_to_end(key)
        if len(self._pending) > self.pending_limit:
            dropped_key, dropped = self._pending.popitem(last=False)
            logger.error(
                "call history pending queue full; dropped call_id=%s sequence=%s",
                dropped.call_id,
                dropped_key[1],
            )

    def _start_sync(self, payload: _RecordPayload) -> None:
        with self.session_factory() as session:
            existing = session.get(CallRecord, payload.call_id)
            if existing:
                if (
                    existing.organization_id != payload.organization_id
                    or existing.partner_app_id != payload.partner_app_id
                    or existing.called_number != payload.called_number
                    or existing.routing_context != payload.routing_context
                    or existing.source != "gateway"
                ):
                    raise ValueError("Call history identity already belongs to another record")
                return
            self._insert_record(session, payload, include_signal=False)
            session.commit()

    def _record_sync(self, payload: _RecordPayload) -> None:
        with self.session_factory() as session:
            record = session.get(CallRecord, payload.call_id)
            if record is None:
                self._insert_record(session, payload, include_signal=payload.sequence >= 1)
                if payload.sequence >= 1:
                    session.flush()
                    created = session.get(CallRecord, payload.call_id)
                    if created is not None:
                        self._refresh_history_complete(session, created)
                session.commit()
                return
            if (
                record.organization_id != payload.organization_id
                or record.partner_app_id != payload.partner_app_id
                or record.called_number != payload.called_number
                or record.routing_context != payload.routing_context
            ):
                raise ValueError("Call history owner cannot change")
            if payload.sequence < record.sequence:
                # A concurrent writer may have advanced the latest record
                # first. Keep this older immutable signal even though it must
                # not move the latest snapshot backwards.
                if payload.sequence >= 1 and session.get(
                    CallSignal, (payload.call_id, payload.sequence)
                ) is None:
                    session.add(self._signal(payload))
                self._refresh_history_complete(session, record)
                session.commit()
                return
            self._update_record(record, payload)
            signal = session.get(CallSignal, (payload.call_id, payload.sequence))
            if payload.sequence >= 1 and signal is None:
                session.add(self._signal(payload))
            self._refresh_history_complete(session, record)
            session.commit()

    def _insert_record(
        self, session: Session, payload: _RecordPayload, *, include_signal: bool
    ) -> None:
        session.add(
            CallRecord(
                call_id=payload.call_id,
                organization_id=payload.organization_id,
                partner_app_id=payload.partner_app_id,
                agent_slug=payload.agent_slug,
                called_number=payload.called_number,
                routing_context=payload.routing_context,
                direction=payload.direction,
                source=payload.source,
                status=payload.status,
                terminal=payload.terminal,
                answered=payload.answered,
                reason=payload.reason,
                hangup_cause=payload.hangup_cause,
                dial_status=payload.dial_status,
                sequence=payload.sequence,
                created_at=payload.created_at,
                updated_at=payload.updated_at,
                answered_at=payload.answered_at,
                ended_at=payload.ended_at,
                duration_seconds=payload.duration_seconds,
                talk_seconds=payload.talk_seconds,
                history_complete=payload.history_complete,
            )
        )
        if include_signal:
            session.add(self._signal(payload))

    @staticmethod
    def _update_record(record: CallRecord, payload: _RecordPayload) -> None:
        for name in (
            "status", "terminal", "answered", "reason", "hangup_cause", "dial_status",
            "sequence", "updated_at", "answered_at", "ended_at", "duration_seconds",
            "talk_seconds",
        ):
            setattr(record, name, getattr(payload, name))

    @staticmethod
    def _signal(payload: _RecordPayload) -> CallSignal:
        return CallSignal(
            call_id=payload.call_id,
            sequence=payload.sequence,
            status=payload.status,
            terminal=payload.terminal,
            answered=payload.answered,
            reason=payload.reason,
            hangup_cause=payload.hangup_cause,
            dial_status=payload.dial_status,
            updated_at=payload.updated_at,
        )

    @staticmethod
    def _refresh_history_complete(session: Session, record: CallRecord) -> None:
        if record.source != "gateway" or record.sequence < 1:
            return
        session.flush()
        signal_count = session.scalar(
            select(func.count())
            .select_from(CallSignal)
            .where(
                CallSignal.call_id == record.call_id,
                CallSignal.sequence.between(1, record.sequence),
            )
        )
        record.history_complete = signal_count == record.sequence

    def _recover_sync(self) -> int:
        recovered = 0
        recovery_time = datetime.now(UTC)
        with self.session_factory() as session:
            records = session.scalars(
                select(CallRecord).where(
                    CallRecord.source == "gateway", CallRecord.terminal.is_(False)
                )
            ).all()
            for record in records:
                record.status = "failed"
                record.terminal = True
                record.reason = "gateway_restarted"
                record.history_complete = False
                record.sequence += 1
                record.updated_at = recovery_time
                session.add(
                    CallSignal(
                        call_id=record.call_id,
                        sequence=record.sequence,
                        status="failed",
                        terminal=True,
                        answered=record.answered,
                        reason="gateway_restarted",
                        hangup_cause=record.hangup_cause,
                        dial_status=record.dial_status,
                        updated_at=recovery_time,
                    )
                )
                recovered += 1
            session.commit()
        return recovered
