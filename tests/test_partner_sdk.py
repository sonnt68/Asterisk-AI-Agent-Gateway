"""Contract tests for the partner Python SDK."""

import asyncio

import pytest
from asterisk_ai_gateway import (
    GatewayClient,
    GatewayError,
    decode_audio_frame,
    encode_audio_frame,
)

CALL_ID = "8c1f4b2e-0d5a-4f77-9a51-6b0c7e2d3a44"


def test_audio_frame_roundtrip_preserves_call_and_payload():
    frame = encode_audio_frame(CALL_ID, b"\x01\x02\x03\x04")
    assert len(frame) == 16 + 4
    assert decode_audio_frame(frame) == (CALL_ID, b"\x01\x02\x03\x04")


def test_audio_frame_rejects_payload_without_pcm():
    with pytest.raises(ValueError):
        encode_audio_frame(CALL_ID, b"")


def test_decode_rejects_frame_that_carries_no_pcm():
    with pytest.raises(ValueError):
        decode_audio_frame(bytes(16))


def test_websocket_url_upgrades_scheme_and_keeps_realtime_path():
    client = GatewayClient("https://gateway.example.com/", "agw_live_a_b", "support-agent")
    assert client._websocket_url("TOK") == "wss://gateway.example.com/v1/realtime?token=TOK"

    plain = GatewayClient("http://127.0.0.1:18080", "agw_live_a_b", "support-agent")
    assert plain._websocket_url("TOK") == "ws://127.0.0.1:18080/v1/realtime?token=TOK"


def test_repr_never_exposes_the_api_key():
    client = GatewayClient("https://gateway.example.com", "agw_live_secret_value", "support-agent")
    assert "agw_live_secret_value" not in repr(client)


def test_originate_rejects_timeout_outside_gateway_bounds():
    client = GatewayClient("https://gateway.example.com", "agw_live_a_b", "support-agent")

    async def scenario():
        for timeout in (0, 121):
            with pytest.raises(ValueError):
                await client.originate("from-internal", "1002", timeout=timeout)

    asyncio.run(scenario())


def test_route_rejects_targets_the_gateway_has_no_command_for():
    client = GatewayClient("https://gateway.example.com", "agw_live_a_b", "support-agent")

    async def scenario():
        with pytest.raises(ValueError):
            await client.route("call", "parking_lot", "from-internal", "1001")

    asyncio.run(scenario())


def test_control_without_a_session_fails_loudly():
    client = GatewayClient("https://gateway.example.com", "agw_live_a_b", "support-agent")

    async def scenario():
        with pytest.raises(GatewayError):
            await client.hangup(CALL_ID)

    asyncio.run(scenario())
