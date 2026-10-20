"""Partner-safe call snapshots and normalization of Asterisk termination evidence."""

import logging
import time
from datetime import UTC, datetime

from app.realtime_registry import ActiveCall, ConnectionRegistry

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = {
    "completed", "busy", "no_answer", "rejected", "unavailable", "failed", "cancelled"
}
DIAL_STATUSES = {
    "RINGING", "PROGRESS", "PROCEEDING", "ANSWER", "BUSY", "NOANSWER", "CANCEL",
    "CHANUNAVAIL", "CONGESTION", "DONTCALL", "TORTURE", "INVALIDARGS",
}


def call_snapshot(call: ActiveCall) -> dict[str, object]:
    """Expose only gateway identity and normalized evidence, never PBX identifiers."""
    return {
        "type": "call.status",
        "call_id": call.id,
        "status": call.status,
        "sequence": call.sequence,
        "terminal": call.status in TERMINAL_STATUSES,
        "answered": call.answered,
        "reason": call.reason,
        "hangup_cause": call.hangup_cause,
        "dial_status": call.dial_status,
        "updated_at": call.updated_at,
    }


async def publish_status(
    call: ActiveCall, registry: ConnectionRegistry, status: str
) -> None:
    if call.status in TERMINAL_STATUSES or (call.status == status and call.sequence):
        return
    # Late ringing must not move an answered call backwards.
    if call.answered and status in {"dialing", "ringing"}:
        return
    call.status = status
    if status == "answered" and not call.answered:
        call.answered_at = datetime.now(UTC)
    call.answered = call.answered or status == "answered"
    if status in TERMINAL_STATUSES and call.ended_at is None:
        call.ended_at = datetime.now(UTC)
        call.duration_seconds = max(
            0, int((call.ended_at - call.created_at).total_seconds())
        )
        if call.answered_at:
            call.talk_seconds = max(
                0, int((call.ended_at - call.answered_at).total_seconds())
            )
    call.sequence += 1
    call.updated_at = datetime.now(UTC).isoformat()
    snapshot = call_snapshot(call)
    store = getattr(registry, "history_store", None)
    if store is not None:
        try:
            durable = await store.record(call, snapshot)
        except Exception:
            logger.exception(
                "call history transition failed call_id=%s sequence=%s",
                call.id,
                call.sequence,
            )
            durable = False
        if durable is False:
            logger.error(
                "call status sent without durable history call_id=%s sequence=%s",
                call.id,
                call.sequence,
            )
    connection = registry.connections.get(call.connection_id)
    if connection:
        if status in TERMINAL_STATUSES:
            # Publish only after the read path can find the final result.
            # send_json yields; a partner can query as soon as it sees this.
            remember_completed(call, registry)
        await connection.send_json(snapshot)


def termination(call: ActiveCall) -> tuple[str, str]:
    """Prefer explicit results; infer timeout only at the known originate deadline."""
    if call.requested_end_reason:
        return call.requested_end_reason, call.requested_end_reason
    if call.answered:
        return "completed", "normal_hangup"
    # Local originate can report generic Dial NOANSWER even for a precise
    # rejection/unavailable/network cause. Preserve the stronger evidence.
    causes = {
        1: "unavailable", 2: "unavailable", 3: "unavailable", 20: "unavailable",
        27: "unavailable", 17: "busy", 18: "no_answer", 19: "no_answer", 21: "rejected",
    }
    if status := causes.get(call.hangup_cause):
        return status, status
    if call.hangup_cause not in {None, 0, 16}:
        return "failed", "call_failed"
    dial_results = {
        "BUSY": "busy", "NOANSWER": "no_answer", "DONTCALL": "rejected",
        "TORTURE": "rejected", "CHANUNAVAIL": "unavailable",
    }
    if status := dial_results.get(call.dial_status):
        return status, status
    if call.dial_status == "CANCEL":
        return "cancelled", "cancelled"
    if call.hangup_cause in {None, 0} and call.dial_deadline is not None:
        if time.monotonic() >= call.dial_deadline:
            return "no_answer", "timeout"
    return "failed", "unknown" if call.hangup_cause in {None, 0} else "call_failed"


def remember_completed(call: ActiveCall, registry: ConnectionRegistry) -> dict[str, object]:
    snapshot = call_snapshot(call)
    connection = registry.connections.get(call.connection_id)
    if connection:
        if call.id not in connection.completed_calls and len(connection.completed_calls) >= 256:
            connection.completed_calls.pop(next(iter(connection.completed_calls)))
        connection.completed_calls[call.id] = snapshot
    return snapshot
