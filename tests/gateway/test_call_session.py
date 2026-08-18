import pytest
from gateway.call_session import CallSession, CallState


def test_call_session_transitions_from_created_to_active_to_ended() -> None:
    session = CallSession(call_id="call_123")

    session.activate()
    session.end()

    assert session.state is CallState.ENDED


def test_call_session_rejects_a_second_activation() -> None:
    session = CallSession(call_id="call_123")
    session.activate()

    with pytest.raises(ValueError, match="cannot activate"):
        session.activate()
