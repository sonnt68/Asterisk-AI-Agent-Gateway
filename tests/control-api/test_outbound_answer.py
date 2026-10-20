"""call.started must mean the callee answered, and no call may outlive its channel."""

import asyncio

import pytest
from app.call_lifecycle import CallLifecycle
from app.realtime_registry import ActiveCall, Connection, ConnectionRegistry


class FakeAri:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def delete(self, session, path):
        self.deleted.append(path)


class CaptureSocket:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    async def send_json(self, payload: dict[str, object]) -> None:
        self.messages.append(payload)


@pytest.fixture
def lifecycle():
    """A lifecycle with the media and ARI plumbing stubbed out."""
    instance = CallLifecycle.__new__(CallLifecycle)
    instance.registry = ConnectionRegistry()
    instance.ari = FakeAri()
    instance.activated: list[str] = []

    async def record_activation(call, channel, connection, session):
        instance.activated.append(call.id)
        call.bridge_id = "bridge-1"

    instance._activate_call = record_activation
    return instance


def _connected(lifecycle) -> ActiveCall:
    connection = Connection(
        id="conn-1",
        organization_id="org-1",
        partner_app_id="app-1",
        agent_slug="support-agent",
        scopes={"calls:originate"},
        socket=CaptureSocket(),
    )
    lifecycle.registry.connections["conn-1"] = connection
    call = ActiveCall("call-1", None, "conn-1", "support-agent")
    lifecycle.registry.calls["call-1"] = call
    return call


class TestOutboundWaitsForAnswer:
    def test_ringing_channel_does_not_start_the_call(self, lifecycle):
        """The dialled leg enters Stasis while the phone is still ringing."""
        call = _connected(lifecycle)
        asyncio.run(
            lifecycle._start_outbound("call-1", "chan-1", {"id": "chan-1", "state": "Ring"}, None)
        )

        assert lifecycle.activated == []
        assert call.channel_id == "chan-1"
        assert call.bridge_id is None

    def test_answering_starts_the_call(self, lifecycle):
        _connected(lifecycle)
        asyncio.run(
            lifecycle._start_outbound("call-1", "chan-1", {"id": "chan-1", "state": "Ring"}, None)
        )
        asyncio.run(
            lifecycle._on_channel_state_change("chan-1", {"id": "chan-1", "state": "Up"}, None)
        )

        assert lifecycle.activated == ["call-1"]

    def test_a_channel_already_up_starts_immediately(self, lifecycle):
        """Endpoints that answer on pickup must not wait for a second event."""
        _connected(lifecycle)
        asyncio.run(
            lifecycle._start_outbound("call-1", "chan-1", {"id": "chan-1", "state": "Up"}, None)
        )

        assert lifecycle.activated == ["call-1"]

    def test_state_change_never_activates_a_call_twice(self, lifecycle):
        _connected(lifecycle)
        asyncio.run(
            lifecycle._start_outbound("call-1", "chan-1", {"id": "chan-1", "state": "Up"}, None)
        )
        asyncio.run(
            lifecycle._on_channel_state_change("chan-1", {"id": "chan-1", "state": "Up"}, None)
        )

        assert lifecycle.activated == ["call-1"]

    def test_state_change_for_an_unknown_channel_is_ignored(self, lifecycle):
        asyncio.run(
            lifecycle._on_channel_state_change("nope", {"id": "nope", "state": "Up"}, None)
        )

        assert lifecycle.activated == []

    def test_primary_up_before_stasis_does_not_activate(self, lifecycle):
        call = _connected(lifecycle)
        call.channel_id = "chan-1"

        asyncio.run(
            lifecycle._on_channel_state_change(
                "chan-1", {"id": "chan-1", "state": "Up"}, None
            )
        )

        assert lifecycle.activated == []
        assert call.bridge_id is None

    def test_early_up_then_stale_stasis_ring_activates_once(self, lifecycle):
        """An early answer must survive a stale Ring snapshot from StasisStart."""
        call = _connected(lifecycle)
        call.channel_id = "chan-1"

        async def events_in_ari_order():
            await lifecycle.on_ari_event(
                {
                    "type": "ChannelStateChange",
                    "channel": {"id": "chan-1", "state": "Up"},
                },
                None,
            )
            assert call.answered is True
            assert lifecycle.activated == []

            await lifecycle.on_ari_event(
                {
                    "type": "StasisStart",
                    "channel": {
                        "id": "chan-1",
                        "name": "Local/123@from-internal-0001;1",
                        "state": "Ring",
                    },
                    "args": ["outbound", "call-1"],
                },
                None,
            )
            await lifecycle.on_ari_event(
                {
                    "type": "ChannelStateChange",
                    "channel": {"id": "chan-1", "state": "Up"},
                },
                None,
            )

        asyncio.run(events_in_ari_order())

        assert lifecycle.activated == ["call-1"]
        assert call.status == "answered"
        assert call.bridge_id == "bridge-1"

    def test_local_secondary_up_never_answers_or_activates(self, lifecycle):
        call = _connected(lifecycle)
        call.channel_id = "primary-1"
        call.other_channel_id = "secondary-1"
        call.in_stasis = True

        asyncio.run(
            lifecycle._on_channel_state_change(
                "secondary-1", {"id": "secondary-1", "state": "Up"}, None
            )
        )

        assert lifecycle.activated == []
        assert call.answered is False
        assert call.status == "dialing"

    def test_two_answer_events_start_the_call_once(self, lifecycle):
        """Asterisk repeats ChannelStateChange; the second must find it taken."""
        _connected(lifecycle)
        asyncio.run(
            lifecycle._start_outbound("call-1", "chan-1", {"id": "chan-1", "state": "Ring"}, None)
        )

        async def both():
            await asyncio.gather(
                lifecycle._on_channel_state_change("chan-1", {"id": "chan-1", "state": "Up"}, None),
                lifecycle._on_channel_state_change("chan-1", {"id": "chan-1", "state": "Up"}, None),
            )

        asyncio.run(both())
        assert lifecycle.activated == ["call-1"]


def test_outbound_dial_string_suppresses_local_optimisation():
    """Optimisation collapses the Local channel and silently kills the media."""
    source = open("apps/control-api/app/outbound_calls.py").read()
    assert 'f"Local/{extension}@{context}/n"' in source


def test_inbound_destination_uses_bounded_dialplan_metadata(lifecycle):
    class Store:
        def __init__(self) -> None:
            self.started = []

        async def start(self, call) -> None:
            self.started.append(call)

    async def channel_variable(session, channel_id, variable):
        assert variable == "AI_GATEWAY_AGENT"
        return "support-agent"

    lifecycle.registry.history_store = Store()
    lifecycle.ari.channel_variable = channel_variable
    connection = Connection(
        id="conn-1",
        organization_id="org-1",
        partner_app_id="app-1",
        agent_slug="support-agent",
        scopes={"calls:read"},
        socket=CaptureSocket(),
    )
    lifecycle.registry.connections[connection.id] = connection
    asyncio.run(
        lifecycle._start_inbound(
            "chan-in",
            {
                "id": "chan-in",
                "dialplan": {
                    "exten": "200",
                    "context": "from-trunk",
                },
                "caller": {"number": "+84999999999"},
            },
            None,
        )
    )
    call = lifecycle.registry.history_store.started[0]
    assert call.called_number == "200"
    assert call.routing_context == "from-trunk"


def test_inbound_destination_ignores_unbounded_dialplan_metadata(lifecycle):
    class Store:
        def __init__(self) -> None:
            self.started = []

        async def start(self, call) -> None:
            self.started.append(call)

    async def channel_variable(session, channel_id, variable):
        return "support-agent"

    lifecycle.registry.history_store = Store()
    lifecycle.ari.channel_variable = channel_variable
    connection = Connection(
        id="conn-1",
        organization_id="org-1",
        partner_app_id="app-1",
        agent_slug="support-agent",
        scopes={"calls:read"},
        socket=CaptureSocket(),
    )
    lifecycle.registry.connections[connection.id] = connection
    too_long = "x" * 81
    asyncio.run(
        lifecycle._start_inbound(
            "chan-in",
            {"id": "chan-in", "dialplan": {"exten": too_long, "context": 123}},
            None,
        )
    )
    call = lifecycle.registry.history_store.started[0]
    assert call.called_number is None
    assert call.routing_context is None
