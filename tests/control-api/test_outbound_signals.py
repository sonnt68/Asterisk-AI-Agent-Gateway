"""Correlated ARI events and outbound originate lifecycle regression tests."""

import asyncio
from types import SimpleNamespace

import pytest
from app.call_lifecycle import CallLifecycle
from app.realtime_registry import ActiveCall, Connection, ConnectionRegistry


class CaptureSocket:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    async def send_json(self, payload: dict[str, object]) -> None:
        self.messages.append(payload)


class FakeAri:
    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.delete_sessions: list[object] = []
        self.delete_session_closed: list[bool | None] = []
        self.sessions: list[FakeSession] = []

    async def delete(self, session, path):
        self.deleted.append(path)
        self.delete_sessions.append(session)
        self.delete_session_closed.append(getattr(session, "closed", None))

    def session(self):
        session = FakeSession(204)
        self.sessions.append(session)
        return session


class FakeMedia:
    def __init__(self) -> None:
        self.closed: list[str] = []

    async def close(self, call: ActiveCall) -> None:
        self.closed.append(call.id)


class FakeResponse:
    def __init__(
        self,
        status: int,
        payload: dict[str, object] | None = None,
        on_enter=None,
        error: Exception | None = None,
    ):
        self.status = status
        self.payload = payload or {}
        self.on_enter = on_enter
        self.error = error

    async def __aenter__(self):
        if self.error:
            raise self.error
        if self.on_enter:
            await self.on_enter(self)
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self):
        return self.payload


class FakeSession:
    def __init__(self, status: int, on_post_enter=None, post_error: Exception | None = None) -> None:
        self.status = status
        self.on_post_enter = on_post_enter
        self.post_error = post_error
        self.closed = False
        self.posts: list[tuple[str, dict[str, object]]] = []
        self.deletes: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True
        return False

    def post(self, url: str, **kwargs):
        self.posts.append((url, kwargs))
        return FakeResponse(
            self.status,
            {"id": "ari-response-id"},
            self.on_post_enter,
            self.post_error,
        )

    def delete(self, url: str, **kwargs):
        self.deletes.append(url)
        return FakeResponse(204)


def _connection(connection_id: str = "conn-1") -> Connection:
    return Connection(
        id=connection_id,
        organization_id="org-1",
        partner_app_id="app-1",
        agent_slug="support-agent",
        scopes={"calls:originate", "calls:read"},
        socket=CaptureSocket(),
    )


def _lifecycle() -> tuple[CallLifecycle, ActiveCall, Connection]:
    lifecycle = CallLifecycle.__new__(CallLifecycle)
    lifecycle.registry = ConnectionRegistry()
    lifecycle.ari = FakeAri()
    lifecycle.media = FakeMedia()
    lifecycle.activated: list[str] = []
    lifecycle.activation_sessions: list[object] = []
    lifecycle.activation_session_closed: list[bool | None] = []

    async def activate(call, channel, connection, session):
        lifecycle.activated.append(call.id)
        lifecycle.activation_sessions.append(session)
        lifecycle.activation_session_closed.append(getattr(session, "closed", None))
        call.bridge_id = "bridge-1"

    lifecycle._activate_call = activate
    connection = _connection()
    lifecycle.registry.connections[connection.id] = connection
    call = ActiveCall("call-1", "primary-1", connection.id, connection.agent_slug)
    call.other_channel_id = "secondary-1"
    lifecycle.registry.calls[call.id] = call
    return lifecycle, call, connection


def test_dial_ringing_then_primary_answer_emits_status_and_activates():
    async def scenario():
        lifecycle, call, connection = _lifecycle()
        await lifecycle.on_ari_event(
            {
                "type": "StasisStart",
                "channel": {"id": "primary-1", "name": "Local/1", "state": "Ring"},
                "args": ["outbound", call.id],
            },
            None,
        )
        await lifecycle.on_ari_event(
            {"type": "Dial", "peer": {"id": "primary-1"}, "dialstatus": "RINGING"},
            None,
        )
        await lifecycle.on_ari_event(
            {
                "type": "ChannelStateChange",
                "channel": {"id": "primary-1", "state": "Up"},
            },
            None,
        )
        return call, connection.socket.messages  # type: ignore[attr-defined]

    call, messages = asyncio.run(scenario())
    assert [message["status"] for message in messages] == ["ringing", "answered"]
    assert call.status == "answered"
    assert call.answered is True
    assert call.bridge_id == "bridge-1"


@pytest.mark.parametrize(
    ("destroyed_channel", "cause", "status", "reason"),
    [("primary-1", 17, "busy", "busy"), ("media-1", 16, "failed", "media_failed")],
)
def test_primary_and_media_channel_destroy_use_distinct_terminal_paths(
    destroyed_channel, cause, status, reason
):
    async def scenario():
        lifecycle, call, connection = _lifecycle()
        call.media_channel_id = "media-1"
        await lifecycle.on_ari_event(
            {
                "type": "ChannelDestroyed",
                "channel": {"id": destroyed_channel},
                "cause": cause,
            },
            None,
        )
        return lifecycle, call, connection, connection.socket.messages  # type: ignore[attr-defined]

    lifecycle, call, connection, messages = asyncio.run(scenario())
    statuses = [message for message in messages if message["type"] == "call.status"]
    ended = [message for message in messages if message["type"] == "call.ended"]
    assert statuses[-1]["status"] == status
    assert ended == [{**statuses[-1], "type": "call.ended"}]
    assert call.reason == reason
    assert lifecycle.registry.calls == {}
    assert connection.completed_calls[call.id]["status"] == status
    assert "primary-1" not in str(connection.completed_calls[call.id])
    assert "media-1" not in str(connection.completed_calls[call.id])


def test_stasis_end_then_destroy_preserves_cause_and_emits_once():
    async def scenario():
        lifecycle, call, connection = _lifecycle()
        call.in_stasis = True
        await lifecycle.on_ari_event(
            {"type": "StasisEnd", "channel": {"id": "primary-1"}}, None
        )
        await lifecycle.on_ari_event(
            {
                "type": "ChannelDestroyed",
                "channel": {"id": "primary-1"},
                "cause": 17,
            },
            None,
        )
        await lifecycle.on_ari_event(
            {
                "type": "ChannelDestroyed",
                "channel": {"id": "primary-1"},
                "cause": 16,
            },
            None,
        )
        await asyncio.sleep(0)
        return call, connection.socket.messages  # type: ignore[attr-defined]

    call, messages = asyncio.run(scenario())
    assert call.hangup_cause == 17
    assert [
        message["status"] for message in messages if message["type"] == "call.status"
    ] == ["busy"]
    assert len([message for message in messages if message["type"] == "call.ended"]) == 1
    assert messages[-1]["reason"] == "busy"


def test_deferred_stasis_cleanup_uses_fresh_session_after_listener_closes():
    async def scenario():
        lifecycle, call, connection = _lifecycle()
        call.in_stasis = True
        listener_session = FakeSession(204)
        await listener_session.__aenter__()
        await lifecycle.on_ari_event(
            {"type": "StasisEnd", "channel": {"id": "primary-1"}},
            listener_session,
        )
        cleanup_task = call.end_task
        assert cleanup_task is not None
        await listener_session.__aexit__(None, None, None)
        await asyncio.sleep(0.25)
        await cleanup_task
        return lifecycle, call, connection, listener_session

    lifecycle, call, connection, listener_session = asyncio.run(scenario())
    messages = connection.socket.messages  # type: ignore[attr-defined]
    assert listener_session.closed is True
    assert lifecycle.registry.calls == {}
    assert len(lifecycle.ari.sessions) == 1
    cleanup_session = lifecycle.ari.sessions[0]
    assert cleanup_session.closed is True
    assert lifecycle.ari.delete_sessions
    assert all(session is cleanup_session for session in lifecycle.ari.delete_sessions)
    assert lifecycle.ari.delete_session_closed == [False] * len(lifecycle.ari.deleted)
    assert [message["type"] for message in messages] == ["call.status", "call.ended"]


def test_late_ringing_and_duplicate_up_do_not_regress_answered_state():
    async def scenario():
        lifecycle, call, connection = _lifecycle()
        call.in_stasis = True
        for event in (
            {
                "type": "ChannelStateChange",
                "channel": {"id": "primary-1", "state": "Up"},
            },
            {"type": "Dial", "peer": {"id": "primary-1"}, "dialstatus": "RINGING"},
            {
                "type": "ChannelStateChange",
                "channel": {"id": "primary-1", "state": "Up"},
            },
        ):
            await lifecycle.on_ari_event(event, None)
        return lifecycle, call, connection.socket.messages  # type: ignore[attr-defined]

    lifecycle, call, messages = asyncio.run(scenario())
    assert [message["status"] for message in messages] == ["answered"]
    assert call.status == "answered"
    assert lifecycle.activated == ["call-1"]


def test_pending_accepted_call_does_not_block_other_call_events():
    async def scenario():
        lifecycle, call_a, connection = _lifecycle()
        listener_session = FakeSession(204)
        await listener_session.__aenter__()
        call_a.channel_id = "primary-a"
        call_a.other_channel_id = "secondary-a"
        call_a.accepted = asyncio.Event()
        call_b = ActiveCall("call-b", "primary-b", connection.id, connection.agent_slug)
        call_b.other_channel_id = "secondary-b"
        call_b.in_stasis = True
        lifecycle.registry.calls[call_b.id] = call_b

        await lifecycle.on_ari_event(
            {"type": "Dial", "peer": {"id": "primary-a"}, "dialstatus": "RINGING"},
            listener_session,
        )
        assert call_a.event_task is not None
        await lifecycle.on_ari_event(
            {
                "type": "ChannelStateChange",
                "channel": {"id": "primary-a", "state": "Up"},
            },
            listener_session,
        )
        await lifecycle.on_ari_event(
            {
                "type": "StasisStart",
                "channel": {"id": "primary-a", "name": "Local/a", "state": "Ring"},
                "args": ["outbound", call_a.id],
            },
            listener_session,
        )

        await lifecycle.on_ari_event(
            {
                "type": "ChannelDestroyed",
                "channel": {"id": "primary-b"},
                "cause": 17,
            },
            listener_session,
        )
        before_release = list(connection.socket.messages)  # type: ignore[attr-defined]
        replay_task = call_a.event_task
        assert replay_task is not None
        assert any(
            message["type"] == "call.ended" and message["call_id"] == call_b.id
            for message in before_release
        )
        assert not any(message["call_id"] == call_a.id for message in before_release)

        await listener_session.__aexit__(None, None, None)
        call_a.accepted.set()
        await replay_task
        await lifecycle.on_ari_event(
            {
                "type": "ChannelStateChange",
                "channel": {"id": "primary-a", "state": "Up"},
            },
            listener_session,
        )
        return (
            call_a,
            call_b,
            lifecycle,
            lifecycle.registry,
            listener_session,
            connection.socket.messages,
        )  # type: ignore[attr-defined]

    call_a, call_b, lifecycle, registry, listener_session, messages = asyncio.run(scenario())
    a_messages = [message for message in messages if message["call_id"] == call_a.id]
    b_messages = [message for message in messages if message["call_id"] == call_b.id]
    assert [(message["type"], message.get("status")) for message in a_messages] == [
        ("call.status", "ringing"),
        ("call.status", "answered"),
    ]
    assert [message["type"] for message in b_messages] == ["call.status", "call.ended"]
    assert not call_a.pending_events
    assert call_a.event_task is None
    assert call_a.bridge_id == "bridge-1"
    assert lifecycle.activated == [call_a.id]
    assert lifecycle.activation_session_closed == [False]
    assert len(lifecycle.ari.sessions) == 1
    assert lifecycle.activation_sessions == [lifecycle.ari.sessions[0]]
    assert listener_session.closed is True
    assert lifecycle.ari.sessions[0].closed is True
    assert call_a.id in registry.calls
    assert call_b.id not in registry.calls


class FakeDbSession:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, model, app_id):
        return SimpleNamespace(allowed_destinations="from-internal:12*")


def _originate_message() -> dict[str, object]:
    return {
        "request_id": "request-1",
        "payload": {"context": "from-internal", "extension": "123", "timeout": 4},
    }


def test_originate_registers_both_ids_and_waits_for_accepted_before_ari_signal(
    monkeypatch: pytest.MonkeyPatch,
):
    from app import outbound_calls

    async def scenario():
        registry = ConnectionRegistry()
        connection = _connection()
        registry.connections[connection.id] = connection
        lifecycle, _, _ = _lifecycle()
        lifecycle.registry = registry
        pending_event = None
        seen_ids: list[tuple[str | None, str | None, bool, bool]] = []
        seen_destinations: list[tuple[str | None, str | None]] = []
        sessions: list[FakeSession] = []

        async def on_post_enter(response):
            call = next(iter(registry.calls.values()))
            pending = asyncio.create_task(
                lifecycle.on_ari_event(
                    {
                        "type": "Dial",
                        "peer": {"id": call.channel_id},
                        "dialstatus": "RINGING",
                    },
                    None,
                )
            )
            nonlocal pending_event
            pending_event = pending
            seen_ids.append(
                (
                    call.channel_id,
                    call.other_channel_id,
                    registry.by_channel(call.channel_id or "") is call,
                    registry.by_channel(call.other_channel_id or "") is call,
                )
            )
            seen_destinations.append((call.called_number, call.routing_context))

        def session_factory(*args, **kwargs):
            session = FakeSession(201, on_post_enter if not sessions else None)
            sessions.append(session)
            return session

        monkeypatch.setattr(outbound_calls, "registry", registry)
        monkeypatch.setattr(outbound_calls, "SessionLocal", FakeDbSession)
        monkeypatch.setattr(
            outbound_calls,
            "get_settings",
            lambda: SimpleNamespace(ari_base_url="http://ari.test", ari_username=None, ari_password=None),
        )
        monkeypatch.setattr(outbound_calls.aiohttp, "ClientSession", session_factory)
        await outbound_calls.originate(connection, _originate_message())
        assert pending_event is not None
        await pending_event
        call = next(iter(registry.calls.values()))
        if call.event_task:
            await call.event_task
        return connection, sessions, seen_ids, seen_destinations

    connection, sessions, seen_ids, seen_destinations = asyncio.run(scenario())
    first_request = sessions[0].posts[0][1]["params"]
    assert seen_ids[0][2:] == (True, True)
    assert seen_destinations == [("123", "from-internal")]
    assert first_request["channelId"] == seen_ids[0][0]
    assert first_request["otherChannelId"] == seen_ids[0][1]
    assert [message["type"] for message in connection.socket.messages] == [
        "outbound.accepted",
        "call.status",
        "call.status",
    ]
    assert [message["status"] for message in connection.socket.messages[1:]] == [
        "dialing",
        "ringing",
    ]


def test_originate_error_finishes_call_and_deletes_both_prebound_channels(
    monkeypatch: pytest.MonkeyPatch,
):
    from app import outbound_calls

    async def scenario():
        registry = ConnectionRegistry()
        connection = _connection()
        registry.connections[connection.id] = connection
        sessions: list[FakeSession] = []
        reserved: list[ActiveCall] = []

        def reserve(conn):
            call = ConnectionRegistry.reserve_call(registry, conn)
            reserved.append(call)
            return call

        def session_factory(*args, **kwargs):
            session = FakeSession(503 if not sessions else 204)
            sessions.append(session)
            return session

        monkeypatch.setattr(outbound_calls, "registry", registry)
        monkeypatch.setattr(registry, "reserve_call", reserve)
        monkeypatch.setattr(outbound_calls, "SessionLocal", FakeDbSession)
        monkeypatch.setattr(
            outbound_calls,
            "get_settings",
            lambda: SimpleNamespace(ari_base_url="http://ari.test", ari_username=None, ari_password=None),
        )
        monkeypatch.setattr(outbound_calls.aiohttp, "ClientSession", session_factory)
        with pytest.raises(RuntimeError, match="ARI originate returned 503"):
            await outbound_calls.originate(connection, _originate_message())
        return registry, connection, sessions, reserved

    registry, connection, sessions, reserved = asyncio.run(scenario())
    first_params = sessions[0].posts[0][1]["params"]
    assert registry.calls == {}
    assert reserved[0].accepted.is_set()
    assert connection.socket.messages == []  # type: ignore[attr-defined]
    assert sessions[1].deletes == [
        f"http://ari.test/channels/{first_params['channelId']}",
        f"http://ari.test/channels/{first_params['otherChannelId']}",
    ]


def test_originate_timeout_is_sanitized_and_releases_reservation(
    monkeypatch: pytest.MonkeyPatch,
):
    from app import outbound_calls

    async def scenario():
        registry = ConnectionRegistry()
        connection = _connection()
        registry.connections[connection.id] = connection
        sessions: list[FakeSession] = []
        reserved: list[ActiveCall] = []

        def reserve(conn):
            call = ConnectionRegistry.reserve_call(registry, conn)
            reserved.append(call)
            return call

        def session_factory(*args, **kwargs):
            session = FakeSession(
                201 if not sessions else 204,
                post_error=TimeoutError("socket timeout password=top-secret"),
            ) if not sessions else FakeSession(204)
            sessions.append(session)
            return session

        monkeypatch.setattr(outbound_calls, "registry", registry)
        monkeypatch.setattr(registry, "reserve_call", reserve)
        monkeypatch.setattr(outbound_calls, "SessionLocal", FakeDbSession)
        monkeypatch.setattr(
            outbound_calls,
            "get_settings",
            lambda: SimpleNamespace(ari_base_url="http://ari.test", ari_username=None, ari_password=None),
        )
        monkeypatch.setattr(outbound_calls.aiohttp, "ClientSession", session_factory)
        with pytest.raises(RuntimeError, match="Asterisk originate is unavailable") as error:
            await outbound_calls.originate(connection, _originate_message())
        return registry, connection, sessions, reserved, str(error.value)

    registry, connection, sessions, reserved, error = asyncio.run(scenario())
    first_params = sessions[0].posts[0][1]["params"]
    assert error == "Asterisk originate is unavailable"
    assert "top-secret" not in error
    assert registry.calls == {}
    assert reserved[0].accepted.is_set()
    assert connection.socket.messages == []  # type: ignore[attr-defined]
    assert sessions[1].deletes == [
        f"http://ari.test/channels/{first_params['channelId']}",
        f"http://ari.test/channels/{first_params['otherChannelId']}",
    ]
