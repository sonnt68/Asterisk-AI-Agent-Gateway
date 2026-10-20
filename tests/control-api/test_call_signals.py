"""Partner-visible status ordering and normalized termination evidence."""

import asyncio

import pytest
from app.call_signals import publish_status, remember_completed, termination
from app.realtime_registry import ActiveCall, Connection, ConnectionRegistry


class CaptureSocket:
    def __init__(self, on_send=None) -> None:
        self.messages: list[dict[str, object]] = []
        self.on_send = on_send

    async def send_json(self, payload: dict[str, object]) -> None:
        self.messages.append(payload)
        if self.on_send:
            await self.on_send(payload)


def _connection(connection_id: str = "conn-1", socket=None) -> Connection:
    return Connection(
        id=connection_id,
        organization_id="org-1",
        partner_app_id="app-1",
        agent_slug="support-agent",
        scopes={"calls:read"},
        socket=socket or CaptureSocket(),
    )


@pytest.mark.parametrize(
    ("cause", "dial_status", "status", "reason"),
    [
        (17, None, "busy", "busy"),
        (None, "BUSY", "busy", "busy"),
        (18, None, "no_answer", "no_answer"),
        (19, None, "no_answer", "no_answer"),
        (21, None, "rejected", "rejected"),
        (1, None, "unavailable", "unavailable"),
        (0, None, "failed", "unknown"),
        (21, "NOANSWER", "rejected", "rejected"),
        (1, "NOANSWER", "unavailable", "unavailable"),
        (34, "NOANSWER", "failed", "call_failed"),
        (17, "NOANSWER", "busy", "busy"),
    ],
)
def test_termination_normalizes_ari_failure_evidence(cause, dial_status, status, reason):
    call = ActiveCall("call-1", "pbx-primary", "conn-1", "support-agent")
    call.hangup_cause = cause
    call.dial_status = dial_status

    assert termination(call) == (status, reason)


def test_termination_uses_deadline_for_cause_zero_timeout(monkeypatch: pytest.MonkeyPatch):
    call = ActiveCall("call-1", "pbx-primary", "conn-1", "support-agent")
    call.hangup_cause = 0
    call.dial_deadline = 100.0
    monkeypatch.setattr("app.call_signals.time.monotonic", lambda: 101.0)

    assert termination(call) == ("no_answer", "timeout")


def test_status_signals_are_ordered_deduplicated_and_never_regress():
    async def scenario() -> tuple[ActiveCall, list[dict[str, object]]]:
        registry = ConnectionRegistry()
        connection = _connection()
        registry.connections[connection.id] = connection
        call = ActiveCall("call-1", "pbx-primary", connection.id, connection.agent_slug)
        registry.calls[call.id] = call

        for status in ("dialing", "ringing", "answered", "ringing", "answered"):
            await publish_status(call, registry, status)

        return call, connection.socket.messages  # type: ignore[attr-defined]

    call, messages = asyncio.run(scenario())

    assert [message["status"] for message in messages] == [
        "dialing",
        "ringing",
        "answered",
    ]
    assert [message["sequence"] for message in messages] == [1, 2, 3]
    assert call.status == "answered"
    assert call.answered is True


def test_terminal_status_is_emitted_once():
    async def scenario() -> list[dict[str, object]]:
        registry = ConnectionRegistry()
        connection = _connection()
        registry.connections[connection.id] = connection
        call = ActiveCall("call-1", "pbx-primary", connection.id, connection.agent_slug)
        registry.calls[call.id] = call
        await publish_status(call, registry, "busy")
        await publish_status(call, registry, "failed")
        return connection.socket.messages  # type: ignore[attr-defined]

    messages = asyncio.run(scenario())
    assert [message["status"] for message in messages] == ["busy"]


def test_terminal_snapshot_is_cached_before_partner_send_yields():
    async def scenario() -> dict[str, object]:
        registry = ConnectionRegistry()
        send_started = asyncio.Event()
        release_send = asyncio.Event()
        observed: dict[str, object] = {}

        async def inspect_terminal(payload: dict[str, object]) -> None:
            if payload["type"] != "call.status":
                return
            observed["active"] = call.id in registry.calls
            observed["snapshot"] = dict(connection.completed_calls[call.id])
            send_started.set()
            await release_send.wait()

        connection = _connection(socket=CaptureSocket(inspect_terminal))
        registry.connections[connection.id] = connection
        call = ActiveCall("call-terminal", "pbx-primary", connection.id, connection.agent_slug)
        registry.calls[call.id] = call
        registry.finish_call(call.id)

        publish_task = asyncio.create_task(publish_status(call, registry, "busy"))
        await send_started.wait()
        assert observed["active"] is False
        assert observed["snapshot"]["status"] == "busy"  # type: ignore[index]
        assert observed["snapshot"]["call_id"] == call.id  # type: ignore[index]
        release_send.set()
        await publish_task
        return observed

    asyncio.run(scenario())


def test_remembering_existing_snapshot_does_not_evict_an_older_call():
    registry = ConnectionRegistry()
    connection = _connection()
    registry.connections[connection.id] = connection
    for index in range(256):
        connection.completed_calls[f"call-{index}"] = {
            "type": "call.status",
            "call_id": f"call-{index}",
            "status": "completed",
        }

    call = ActiveCall("call-100", "pbx-primary", connection.id, connection.agent_slug)
    call.status = "busy"
    call.sequence = 9
    remember_completed(call, registry)

    assert len(connection.completed_calls) == 256
    assert "call-0" in connection.completed_calls
    assert connection.completed_calls[call.id]["status"] == "busy"
    assert connection.completed_calls[call.id]["sequence"] == 9


def test_completed_snapshots_are_bounded_and_hide_pbx_channel_ids():
    registry = ConnectionRegistry()
    connection = _connection()
    registry.connections[connection.id] = connection

    for index in range(257):
        call = ActiveCall(
            f"call-{index}",
            f"pbx-primary-{index}",
            connection.id,
            connection.agent_slug,
        )
        call.other_channel_id = f"pbx-secondary-{index}"
        call.status = "completed"
        call.reason = "completed"
        call.answered = True
        call.sequence = 4
        remember_completed(call, registry)

    assert len(connection.completed_calls) == 256
    assert "call-0" not in connection.completed_calls
    assert "call-256" in connection.completed_calls
    for snapshot in connection.completed_calls.values():
        assert snapshot["type"] == "call.status"
        assert "channel_id" not in snapshot
        assert "other_channel_id" not in snapshot
        assert "pbx-" not in str(snapshot)
