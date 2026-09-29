"""Loopback HTTP/WebSocket proof for Python SDK authentication retries."""

import asyncio
import contextlib

import pytest
from asterisk_ai_gateway import AuthenticationError, GatewayClient
from partner_sdk_retry_loopback import LoopbackGateway

API_KEY = "agw_live_super_secret_key"


def _client(server: LoopbackGateway, **kwargs: object) -> GatewayClient:
    options = {"heartbeat_interval": 60, "max_backoff": 0.001}
    options.update(kwargs)
    return GatewayClient(server.url, API_KEY, "support-agent", **options)


async def _consume_one(source: object) -> None:
    try:
        await source.__anext__()  # type: ignore[attr-defined]
    except StopAsyncIteration:
        return


async def _wait_until(predicate: object) -> None:
    for _ in range(200):
        if predicate():  # type: ignore[operator]
            return
        await asyncio.sleep(0.001)
    raise AssertionError("loopback server did not reach the expected state")


def test_stream_retries_token_http_auth_and_raises_after_four_attempts(caplog: pytest.LogCaptureFixture):
    async def scenario() -> None:
        server = LoopbackGateway([401] * 8, [])
        await server.start()
        client = _client(server)
        try:
            with pytest.raises(AuthenticationError) as raised:
                await asyncio.wait_for(client.run(), 1)
            assert server.token_requests == 4
            assert API_KEY not in str(raised.value)
            assert API_KEY not in caplog.text
        finally:
            await client.close()
            await server.stop()

    asyncio.run(scenario())


def test_direct_realtime_token_is_one_shot_and_reconnect_false_disables_retries():
    async def scenario() -> None:
        for status in (401, 403):
            server = LoopbackGateway([status, status, status], [])
            await server.start()
            try:
                client = _client(server)
                with pytest.raises(AuthenticationError):
                    await client.realtime_token()
                assert server.token_requests == 1
            finally:
                await server.stop()

        server = LoopbackGateway([401, 401, 401], [])
        await server.start()
        try:
            no_reconnect = _client(server, reconnect=False)
            with pytest.raises(AuthenticationError):
                await no_reconnect.run()
            assert server.token_requests == 1
        finally:
            await server.stop()

    asyncio.run(scenario())


def test_handshake_and_4401_auth_failures_share_budget_and_mint_fresh_tokens():
    async def scenario() -> None:
        server = LoopbackGateway([200] * 4, [401, 403, "4401", "ready"])
        await server.start()
        client = _client(server)
        source = client.stream()
        try:
            event = await asyncio.wait_for(source.__anext__(), 1)
            assert event["type"] == "session.ready"
            assert server.token_requests == server.ws_requests == 4
            assert server.tokens == server.ws_tokens
            assert len(set(server.tokens)) == 4
        finally:
            server.hold.set()
            await client.close()
            await source.aclose()
            await server.stop()

    asyncio.run(scenario())


def test_stream_raises_after_persistent_handshake_or_4401_auth_failures():
    async def scenario() -> None:
        for action in (401, 403, "4401"):
            server = LoopbackGateway([200] * 4, [action] * 4)
            await server.start()
            client = _client(server)
            source = client.stream()
            try:
                with pytest.raises(AuthenticationError) as raised:
                    await asyncio.wait_for(source.__anext__(), 1)
                assert API_KEY not in str(raised.value)
                assert server.token_requests == server.ws_requests == 4
                assert server.tokens == server.ws_tokens
                assert len(set(server.tokens)) == 4
            finally:
                await client.close()
                await source.aclose()
                await server.stop()

    asyncio.run(scenario())


def test_default_auth_backoff_is_one_two_four_seconds():
    async def scenario() -> None:
        server = LoopbackGateway([401] * 4, [])
        await server.start()
        client = _client(server, max_backoff=30)
        try:
            with pytest.raises(AuthenticationError):
                await client.run()
            assert server.token_requests == 4
            intervals = [later - earlier for earlier, later in zip(server.token_times, server.token_times[1:])]
            assert intervals[0] >= 0.85
            assert intervals[1] >= 1.75
            assert intervals[2] >= 3.5
        finally:
            await client.close()
            await server.stop()

    asyncio.run(scenario())


def test_session_ready_resets_budget_but_socket_open_without_ready_does_not():
    async def scenario() -> None:
        recovered = LoopbackGateway([401, 200, 401, 401, 401, 200], ["ready-close", "ready"])
        await recovered.start()
        client = _client(recovered)
        source = client.stream()
        try:
            assert (await source.__anext__())["type"] == "session.ready"
            assert (await asyncio.wait_for(source.__anext__(), 1))["type"] == "session.ready"
            assert recovered.token_requests == 6
        finally:
            recovered.hold.set()
            await client.close()
            await source.aclose()
            await recovered.stop()

        not_ready = LoopbackGateway([401, 200, 401, 401, 401], ["no-ready"])
        await not_ready.start()
        client = _client(not_ready)
        try:
            with pytest.raises(AuthenticationError):
                await asyncio.wait_for(client.run(), 1)
            assert not_ready.token_requests == 5
            assert not_ready.ws_requests == 1
        finally:
            await client.close()
            await not_ready.stop()

    asyncio.run(scenario())


def test_close_wakes_backoff_and_blocks_late_retry_timer():
    async def scenario() -> None:
        server = LoopbackGateway([200], [500])
        await server.start()
        client = _client(server, max_backoff=0.2)
        source = client.stream()
        task = asyncio.create_task(_consume_one(source))
        try:
            await _wait_until(lambda: server.ws_requests == 1)
            await client.close()
            await asyncio.wait_for(task, 1)
            await asyncio.sleep(0.02)
            assert server.token_requests == 1
            assert server.ws_requests == 1
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, StopAsyncIteration):
                await task
            await source.aclose()
            await server.stop()

    asyncio.run(scenario())


def test_close_during_inflight_token_never_opens_a_socket():
    async def scenario() -> None:
        server = LoopbackGateway([200], [], block_token=True)
        await server.start()
        client = _client(server)
        source = client.stream()
        task = asyncio.create_task(_consume_one(source))
        try:
            await asyncio.wait_for(server.token_started.wait(), 1)
            await client.close()
            server.release_token.set()
            await asyncio.wait_for(task, 1)
            assert server.ws_requests == 0
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, StopAsyncIteration):
                await task
            await source.aclose()
            await server.stop()

    asyncio.run(scenario())


def test_close_during_handshake_never_registers_or_leaves_the_stream_running():
    async def scenario() -> None:
        server = LoopbackGateway([200], ["ready"], block_handshake=True)
        await server.start()
        client = _client(server)
        task = asyncio.create_task(client.run())
        try:
            await asyncio.wait_for(server.handshake_started.wait(), 1)
            await client.close()
            server.release_handshake.set()
            await asyncio.wait_for(task, 1)
            assert server.registered == 0
            assert server.token_requests == server.ws_requests == 1
            assert client.connection_id is None
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            await client.close()
            await server.stop()

    asyncio.run(scenario())


def test_task_cancellation_during_backoff_or_token_request_stops_cleanly():
    async def scenario() -> None:
        server = LoopbackGateway([200], [500])
        await server.start()
        client = _client(server, max_backoff=30)
        source = client.stream()
        task = asyncio.create_task(_consume_one(source))
        try:
            await _wait_until(lambda: server.ws_requests == 1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            await asyncio.sleep(0.02)
            assert server.token_requests == server.ws_requests == 1
        finally:
            await client.close()
            await source.aclose()
            await server.stop()

        server = LoopbackGateway([200], [], block_token=True)
        await server.start()
        client = _client(server)
        source = client.stream()
        task = asyncio.create_task(_consume_one(source))
        try:
            await asyncio.wait_for(server.token_started.wait(), 1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert server.ws_requests == 0
        finally:
            server.release_token.set()
            await client.close()
            await source.aclose()
            await server.stop()

    asyncio.run(scenario())
