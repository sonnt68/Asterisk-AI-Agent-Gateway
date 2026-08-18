"""Validate deployed key revocation, token replay rejection, rate limit, and CSRF."""

import argparse
import asyncio
import json
import os

import aiohttp
import websockets


async def request(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    expected: set[int] = {200},
    **kwargs: object,
) -> tuple[int, object | None]:
    async with session.request(method, url, **kwargs) as response:
        payload = await response.json() if response.content_length else None
        if response.status not in expected:
            raise RuntimeError(f"{method} {url} returned {response.status}")
        return response.status, payload


async def run(args: argparse.Namespace) -> None:
    email = os.environ["GATEWAY_TEST_EMAIL"]
    password = os.environ["GATEWAY_TEST_PASSWORD"]
    base = f"{args.http_url}/api/v1"
    headers = {"Origin": args.origin}
    jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(cookie_jar=jar, headers=headers) as session:
        _, login = await request(
            session,
            "POST",
            f"{base}/auth/login",
            json={"email": email, "password": password},
        )
        _, apps = await request(
            session,
            "GET",
            f"{base}/organizations/{login['organization_id']}/partner-apps",
        )
        app = next(item for item in apps if item["agent_slug"] == args.agent_slug)
        revoked_key_id = None
        rate_key_id = None
        try:
            _, issued = await request(
                session,
                "POST",
                f"{base}/partner-apps/{app['id']}/api-keys",
                expected={201},
                json={"name": "ephemeral-revocation-probe", "scopes": app["scopes"]},
            )
            revoked_key_id = issued["id"]
            _, rotated = await request(
                session,
                "POST",
                f"{base}/api-keys/{revoked_key_id}/rotate",
                expected={201},
            )
            revoked_key_id = rotated["id"]
            _, token_data = await request(
                session,
                "POST",
                f"{base}/realtime/tokens",
                headers={"Authorization": f"Bearer {rotated['key']}"},
            )
            await request(
                session,
                "DELETE",
                f"{base}/api-keys/{revoked_key_id}",
                expected={204},
            )
            revoked_key_id = None
            await request(
                session,
                "POST",
                f"{base}/realtime/tokens",
                expected={401},
                headers={"Authorization": f"Bearer {issued['key']}"},
            )
            await request(
                session,
                "POST",
                f"{base}/realtime/tokens",
                expected={401},
                headers={"Authorization": f"Bearer {rotated['key']}"},
            )
            await assert_token_rejected(args.ws_url, token_data["token"])

            _, rate_key = await request(
                session,
                "POST",
                f"{base}/partner-apps/{app['id']}/api-keys",
                expected={201},
                json={"name": "ephemeral-rate-probe", "scopes": app["scopes"]},
            )
            rate_key_id = rate_key["id"]
            limited_at = await hit_rate_limit(
                session, f"{base}/realtime/tokens", rate_key["key"], args.max_attempts
            )
            await assert_csrf_denied(args, email, password)
        finally:
            for key_id in (revoked_key_id, rate_key_id):
                if key_id:
                    await request(
                        session,
                        "DELETE",
                        f"{base}/api-keys/{key_id}",
                        expected={204},
                    )
        print(
            json.dumps(
                {
                    "status": "passed",
                    "key_revocation": "passed",
                    "key_rotation": "passed",
                    "token_replay": "passed",
                    "rate_limited_at": limited_at,
                    "csrf_origin": "passed",
                }
            )
        )


async def assert_token_rejected(ws_url: str, token: str) -> None:
    try:
        async with websockets.connect(f"{ws_url}/v1/realtime?token={token}"):
            raise AssertionError("Revoked token opened a WebSocket")
    except websockets.exceptions.InvalidStatus as error:
        if error.response.status_code != 403:
            raise


async def hit_rate_limit(
    session: aiohttp.ClientSession, url: str, key: str, attempts: int
) -> int:
    for attempt in range(1, attempts + 1):
        async with session.post(
            url, headers={"Authorization": f"Bearer {key}"}
        ) as response:
            await response.read()
            if response.status == 429:
                return attempt
            if response.status != 200:
                raise RuntimeError(f"Unexpected token status {response.status}")
    raise AssertionError("Token endpoint did not enforce its configured rate limit")


async def assert_csrf_denied(
    args: argparse.Namespace, email: str, password: str
) -> None:
    async with aiohttp.ClientSession(
        cookie_jar=aiohttp.CookieJar(unsafe=True)
    ) as browser:
        await request(
            browser,
            "POST",
            f"{args.http_url}/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        await request(
            browser,
            "POST",
            f"{args.http_url}/api/v1/auth/logout",
            expected={403},
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--http-url", default="http://127.0.0.1:8080")
    parser.add_argument("--ws-url", default="ws://127.0.0.1:8080")
    parser.add_argument("--origin", required=True)
    parser.add_argument("--agent-slug", default="demo-agent")
    parser.add_argument("--max-attempts", type=int, default=65)
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
