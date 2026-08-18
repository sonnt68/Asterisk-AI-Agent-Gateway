import asyncio
from uuid import uuid4

from gateway.audiosocket import TYPE_AUDIO, TYPE_UUID, encode_frame
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
        assert header[0] == TYPE_AUDIO
        assert payload == b"from-partner"
        writer.close()
        await writer.wait_closed()
        await server.stop()

    asyncio.run(scenario())
