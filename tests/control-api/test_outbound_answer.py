"""call.started must mean the callee answered, and no call may outlive its channel."""

import asyncio
from types import SimpleNamespace

import pytest
from app.call_lifecycle import CallLifecycle
from app.realtime_registry import ActiveCall, ConnectionRegistry


class FakeAri:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def delete(self, session, path):
        self.deleted.append(path)


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
    connection = SimpleNamespace(id="conn-1", agent_slug="support-agent")
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
