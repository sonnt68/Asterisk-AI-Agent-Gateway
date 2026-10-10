import pytest
from app.main import app
from app.realtime_registry import registry
from app.security import issue_realtime_token
from app.settings import get_settings
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


def test_realtime_socket_registers_matching_agent() -> None:
    token = issue_realtime_token(
        {
            "organization_id": "org_1",
            "partner_app_id": "app_1",
            "agent_slug": "support-agent",
            "scopes": "calls:read,media:stream",
        },
        get_settings(),
    )
    with TestClient(app).websocket_connect(f"/v1/realtime?token={token}") as socket:
        socket.send_json(
            {"type": "session.register", "agent_slug": "support-agent", "protocol_version": "1"}
        )

        assert socket.receive_json()["type"] == "session.ready"


def test_realtime_socket_rejects_unknown_control_command() -> None:
    token = issue_realtime_token(
        {
            "organization_id": "org_1",
            "partner_app_id": "app_1",
            "agent_slug": "support-agent",
            "scopes": "calls:read",
        },
        get_settings(),
    )
    with TestClient(app).websocket_connect(f"/v1/realtime?token={token}") as socket:
        socket.send_json(
            {"type": "session.register", "agent_slug": "support-agent", "protocol_version": "1"}
        )
        socket.receive_json()
        socket.send_json({"type": "call.control", "command": "not-a-command"})

        assert socket.receive_json()["code"] == "command-denied"


def test_realtime_socket_denies_playback_without_media_playback_scope() -> None:
    token = issue_realtime_token(
        {
            "organization_id": "org_1",
            "partner_app_id": "app_1",
            "agent_slug": "support-agent",
            "scopes": "calls:read,media:stream",
        },
        get_settings(),
    )
    with TestClient(app).websocket_connect(f"/v1/realtime?token={token}") as socket:
        socket.send_json(
            {"type": "session.register", "agent_slug": "support-agent", "protocol_version": "1"}
        )
        socket.receive_json()
        socket.send_json(
            {
                "type": "call.control",
                "call_id": "any",
                "command": "playback.start",
                "payload": {"media": "sound:hello"},
            }
        )

        denial = socket.receive_json()
        assert denial["code"] == "command-denied"
        assert "media:playback" in denial["message"]


def test_realtime_socket_denies_channel_variable_without_scope() -> None:
    token = issue_realtime_token(
        {
            "organization_id": "org_1",
            "partner_app_id": "app_1",
            "agent_slug": "support-agent",
            "scopes": "calls:read",
        },
        get_settings(),
    )
    with TestClient(app).websocket_connect(f"/v1/realtime?token={token}") as socket:
        socket.send_json(
            {"type": "session.register", "agent_slug": "support-agent", "protocol_version": "1"}
        )
        socket.receive_json()
        socket.send_json(
            {
                "type": "call.control",
                "call_id": "any",
                "command": "channel.set_var",
                "payload": {"variable": "AI_INTENT", "value": "x"},
            }
        )

        denial = socket.receive_json()
        assert denial["code"] == "command-denied"
        assert "channel:variables" in denial["message"]


def _takeover_token(agent_slug: str = "takeover-agent") -> str:
    return issue_realtime_token(
        {
            "organization_id": "org_1",
            "partner_app_id": "app_1",
            "agent_slug": agent_slug,
            "scopes": "calls:read",
        },
        get_settings(),
    )


def _register(socket: object, agent_slug: str = "takeover-agent") -> dict[str, object]:
    socket.send_json(  # type: ignore[attr-defined]
        {"type": "session.register", "agent_slug": agent_slug, "protocol_version": "1"}
    )
    return socket.receive_json()  # type: ignore[attr-defined]


def test_newest_registration_supersedes_the_old_connection_and_hangs_up_its_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hangups: list[tuple[str, str]] = []

    async def record(channel_id: str, command: str, payload: dict[str, object]) -> None:
        hangups.append((channel_id, command))

    monkeypatch.setattr("app.call_control.execute", record)
    token = _takeover_token()
    # One portal, so both sockets share the event loop as they do in production.
    with TestClient(app) as client:
        with client.websocket_connect(f"/v1/realtime?token={token}") as old:
            first = _register(old)
            assert first["type"] == "session.ready"
            old_connection = registry.connections[str(first["connection_id"])]
            call = registry.reserve_call(old_connection)
            call.channel_id = "chan-old"
            try:
                with client.websocket_connect(f"/v1/realtime?token={token}") as new:
                    second = _register(new)

                    assert second["type"] == "session.ready"
                    notice = old.receive_json()
                    assert notice["code"] == "session-superseded"
                    with pytest.raises(WebSocketDisconnect) as closed:
                        old.receive_json()
                    assert closed.value.code == 4409
                    assert hangups == [("chan-old", "call.hangup")]
                    assert registry.find_agent("takeover-agent").id == second["connection_id"]
            finally:
                registry.finish_call(call.id)
    assert registry.find_agent("takeover-agent") is None


def test_same_connection_registering_twice_is_still_refused() -> None:
    with TestClient(app).websocket_connect(
        f"/v1/realtime?token={_takeover_token()}"
    ) as socket:
        assert _register(socket)["type"] == "session.ready"

        assert _register(socket)["code"] == "agent-in-use"


class _LeaseMovedPresence:
    """A Redis lease taken over by a newer registration on another instance."""

    def __init__(self) -> None:
        self.unregistered: list[str] = []

    async def claim(self, agent_slug: str, connection_id: str) -> None:
        return None

    async def heartbeat(self, agent_slug: str, connection_id: str) -> str:
        return "superseded"

    async def unregister(self, agent_slug: str, connection_id: str) -> None:
        self.unregistered.append(connection_id)


def test_lease_taken_by_another_instance_closes_with_4409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    presence = _LeaseMovedPresence()
    monkeypatch.setattr(app.state, "presence", presence, raising=False)
    with TestClient(app).websocket_connect(
        f"/v1/realtime?token={_takeover_token()}"
    ) as socket:
        ready = _register(socket)
        socket.send_json({"type": "heartbeat"})

        assert socket.receive_json()["code"] == "session-superseded"
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
        assert closed.value.code == 4409
        assert presence.unregistered == [ready["connection_id"]]
    assert registry.find_agent("takeover-agent") is None
