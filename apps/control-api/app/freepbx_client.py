"""Narrow asynchronous client for the private FreePBX BMO bridge."""

from collections.abc import Mapping
from typing import Any

import aiohttp

from app.settings import Settings, get_settings


class BridgeError(RuntimeError):
    """A safe, user-facing bridge failure without remote details."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class FreePbxBridgeClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def configured(self) -> bool:
        return bool(
            self.settings.freepbx_bridge_url
            and self.settings.freepbx_bridge_token
            and self.settings.freepbx_operator_organization_id
        )

    async def _call(
        self, operation: str, payload: Mapping[str, Any] | None = None
    ) -> Any:
        if not self.configured:
            raise BridgeError("FreePBX bridge is not configured")
        headers = {"Authorization": f"Bearer {self.settings.freepbx_bridge_token}"}
        body = {"operation": operation, "payload": dict(payload or {})}
        timeout = aiohttp.ClientTimeout(total=90 if operation == "apply" else 10)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self.settings.freepbx_bridge_url or "",
                    json=body,
                    headers=headers,
                ) as response:
                    if response.status >= 400:
                        raise BridgeError(
                            "FreePBX bridge rejected request",
                            status_code=409 if response.status == 409 else response.status,
                        )
                    result = await response.json()
        except BridgeError:
            raise
        except (TimeoutError, aiohttp.ClientError, ValueError):
            raise BridgeError("FreePBX bridge unavailable") from None
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise BridgeError("FreePBX bridge rejected request")
        return result.get("data")

    async def status(self) -> Any:
        return await self._call("status")

    async def list_trunks(self) -> Any:
        return await self._call("list_trunks")

    async def save_trunk(self, payload: Mapping[str, Any]) -> Any:
        return await self._call("save_trunk", payload)

    async def save_did(self, payload: Mapping[str, Any]) -> Any:
        return await self._call("save_did", payload)

    async def apply(self) -> Any:
        return await self._call("apply")
