"""Exercise managed DID routing through a deployed local Asterisk.

Run inside the API container.  The probe uses a signed browser session from
the bound operator organization, creates disposable partner apps and keys in
memory, and originates only a local ``Local/<DID>@from-pstn/n`` channel.  It
never dials a carrier or prints credentials.  The phone number and trunk are
left disabled for the operator's exact post-run cleanup.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote
from uuid import UUID, uuid4

import aiohttp
import websockets
from app.auth import Principal, create_session
from app.database import SessionLocal
from app.models import Membership
from app.settings import get_settings
from sqlalchemy import select
from yarl import URL

FIXTURE_NUMBER = "999999920261021"
FIXTURE_LABEL = "gateway-telephony-fixture"
PARTNER_SCOPES = ["calls:read", "media:stream", "media:playback"]
LOCAL_CONTEXT = "from-pstn"
APP_NAME = "Gateway telephony fixture"
CALL_TIMEOUT = 25


class ProbeFailure(RuntimeError):
    """A fixed, safe failure name that never contains a response body."""


@dataclass
class ProbeResources:
    app_ids: list[str]
    key_ids: list[str]
    sessions: list[PartnerSession]
    number_id: str | None = None
    trunk_id: str | None = None


def require(condition: bool, stage: str) -> None:
    if not condition:
        raise ProbeFailure(stage)


async def api_request(
    http: aiohttp.ClientSession,
    method: str,
    base: str,
    path: str,
    *,
    stage: str,
    expected: set[int] = {200},
    payload: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> object:
    try:
        async with http.request(
            method, base + path, json=payload, headers=headers
        ) as response:
            if response.status not in expected:
                await response.read()
                raise ProbeFailure(stage)
            if response.status == 204:
                return None
            try:
                return await response.json(content_type=None)
            except (aiohttp.ContentTypeError, ValueError):
                raise ProbeFailure(stage) from None
    except ProbeFailure:
        raise
    except (TimeoutError, aiohttp.ClientError):
        raise ProbeFailure(stage) from None


async def ari_request(
    ari: aiohttp.ClientSession,
    base: str,
    method: str,
    path: str,
    *,
    stage: str,
    expected: set[int] = {200},
    params: dict[str, str] | None = None,
) -> object:
    try:
        async with ari.request(method, base + path, params=params) as response:
            if response.status not in expected:
                await response.read()
                raise ProbeFailure(stage)
            if response.status == 204:
                return None
            try:
                return await response.json(content_type=None)
            except (aiohttp.ContentTypeError, ValueError):
                raise ProbeFailure(stage) from None
    except ProbeFailure:
        raise
    except (TimeoutError, aiohttp.ClientError):
        raise ProbeFailure(stage) from None


def operator_browser_cookie(organization_id: str) -> str:
    settings = get_settings()
    require(
        settings.freepbx_operator_organization_id == organization_id,
        "operator_organization_binding",
    )
    with SessionLocal() as session:
        membership = session.scalar(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.role.in_(["owner", "admin"]),
            )
        )
    require(membership is not None, "operator_manager_membership")
    return create_session(Principal(membership.user_id, organization_id, membership.role))


def object_dict(value: object, stage: str) -> dict[str, object]:
    require(isinstance(value, dict), stage)
    return value


def list_value(value: object, stage: str) -> list[object]:
    require(isinstance(value, list), stage)
    return value


async def wait_clean(
    http: aiohttp.ClientSession,
    api_base: str,
    ari: aiohttp.ClientSession,
    ari_base: str,
    outer_channel: str | None,
) -> None:
    for _ in range(40):
        runtime = object_dict(
            await api_request(http, "GET", api_base, "/runtime", stage="runtime_read"),
            "runtime_shape",
        )
        channels = list_value(
            await ari_request(
                ari, ari_base, "GET", "/channels", stage="ari_channels_read"
            ),
            "ari_channels_shape",
        )
        media_channels = [
            item
            for item in channels
            if isinstance(item, dict)
            and (
                str(item.get("name", "")).startswith("AudioSocket/")
                or str(item.get("name", "")).startswith("UnicastRTP/")
            )
        ]
        outer_exists = any(
            isinstance(item, dict) and item.get("id") == outer_channel
            for item in channels
        )
        if runtime.get("active_calls") == 0 and not media_channels and not outer_exists:
            return
        await asyncio.sleep(0.25)
    raise ProbeFailure("call_cleanup")


@dataclass
class PartnerSession:
    slug: str
    socket: Any
    messages: asyncio.Queue[object]
    reader: asyncio.Task[None] | None
    heartbeat: asyncio.Task[None] | None = None

    @classmethod
    async def open(
        cls, ws_base: str, origin: str, slug: str, token: str
    ) -> PartnerSession:
        url = f"{ws_base.rstrip('/')}/v1/realtime?token={quote(token, safe='')}"
        socket: Any | None = None
        try:
            socket = await asyncio.wait_for(
                websockets.connect(url, origin=origin, max_size=None), 10
            )
            await socket.send(
                json.dumps(
                    {
                        "type": "session.register",
                        "agent_slug": slug,
                        "protocol_version": "1",
                    }
                )
            )
            ready = await asyncio.wait_for(socket.recv(), 10)
            ready_data = json.loads(ready) if isinstance(ready, str) else {}
            require(
                isinstance(ready_data, dict)
                and ready_data.get("type") == "session.ready",
                "partner_session_register",
            )
        except ProbeFailure:
            if socket is not None:
                with contextlib.suppress(Exception, asyncio.CancelledError):
                    await socket.close()
            raise
        except Exception:
            raise ProbeFailure("partner_session_register") from None
        messages: asyncio.Queue[object] = asyncio.Queue()
        require(socket is not None, "partner_session_socket")
        session = cls(slug, socket, messages, None)
        session.reader = asyncio.create_task(session._read())
        session.heartbeat = asyncio.create_task(session._heartbeat())
        return session

    async def _heartbeat(self) -> None:
        # Long native-media probes must renew the same lease as SDK clients.
        try:
            while True:
                await asyncio.sleep(10)
                await self.socket.send(json.dumps({"type": "heartbeat"}))
        except Exception:
            await self.messages.put(None)

    async def _read(self) -> None:
        try:
            async for message in self.socket:
                await self.messages.put(message)
        except Exception:
            pass
        finally:
            await self.messages.put(None)

    async def close(self) -> None:
        for task in (self.reader, self.heartbeat):
            if task:
                task.cancel()
                with contextlib.suppress(Exception, asyncio.CancelledError):
                    await task
        with contextlib.suppress(Exception, asyncio.CancelledError):
            await self.socket.close()


def event_data(message: object) -> dict[str, object] | None:
    if not isinstance(message, str):
        return None
    try:
        data = json.loads(message)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


async def wait_for_start(
    expected: PartnerSession, other: PartnerSession, timeout: float = CALL_TIMEOUT
) -> tuple[str, dict[str, object]]:
    pending = {
        asyncio.create_task(session.messages.get()): session
        for session in (expected, other)
    }
    deadline = asyncio.get_running_loop().time() + timeout
    try:
        while pending:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise ProbeFailure("call_started_timeout")
            done, _ = await asyncio.wait(
                pending, timeout=remaining, return_when=asyncio.FIRST_COMPLETED
            )
            if not done:
                raise ProbeFailure("call_started_timeout")
            for task in done:
                owner = pending.pop(task)
                message = task.result()
                pending[asyncio.create_task(owner.messages.get())] = owner
                if message is None:
                    raise ProbeFailure("partner_socket_closed")
                data = event_data(message)
                if not data:
                    continue
                if data.get("type") == "error":
                    raise ProbeFailure("partner_protocol_error")
                if data.get("type") != "call.started":
                    continue
                call_id = data.get("call_id")
                try:
                    UUID(str(call_id))
                except (ValueError, AttributeError):
                    raise ProbeFailure("call_started_shape") from None
                if owner is not expected:
                    raise ProbeFailure("wrong_partner_received_call_started")
                return str(call_id), data
    finally:
        for task in pending:
            task.cancel()

    raise ProbeFailure("call_started_timeout")


async def wait_for_binary(session: PartnerSession, call_id: str) -> None:
    deadline = asyncio.get_running_loop().time() + 8
    while asyncio.get_running_loop().time() < deadline:
        try:
            message = await asyncio.wait_for(
                session.messages.get(), max(0.1, deadline - asyncio.get_running_loop().time())
            )
        except TimeoutError:
            break
        if isinstance(message, bytes) and len(message) > 16:
            require(message[:16] == UUID(call_id).bytes, "audio_frame_call_id")
            return
        data = event_data(message)
        if data and data.get("type") == "error":
            raise ProbeFailure("partner_protocol_error")
    raise ProbeFailure("audio_frame_timeout")


async def wait_for_end(
    expected: PartnerSession, other: PartnerSession, call_id: str
) -> None:
    pending = {
        asyncio.create_task(session.messages.get()): session
        for session in (expected, other)
    }
    deadline = asyncio.get_running_loop().time() + CALL_TIMEOUT
    try:
        while pending:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise ProbeFailure("call_ended_timeout")
            done, _ = await asyncio.wait(
                pending, timeout=remaining, return_when=asyncio.FIRST_COMPLETED
            )
            if not done:
                raise ProbeFailure("call_ended_timeout")
            for task in done:
                owner = pending.pop(task)
                message = task.result()
                pending[asyncio.create_task(owner.messages.get())] = owner
                if message is None:
                    raise ProbeFailure("partner_socket_closed")
                data = event_data(message)
                if not data:
                    continue
                if data.get("type") == "error":
                    raise ProbeFailure("partner_protocol_error")
                if data.get("type") == "call.started" and owner is not expected:
                    raise ProbeFailure("wrong_partner_received_call_started")
                if data.get("type") == "call.ended" and data.get("call_id") == call_id:
                    return
    finally:
        for task in pending:
            task.cancel()
    raise ProbeFailure("call_ended_timeout")


async def wait_for_no_start(
    first: PartnerSession, second: PartnerSession, timeout: float = 5
) -> None:
    pending = {
        asyncio.create_task(session.messages.get()): session
        for session in (first, second)
    }
    deadline = asyncio.get_running_loop().time() + timeout
    try:
        while pending:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return
            done, _ = await asyncio.wait(
                pending, timeout=remaining, return_when=asyncio.FIRST_COMPLETED
            )
            if not done:
                return
            for task in done:
                owner = pending.pop(task)
                message = task.result()
                pending[asyncio.create_task(owner.messages.get())] = owner
                if message is None:
                    raise ProbeFailure("partner_socket_closed")
                data = event_data(message)
                if data and data.get("type") == "error":
                    raise ProbeFailure("partner_protocol_error")
                if data and data.get("type") == "call.started":
                    raise ProbeFailure("disabled_route_delivered_call")
    finally:
        for task in pending:
            task.cancel()


async def originate(
    ari: aiohttp.ClientSession, ari_base: str, number: str, stage: str
) -> str:
    channel_id = str(uuid4())
    response = object_dict(
        await ari_request(
            ari,
            ari_base,
            "POST",
            "/channels",
            stage=stage,
            expected={200, 201},
            params={
                "endpoint": f"Local/{number}@{LOCAL_CONTEXT}/n",
                "app": "asterisk-ai-gateway",
                "appArgs": "externalmedia",
                "channelId": channel_id,
            },
        ),
        "ari_originate_shape",
    )
    require(response.get("id") == channel_id, "ari_originate_channel_id")
    return channel_id


async def delete_channel(ari: aiohttp.ClientSession, ari_base: str, channel_id: str) -> None:
    await ari_request(
        ari,
        ari_base,
        "DELETE",
        f"/channels/{quote(channel_id, safe='')}",
        stage="ari_channel_delete",
        expected={204, 404},
    )


async def exercise_call(
    http: aiohttp.ClientSession,
    api_base: str,
    ari: aiohttp.ClientSession,
    ari_base: str,
    number: str,
    expected: PartnerSession,
    other: PartnerSession,
    *,
    stage: str,
) -> None:
    outer: str | None = None
    try:
        outer = await originate(ari, ari_base, number, stage + "_originate")
        call_id, _ = await wait_for_start(expected, other)
        await ari_request(
            ari,
            ari_base,
            "POST",
            f"/channels/{quote(outer, safe='')}/play",
            stage=stage + "_playback",
            expected={200, 201},
            params={"media": "sound:beep"},
        )
        await wait_for_binary(expected, call_id)
        try:
            await expected.socket.send(UUID(call_id).bytes + (b"\0" * 320))
        except (TimeoutError, OSError, websockets.WebSocketException):
            raise ProbeFailure(stage + "_silence") from None
        await delete_channel(ari, ari_base, outer)
        await wait_for_end(expected, other, call_id)
    finally:
        if outer:
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await delete_channel(ari, ari_base, outer)
        await wait_clean(http, api_base, ari, ari_base, outer)


async def exercise_disabled_call(
    http: aiohttp.ClientSession,
    api_base: str,
    ari: aiohttp.ClientSession,
    ari_base: str,
    number: str,
    first: PartnerSession,
    second: PartnerSession,
) -> None:
    outer: str | None = None
    try:
        outer = await originate(ari, ari_base, number, "disabled_originate")
        await wait_for_no_start(first, second)
    finally:
        if outer:
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await delete_channel(ari, ari_base, outer)
        await wait_clean(http, api_base, ari, ari_base, outer)


async def create_app_and_key(
    http: aiohttp.ClientSession,
    api_base: str,
    organization_id: str,
    slug: str,
    app_ids: list[str],
    key_ids: list[str],
) -> tuple[str, str]:
    app = object_dict(
        await api_request(
            http,
            "POST",
            api_base,
            f"/organizations/{organization_id}/partner-apps",
            stage="partner_app_create",
            expected={201},
            payload={
                "name": APP_NAME,
                "agent_slug": slug,
                "scopes": PARTNER_SCOPES,
                "allowed_destinations": [],
            },
        ),
        "partner_app_create_shape",
    )
    app_id = app.get("id")
    require(isinstance(app_id, str) and app_id, "partner_app_id")
    app_ids.append(app_id)
    key = object_dict(
        await api_request(
            http,
            "POST",
            api_base,
            f"/partner-apps/{quote(app_id, safe='')}/api-keys",
            stage="partner_key_create",
            expected={201},
            payload={
                "name": APP_NAME,
                "scopes": PARTNER_SCOPES,
                "expires_at": (datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
            },
        ),
        "partner_key_create_shape",
    )
    key_id, secret = key.get("id"), key.get("key")
    require(
        isinstance(key_id, str) and isinstance(secret, str) and secret,
        "partner_key_secret",
    )
    key_ids.append(key_id)
    return app_id, secret


async def run(
    args: argparse.Namespace,
    resources: ProbeResources,
    browser_cookie: str,
) -> dict[str, object]:
    require(args.number == FIXTURE_NUMBER, "fixture_number_mismatch")
    settings = get_settings()
    require(settings.ari_base_url and settings.ari_username and settings.ari_password, "ari_configuration")
    ari_base = settings.ari_base_url.rstrip("/")
    origin = args.origin or settings.web_origin
    api_base = args.base_url.rstrip("/") + "/api/v1"
    ws_base = args.ws_url.rstrip("/")
    async with aiohttp.ClientSession(
        cookie_jar=aiohttp.CookieJar(unsafe=True),
        headers={"Origin": origin},
    ) as http:
        http.cookie_jar.update_cookies(
            {"gateway_session": browser_cookie}, response_url=URL(args.base_url)
        )
        status = object_dict(
            await api_request(
                http, "GET", api_base, "/asterisk/provisioning", stage="provisioning_read"
            ),
            "provisioning_shape",
        )
        require(status.get("can_manage") is True, "provisioning_authorization")
        require(status.get("configured") is True and status.get("connected") is True, "provisioning_connected")
        transports = [item for item in list_value(status.get("transports"), "provisioning_transports") if isinstance(item, str)]
        require(bool(transports), "provisioning_transport")
        trunks = list_value(
            await api_request(http, "GET", api_base, "/asterisk/trunks", stage="trunks_read"),
            "trunks_shape",
        )
        require(
            not any(isinstance(item, dict) and item.get("name") == FIXTURE_LABEL for item in trunks),
            "trunk_name_collision",
        )
        phone_numbers = list_value(
            await api_request(http, "GET", api_base, "/phone-numbers", stage="numbers_read"),
            "numbers_shape",
        )
        require(
            not any(
                isinstance(item, dict)
                and (item.get("number") == args.number or item.get("label") == FIXTURE_LABEL)
                for item in phone_numbers
            ),
            "phone_number_collision",
        )

        suffix = uuid4().hex[:12]
        slug_a = "telephony-fixture-a-" + suffix
        slug_b = "telephony-fixture-b-" + suffix
        app_a, secret_a = await create_app_and_key(
            http, api_base, args.organization_id, slug_a, resources.app_ids, resources.key_ids
        )
        app_b, secret_b = await create_app_and_key(
            http, api_base, args.organization_id, slug_b, resources.app_ids, resources.key_ids
        )
        trunk = object_dict(
            await api_request(
                http,
                "POST",
                api_base,
                "/asterisk/trunks",
                stage="trunk_create",
                expected={201},
                payload={
                    "name": FIXTURE_LABEL,
                    "host": "127.0.0.1",
                    "port": 9,
                    "transport": transports[0],
                    "authentication": "outbound",
                    "registration": "none",
                    "username": FIXTURE_LABEL,
                    "auth_username": FIXTURE_LABEL,
                    "password": uuid4().hex,
                    "enabled": False,
                },
            ),
            "trunk_create_shape",
        )
        trunk_id = trunk.get("id")
        require(isinstance(trunk_id, str) and trunk_id, "trunk_create_id")
        resources.trunk_id = trunk_id
        require(trunk.get("enabled") is False, "trunk_create_state")
        require(trunk.get("password_set") is True, "trunk_password_set")
        preserved = object_dict(
            await api_request(
                http,
                "PATCH",
                api_base,
                f"/asterisk/trunks/{quote(trunk_id, safe='')}",
                stage="trunk_patch",
                payload={"enabled": False},
            ),
            "trunk_patch_shape",
        )
        require(preserved.get("password_set") is True, "trunk_password_preserved")

        phone = object_dict(
            await api_request(
                http,
                "POST",
                api_base,
                "/phone-numbers",
                stage="phone_number_create",
                expected={201},
                payload={
                    "number": args.number,
                    "label": FIXTURE_LABEL,
                    "partner_app_id": app_a,
                    "enabled": True,
                },
            ),
            "phone_number_create_shape",
        )
        number_id = phone.get("id")
        require(isinstance(number_id, str) and number_id, "phone_number_id")
        resources.number_id = number_id
        require(phone.get("pbx_applied") is False, "phone_number_pending")
        applied = object_dict(
            await api_request(
                http, "POST", api_base, "/asterisk/apply", stage="asterisk_apply"
            ),
            "asterisk_apply_shape",
        )
        applied_routes = list_value(applied.get("applied_routes"), "applied_routes_shape")
        require(
            any(
                isinstance(item, dict)
                and item.get("route_id") == number_id
                and item.get("number") == args.number
                for item in applied_routes
            ),
            "asterisk_apply_readback",
        )
        applied_numbers = list_value(
            await api_request(
                http,
                "GET",
                api_base,
                "/phone-numbers",
                stage="phone_number_applied_read",
            ),
            "phone_number_applied_shape",
        )
        applied_phone = next(
            (
                item
                for item in applied_numbers
                if isinstance(item, dict) and item.get("id") == number_id
            ),
            None,
        )
        require(
            isinstance(applied_phone, dict) and applied_phone.get("pbx_applied") is True,
            "phone_number_applied_state",
        )

        for app_id, secret, slug in ((app_a, secret_a, slug_a), (app_b, secret_b, slug_b)):
            token = object_dict(
                await api_request(
                    http,
                    "POST",
                    api_base,
                    "/realtime/tokens",
                    stage="realtime_token_create",
                    headers={"Authorization": f"Bearer {secret}"},
                ),
                "realtime_token_shape",
            ).get("token")
            require(isinstance(token, str) and token, "realtime_token_value")
            resources.sessions.append(await PartnerSession.open(ws_base, origin, slug, token))

        ari_timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(
            auth=aiohttp.BasicAuth(settings.ari_username, settings.ari_password),
            timeout=ari_timeout,
        ) as ari:
            await wait_clean(http, api_base, ari, ari_base, None)
            await exercise_call(
                http, api_base, ari, ari_base, args.number, resources.sessions[0], resources.sessions[1], stage="mapped_a"
            )
            reassigned = object_dict(
                await api_request(
                    http,
                    "PATCH",
                    api_base,
                    f"/phone-numbers/{quote(number_id, safe='')}",
                    stage="phone_number_reassign",
                    payload={"partner_app_id": app_b},
                ),
                "phone_number_reassign_shape",
            )
            require(
                reassigned.get("partner_app_id") == app_b
                and reassigned.get("pbx_applied") is True,
                "phone_number_reassign_state",
            )
            await exercise_call(
                http, api_base, ari, ari_base, args.number, resources.sessions[1], resources.sessions[0], stage="mapped_b"
            )
            disabled = object_dict(
                await api_request(
                    http,
                    "PATCH",
                    api_base,
                    f"/phone-numbers/{quote(number_id, safe='')}",
                    stage="phone_number_disable",
                    payload={"enabled": False},
                ),
                "phone_number_disable_shape",
            )
            require(disabled.get("enabled") is False, "phone_number_disabled_state")
            await exercise_disabled_call(
                http, api_base, ari, ari_base, args.number, resources.sessions[0], resources.sessions[1]
            )

    return {
        "status": "passed",
        "organization_id": args.organization_id,
        "number_id": resources.number_id,
        "trunk_id": resources.trunk_id,
        "app_ids": resources.app_ids,
        "key_ids": resources.key_ids,
        "routing": {
            "mapped_a": "passed",
            "apply_readback": "passed",
            "reassigned_without_reload": "passed",
            "disabled_fail_closed": "passed",
            "trunk_password_preservation": "passed",
            "call_cleanup_media_zero": "passed",
        },
        "cleanup": {
            "keys_revoked": resources.key_ids,
            "apps_disabled": resources.app_ids,
            "number_disabled": resources.number_id,
            "trunk_left_disabled": resources.trunk_id,
            "pending_operator_cleanup": ["remove_fixture_phone_number", "remove_fixture_trunk", "remove_native_did"],
        },
    }


async def cleanup(
    args: argparse.Namespace,
    browser_cookie: str,
    app_ids: list[str],
    key_ids: list[str],
    number_id: str | None,
    trunk_id: str | None,
) -> dict[str, object]:
    settings = get_settings()
    origin = args.origin or settings.web_origin
    api_base = args.base_url.rstrip("/") + "/api/v1"
    async with aiohttp.ClientSession(
        cookie_jar=aiohttp.CookieJar(unsafe=True), headers={"Origin": origin}
    ) as http:
        http.cookie_jar.update_cookies(
            {"gateway_session": browser_cookie}, response_url=URL(args.base_url)
        )
        disabled_number = number_id
        if not disabled_number:
            rows = list_value(
                await api_request(http, "GET", api_base, "/phone-numbers", stage="cleanup_numbers_read"),
                "cleanup_numbers_shape",
            )
            own = next(
                (
                    item
                    for item in rows
                    if isinstance(item, dict)
                    and item.get("number") == args.number
                    and item.get("label") == FIXTURE_LABEL
                ),
                None,
            )
            if isinstance(own, dict) and isinstance(own.get("id"), str):
                disabled_number = own["id"]
        if disabled_number:
            await api_request(
                http,
                "PATCH",
                api_base,
                f"/phone-numbers/{quote(disabled_number, safe='')}",
                stage="cleanup_number_disable",
                payload={"enabled": False},
            )
        revoked: list[str] = []
        for key_id in key_ids:
            await api_request(
                http,
                "DELETE",
                api_base,
                f"/api-keys/{quote(key_id, safe='')}",
                stage="cleanup_key_revoke",
                expected={204},
            )
            revoked.append(key_id)
        disabled: list[str] = []
        for app_id in app_ids:
            await api_request(
                http,
                "DELETE",
                api_base,
                f"/partner-apps/{quote(app_id, safe='')}",
                stage="cleanup_app_disable",
                expected={204},
            )
            disabled.append(app_id)
    return {
        "keys_revoked": revoked,
        "apps_disabled": disabled,
        "number_disabled": disabled_number,
        "trunk_left_disabled": trunk_id,
        "pending_operator_cleanup": ["remove_fixture_phone_number", "remove_fixture_trunk", "remove_native_did"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--number", required=True)
    parser.add_argument("--base-url", default="http://admin-ui")
    parser.add_argument("--ws-url", default="ws://admin-ui")
    parser.add_argument("--origin")
    return parser.parse_args()


async def main(args: argparse.Namespace) -> None:
    resources = ProbeResources([], [], [])
    cookie: str | None = None
    result: dict[str, object] | None = None
    failure: str | None = None
    try:
        cookie = operator_browser_cookie(args.organization_id)
        result = await run(args, resources, cookie)
    except ProbeFailure as error:
        failure = str(error)
    except Exception:
        failure = "unexpected_failure"
    finally:
        for session in resources.sessions:
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await session.close()
        cleanup_result: dict[str, object]
        if cookie is None:
            cleanup_result = {
                "keys_revoked": [],
                "apps_disabled": [],
                "number_disabled": resources.number_id,
                "trunk_left_disabled": resources.trunk_id,
                "cleanup_status": "not_attempted",
                "pending_operator_cleanup": [
                    "remove_fixture_phone_number",
                    "remove_fixture_trunk",
                    "remove_native_did",
                ],
            }
        else:
            try:
                cleanup_result = await cleanup(
                    args,
                    cookie,
                    resources.app_ids,
                    resources.key_ids,
                    resources.number_id,
                    resources.trunk_id,
                )
            except Exception:
                cleanup_result = {
                    "keys_revoked": [],
                    "apps_disabled": [],
                    "number_disabled": resources.number_id,
                    "trunk_left_disabled": resources.trunk_id,
                    "cleanup_status": "manual_cleanup_required",
                    "pending_operator_cleanup": [
                        "remove_fixture_phone_number",
                        "remove_fixture_trunk",
                        "remove_native_did",
                    ],
                }
        if failure:
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "stage": failure,
                        "cleanup": cleanup_result,
                    },
                    sort_keys=True,
                )
            )
            raise SystemExit(1)
        require(result is not None, "probe_result")
        result["cleanup"] = cleanup_result
        print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
