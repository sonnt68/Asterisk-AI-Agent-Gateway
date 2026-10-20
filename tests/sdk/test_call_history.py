"""Loopback HTTP proof for the published Python call-history client."""

from __future__ import annotations

import asyncio

import pytest
from aiohttp import web
from asterisk_ai_gateway import GatewayClient, GatewayHTTPError

API_KEY = "agw_live_history_secret"
CALL_ID = "call/with space"


class CallHistoryLoopback:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []
        self.runner: web.AppRunner | None = None
        self.url = ""

    async def start(self) -> None:
        app = web.Application()
        app.router.add_route("*", "/{tail:.*}", self._handle)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
        self.url = f"http://127.0.0.1:{port}"

    async def stop(self) -> None:
        if self.runner is not None:
            await self.runner.cleanup()

    async def _handle(self, request: web.Request) -> web.Response:
        self.requests.append(
            {
                "method": request.method,
                "raw_path": request.raw_path,
                "authorization": request.headers.get("Authorization"),
            }
        )
        call = {
            "call_id": CALL_ID,
            "partner_app_id": "app-1",
            "agent_slug": "support-agent",
            "direction": "outbound",
            "source": "gateway",
            "status": "completed",
            "terminal": True,
            "answered": True,
            "reason": "normal_hangup",
            "hangup_cause": 16,
            "dial_status": "ANSWER",
            "sequence": 3,
            "created_at": "2026-10-20T01:00:00+00:00",
            "updated_at": "2026-10-20T01:02:03+00:00",
            "answered_at": "2026-10-20T01:00:05+00:00",
            "ended_at": "2026-10-20T01:02:03+00:00",
            "duration_seconds": 123,
            "talk_seconds": 118,
            "history_complete": True,
        }
        if request.path == "/api/v1/partner/calls":
            requested_page = request.query.get("page")
            if requested_page is not None:
                if "cursor" in request.query:
                    return web.json_response(
                        {"detail": "page cannot be combined with cursor"}, status=422
                    )
                if requested_page == "3":
                    return web.json_response(
                        {
                            "items": [],
                            "next_cursor": None,
                            "page": 3,
                            "page_size": 50,
                            "total": 0,
                            "total_pages": 1,
                        }
                    )
                return web.json_response(
                    {
                        "items": [call],
                        "next_cursor": None,
                        "page": int(requested_page),
                        "page_size": int(request.query.get("limit", "50")),
                        "total": 201,
                        "total_pages": 3,
                    }
                )
            return web.json_response(
                {
                    "items": [call],
                    "next_cursor": "cursor-2" if "cursor" in request.query else None,
                    "page": None,
                    "page_size": None,
                    "total": None,
                    "total_pages": None,
                }
            )
        if request.path.endswith("/signals"):
            return web.json_response(
                {
                    "items": [
                        {
                            "type": "call.status",
                            "call_id": CALL_ID,
                            "status": "completed",
                            "terminal": True,
                            "answered": True,
                            "reason": "normal_hangup",
                            "hangup_cause": 16,
                            "dial_status": "ANSWER",
                            "sequence": 3,
                            "updated_at": "2026-10-20T01:02:03+00:00",
                        }
                    ],
                    "next_cursor": None,
                }
            )
        return web.json_response(call)


def test_call_history_uses_direct_api_key_gets_and_safe_query_encoding() -> None:
    async def scenario() -> None:
        server = CallHistoryLoopback()
        await server.start()
        client = GatewayClient(server.url, API_KEY, "support-agent")
        try:
            page = await client.list_calls(
                limit=100,
                cursor="cursor/1 & two",
                status="answered",
                direction="outbound",
                agent_slug="sales-agent",
                started_after="2026-10-20T01:02:03+00:00",
                started_before="2026-10-21T01:02:03+00:00",
            )
            assert page["next_cursor"] == "cursor-2"
            assert page["items"][0]["call_id"] == CALL_ID
            assert page["page"] is None
            assert page["page_size"] is None
            assert page["total"] is None
            assert page["total_pages"] is None

            default_page = await client.list_calls()
            assert default_page["next_cursor"] is None
            assert default_page["page"] is None

            numbered_page = await client.list_calls(agent_slug="wire-agent", page=3)
            assert numbered_page["items"] == []
            assert numbered_page["next_cursor"] is None
            assert numbered_page["page"] == 3
            assert numbered_page["page_size"] == 50
            assert numbered_page["total"] == 0
            assert numbered_page["total_pages"] == 1

            detail = await client.get_call(CALL_ID)
            assert detail["call_id"] == CALL_ID

            signals = await client.list_call_signals(CALL_ID, limit=2, cursor="signal & cursor")
            assert signals["items"][0]["sequence"] == 3

            assert len(server.requests) == 5
            assert all(request["method"] == "GET" for request in server.requests)
            assert all(request["authorization"] == f"Bearer {API_KEY}" for request in server.requests)
            assert "limit=100" in str(server.requests[0]["raw_path"])
            assert "cursor=cursor%2F1+%26+two" in str(server.requests[0]["raw_path"])
            assert "agent_slug=sales-agent" in str(server.requests[0]["raw_path"])
            assert "started_after=2026-10-20T01%3A02%3A03%2B00%3A00" in str(server.requests[0]["raw_path"])
            assert "limit=50" in str(server.requests[1]["raw_path"])
            assert "agent_slug=wire-agent" in str(server.requests[2]["raw_path"])
            assert "page=3" in str(server.requests[2]["raw_path"])
            assert "/call%2Fwith%20space" in str(server.requests[3]["raw_path"])
            assert "/call%2Fwith%20space/signals" in str(server.requests[4]["raw_path"])
            assert "cursor=signal+%26+cursor" in str(server.requests[4]["raw_path"])
            assert "realtime" not in " ".join(str(request["raw_path"]) for request in server.requests)
        finally:
            await server.stop()

    asyncio.run(scenario())


def test_call_history_http_errors_are_structured_safe_and_not_retried() -> None:
    async def scenario() -> None:
        for status in (401, 403, 404, 422):
            request_count = 0
            request_path = ""

            async def handle(request: web.Request, status: int = status) -> web.Response:
                nonlocal request_count, request_path
                request_count += 1
                request_path = request.raw_path
                return web.json_response({"detail": f"invalid request for {API_KEY}"}, status=status)

            app = web.Application()
            app.router.add_get("/{tail:.*}", handle)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "127.0.0.1", 0)
            await site.start()
            port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
            client = GatewayClient(f"http://127.0.0.1:{port}", API_KEY, "support-agent")
            try:
                with pytest.raises(GatewayHTTPError) as raised:
                    if status == 422:
                        await client.list_calls(cursor="cursor-1", page=2)
                    else:
                        await client.list_calls()
                assert raised.value.status == status
                assert raised.value.status_code == status
                assert API_KEY not in str(raised.value)
                assert request_count == 1
                if status == 422:
                    assert "cursor=cursor-1" in request_path
                    assert "page=2" in request_path
            finally:
                await runner.cleanup()

    asyncio.run(scenario())


def test_call_history_rejects_empty_call_ids_before_http() -> None:
    client = GatewayClient("http://127.0.0.1:1", API_KEY, "support-agent")

    async def scenario() -> None:
        with pytest.raises(ValueError):
            await client.get_call("  ")
        with pytest.raises(ValueError):
            await client.list_call_signals("")

    asyncio.run(scenario())
