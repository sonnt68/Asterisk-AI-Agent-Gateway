"""ARI payload and side-effect ordering for outbound caller selection."""

import asyncio
from types import SimpleNamespace

import pytest
from app.outbound_number_policy import OutboundPolicy
from app.realtime_registry import Connection, ConnectionRegistry


class CaptureSocket:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    async def send_json(self, payload: dict[str, object]) -> None:
        self.messages.append(payload)


class Response:
    status = 201

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self):
        return {"id": "ari-call"}


class AriSession:
    instances: list["AriSession"] = []

    def __init__(self, *args, **kwargs):
        self.posts: list[tuple[str, dict[str, object]]] = []
        self.__class__.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def post(self, url: str, **kwargs):
        self.posts.append((url, kwargs))
        return Response()


def _connection() -> Connection:
    return Connection(
        id="connection-1",
        organization_id="org-1",
        partner_app_id="app-1",
        agent_slug="support-agent",
        scopes={"calls:originate"},
        socket=CaptureSocket(),
    )


def _message(**payload: object) -> dict[str, object]:
    return {
        "request_id": "request-1",
        "payload": {"context": "from-internal", "extension": "123", "timeout": 4, **payload},
    }


def _settings() -> SimpleNamespace:
    return SimpleNamespace(ari_base_url="http://ari.test", ari_username=None, ari_password=None)


def test_legacy_policy_omits_caller_id_and_preserves_ari_shape(monkeypatch: pytest.MonkeyPatch):
    from app import outbound_calls

    async def scenario():
        registry = ConnectionRegistry()
        connection = _connection()
        registry.connections[connection.id] = connection
        AriSession.instances.clear()
        monkeypatch.setattr(outbound_calls, "registry", registry)
        monkeypatch.setattr(
            outbound_calls,
            "resolve_outbound_policy_async",
            lambda *args, **kwargs: _legacy_policy(),
        )
        monkeypatch.setattr(outbound_calls, "get_settings", _settings)
        monkeypatch.setattr(outbound_calls.aiohttp, "ClientSession", AriSession)
        await outbound_calls.originate(connection, _message())
        return connection

    async def _legacy_policy() -> OutboundPolicy:
        return OutboundPolicy(frozenset({"from-internal:123"}), None)

    connection = asyncio.run(scenario())
    request = AriSession.instances[0].posts[0][1]
    assert "callerId" not in request["params"]
    assert "json" not in request
    assert connection.socket.messages[0]["type"] == "outbound.accepted"  # type: ignore[attr-defined]


def test_selected_policy_sends_exact_caller_id_and_freepbx_override(monkeypatch: pytest.MonkeyPatch):
    from app import outbound_calls

    async def scenario():
        registry = ConnectionRegistry()
        connection = _connection()
        registry.connections[connection.id] = connection
        requested: list[object] = []
        AriSession.instances.clear()

        async def policy(*args, **kwargs):
            requested.append(args[2] if len(args) > 2 else kwargs.get("caller_number"))
            return OutboundPolicy(frozenset({"from-internal:123"}), "+84900000051")

        monkeypatch.setattr(outbound_calls, "registry", registry)
        monkeypatch.setattr(outbound_calls, "resolve_outbound_policy_async", policy)
        monkeypatch.setattr(outbound_calls, "get_settings", _settings)
        monkeypatch.setattr(outbound_calls.aiohttp, "ClientSession", AriSession)
        await outbound_calls.originate(
            connection,
            _message(caller_number="+84900000051"),
        )
        return requested

    requested = asyncio.run(scenario())
    request = AriSession.instances[0].posts[0][1]
    assert requested == ["+84900000051"]
    assert request["params"]["callerId"] == "+84900000051"
    assert request["json"] == {"variables": {"__TRUNKCIDOVERRIDE": "+84900000051"}}


def test_selection_failure_happens_before_reservation_or_ari(monkeypatch: pytest.MonkeyPatch):
    from app import outbound_calls

    class NoSideEffectRegistry:
        calls: dict[str, object] = {}
        reserve_count = 0

        def reserve_call(self, connection):
            self.reserve_count += 1
            raise AssertionError("selection must fail before reservation")

    async def reject(*args, **kwargs):
        raise PermissionError("No enabled outbound caller number is available")

    registry = NoSideEffectRegistry()
    monkeypatch.setattr(outbound_calls, "registry", registry)
    monkeypatch.setattr(outbound_calls, "resolve_outbound_policy_async", reject)
    monkeypatch.setattr(
        outbound_calls.aiohttp,
        "ClientSession",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ARI must not run")),
    )

    with pytest.raises(PermissionError, match="No enabled"):
        asyncio.run(outbound_calls.originate(_connection(), _message()))
    assert registry.reserve_count == 0
