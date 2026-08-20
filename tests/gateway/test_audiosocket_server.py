import asyncio
from uuid import uuid4

from gateway.audiosocket import GATEWAY_AUDIO_TYPE, TYPE_AUDIO, TYPE_UUID, encode_frame
from gateway.audiosocket_server import AudioSocketServer


def test_audiosocket_server_routes_bidirectional_audio() -> None:
    async def scenario() -> None:
        received: list[bytes] = []
        bound: list[tuple[str, str]] = []

        async def on_uuid(connection_id: str, call_id: str) -> bool:
            bound.append((connection_id, call_id))
            return True

        async def on_audio(_connection_id: str, payload: bytes) -> None:
            received.append(payload)

        async def ignore(*_args: object) -> None:
            return None

        server = AudioSocketServer("127.0.0.1", 0, on_uuid, on_audio, ignore, ignore)
        await server.start()
        assert server.server and server.server.sockets
        port = server.server.sockets[0].getsockname()[1]
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        call_id = uuid4()
        writer.write(encode_frame(TYPE_UUID, call_id.bytes))
        writer.write(encode_frame(TYPE_AUDIO, b"from-asterisk"))
        await writer.drain()
        for _ in range(20):
            if received:
                break
            await asyncio.sleep(0.01)
        assert received == [b"from-asterisk"]
        assert bound[0][1] == str(call_id)

        assert await server.send_audio(bound[0][0], b"from-partner")
        header = await reader.readexactly(3)
        payload = await reader.readexactly(int.from_bytes(header[1:], "big"))
        assert header[0] == GATEWAY_AUDIO_TYPE  # 0x12: declares 16 kHz to Asterisk
        assert payload == b"from-partner"
        writer.close()
        await writer.wait_closed()
        await server.stop()

    asyncio.run(scenario())


def test_outbound_frames_use_the_only_type_asterisk_reads():
    """Asterisk 21 accepts 0x00 and 0x10 alone; anything else drops the channel."""
    from gateway.audiosocket import AUDIO_TYPE_RATES, GATEWAY_AUDIO_TYPE

    assert GATEWAY_AUDIO_TYPE == 0x10
    assert AUDIO_TYPE_RATES[0x12] == 16000, "the table stays for inbound frames"


def test_the_channel_format_carries_the_rate_the_type_byte_cannot():
    """`c(slin)` is the only thing telling Asterisk how fast to play a frame."""
    from gateway.audiosocket import channel_format

    assert channel_format(8000) == "slin"
    assert channel_format(16000) == "slin16"
    assert channel_format(24000) == "slin24"


def test_a_rate_asterisk_cannot_name_is_refused_at_the_source():
    """Better a startup error than a channel Asterisk silently mis-plays."""
    import pytest
    from gateway.audiosocket import channel_format

    with pytest.raises(ValueError):
        channel_format(11025)


def test_the_gateway_carries_telephony_rate_by_default():
    """A wider wire only adds resampling; the trunk is 8 kHz regardless."""
    from gateway.audiosocket import GATEWAY_SAMPLE_RATE

    assert GATEWAY_SAMPLE_RATE == 8000


def test_handshake_accepts_every_signed_linear_rate():
    """Refusing 0x12 would drop the connection the moment Asterisk sends 16 kHz."""
    from uuid import uuid4

    from gateway.audiosocket import TYPE_UUID, AudioSocketFrame, AudioSocketHandshake

    handshake = AudioSocketHandshake()
    handshake.accept(AudioSocketFrame(TYPE_UUID, uuid4().bytes))
    for audio_type in (0x10, 0x12, 0x13):
        assert handshake.accept(AudioSocketFrame(audio_type, b"\x00\x00")) is None


def test_oversized_payloads_are_split_not_dropped():
    """Dropping them lost audio silently and pushed partners to 8 kHz."""
    import asyncio

    from gateway.audiosocket import MAX_PAYLOAD_BYTES

    class FakeWriter:
        def __init__(self): self.frames = []
        def write(self, data): self.frames.append(data)
        async def drain(self): return None

    server = AudioSocketServer("127.0.0.1", 0, None, None, None, None)
    writer = FakeWriter()
    server.writers["c1"] = writer

    payload = bytes(MAX_PAYLOAD_BYTES * 2 + 100)
    assert asyncio.run(server.send_audio("c1", payload)) is True
    assert len(writer.frames) == 3
    sent = b"".join(f[3:] for f in writer.frames)
    assert sent == payload, "every byte must reach Asterisk"
