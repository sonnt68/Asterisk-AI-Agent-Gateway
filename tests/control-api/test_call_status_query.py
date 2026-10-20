"""Scoped status reads and cancellation intent handling."""

import asyncio

import pytest
from app.call_signals import remember_completed
from app.realtime_control import handle_control
from app.realtime_registry import ActiveCall, Connection, ConnectionRegistry
from app.realtime_socket import cancel_outbound


class FakeSocket:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    async def send_json(self, payload: dict[str, object]) -> None:
        self.messages.append(payload)


def _connection(connection_id: str = "connection-1", scopes: set[str] | None = None) -> Connection:
    return Connection(
        id=connection_id,
        organization_id="org-1",
        partner_app_id="app-1",
        agent_slug="agent-1",
        scopes=scopes or {"calls:read", "calls:hangup", "calls:originate"},
        socket=FakeSocket(),
    )


def _call(connection: Connection, call_id: str = "call-1") -> ActiveCall:
    call = ActiveCall(call_id, "channel-1", connection.id, connection.agent_slug)
    call.status = "ringing"
    call.answered = False
    return call


def test_status_query_refreshes_when_request_id_is_already_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_registry = ConnectionRegistry()
    monkeypatch.setattr("app.realtime_control.registry", local_registry)
    connection = _connection(scopes={"calls:read"})
    call = _call(connection)
    local_registry.calls[call.id] = call
    connection.idempotency["same-request"] = {
        "type": "call.status",
        "call_id": call.id,
        "status": "stale",
    }

    asyncio.run(
        handle_control(
            connection,
            {"command": "call.status", "call_id": call.id, "request_id": "same-request"},
        )
    )

    response = connection.socket.messages[-1]  # type: ignore[attr-defined]
    assert response["type"] == "call.status"
    assert response["call_id"] == call.id
    assert response["status"] == "ringing"
    assert response["request_id"] == "same-request"


def test_status_query_returns_owned_completed_snapshot_and_rejects_foreign_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_registry = ConnectionRegistry()
    monkeypatch.setattr("app.realtime_control.registry", local_registry)
    connection = _connection(scopes={"calls:read"})
    local_registry.connections[connection.id] = connection
    finished = ActiveCall("finished", None, connection.id, connection.agent_slug)
    finished.status = "completed"
    finished.sequence = 4
    finished.answered = True
    finished.reason = "completed"
    finished.hangup_cause = 16
    finished.dial_status = "ANSWER"
    finished.updated_at = "2026-10-20T01:02:03+00:00"
    terminal = remember_completed(finished, local_registry)

    asyncio.run(
        handle_control(
            connection,
            {"command": "call.status", "call_id": "finished", "request_id": "fresh"},
        )
    )
    response = connection.socket.messages[-1]  # type: ignore[attr-defined]
    assert response == {**terminal, "request_id": "fresh"}

    foreign = _connection("connection-2")
    local_registry.calls["foreign"] = _call(foreign, "foreign")
    connection.completed_calls["foreign"] = terminal
    with pytest.raises(LookupError, match="No gateway call is available"):
        asyncio.run(
            handle_control(
                connection,
                {"command": "call.status", "call_id": "foreign"},
            )
        )


def test_call_hangup_sets_intent_and_rolls_it_back_when_ari_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_registry = ConnectionRegistry()
    monkeypatch.setattr("app.realtime_control.registry", local_registry)
    connection = _connection()
    call = _call(connection)
    call.answered = True
    call.requested_end_reason = "operator"
    local_registry.calls[call.id] = call

    async def fail_execute(*args: object, **kwargs: object) -> None:
        raise RuntimeError("ARI unavailable")

    monkeypatch.setattr("app.call_control.execute", fail_execute)
    with pytest.raises(RuntimeError, match="ARI unavailable"):
        asyncio.run(
            handle_control(
                connection,
                {"command": "call.hangup", "call_id": call.id},
            )
        )

    assert call.requested_end_reason == "operator"


def test_outbound_cancel_requires_scope_and_rolls_back_failed_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_registry = ConnectionRegistry()
    monkeypatch.setattr("app.realtime_socket.registry", local_registry)
    connection = _connection(scopes={"calls:read"})
    call = _call(connection)
    call.requested_end_reason = "previous"
    local_registry.calls[call.id] = call
    socket = FakeSocket()

    asyncio.run(cancel_outbound(socket, connection, {"call_id": call.id}))
    assert socket.messages[-1]["code"] == "command-denied"
    assert call.requested_end_reason == "previous"

    connection.scopes.add("calls:originate")

    async def fail_execute(*args: object, **kwargs: object) -> None:
        raise RuntimeError("ARI rejected hangup")

    monkeypatch.setattr("app.call_control.execute", fail_execute)
    asyncio.run(cancel_outbound(socket, connection, {"call_id": call.id}))

    assert socket.messages[-1]["code"] == "outbound-failed"
    assert call.requested_end_reason == "previous"


def test_outbound_cancel_has_no_synthetic_success_event(monkeypatch: pytest.MonkeyPatch) -> None:
    local_registry = ConnectionRegistry()
    monkeypatch.setattr("app.realtime_socket.registry", local_registry)
    connection = _connection()
    call = _call(connection)
    local_registry.calls[call.id] = call
    socket = FakeSocket()

    async def execute(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr("app.call_control.execute", execute)
    asyncio.run(cancel_outbound(socket, connection, {"call_id": call.id}))

    assert socket.messages == []
    assert call.requested_end_reason == "cancelled"
