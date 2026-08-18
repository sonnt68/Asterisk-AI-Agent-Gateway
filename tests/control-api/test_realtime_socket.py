from app.main import app
from app.security import issue_realtime_token
from app.settings import get_settings
from fastapi.testclient import TestClient


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
