"""Supervised ARI event listener that registers the gateway Stasis app."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

import aiohttp

from app.metrics import ari_connected
from app.settings import Settings

logger = logging.getLogger(__name__)


class AriEventListener:
    def __init__(
        self,
        settings: Settings,
        on_event: Callable[[dict[str, object], aiohttp.ClientSession], Awaitable[None]],
    ) -> None:
        self.settings = settings
        self.on_event = on_event
        self._running = False
        self.ready = False

    @property
    def configured(self) -> bool:
        return bool(
            self.settings.ari_base_url and self.settings.ari_username and self.settings.ari_password
        )

    async def run(self) -> None:
        if not self.configured:
            logger.warning("ARI listener disabled: Asterisk credentials are not configured")
            return
        self._running = True
        auth = aiohttp.BasicAuth(self.settings.ari_username or "", self.settings.ari_password or "")
        url = f"{self.settings.ari_base_url}/events?app=asterisk-ai-gateway"
        while self._running:
            try:
                async with aiohttp.ClientSession(auth=auth) as session:
                    async with session.ws_connect(url, heartbeat=20) as socket:
                        self.ready = True
                        ari_connected.set(1)
                        logger.info("ARI listener connected")
                        async for message in socket:
                            if message.type is aiohttp.WSMsgType.TEXT:
                                event = message.json()
                                logger.info(
                                    "ARI event received", extra={"event_type": event.get("type")}
                                )
                                try:
                                    await self.on_event(event, session)
                                except Exception:
                                    logger.exception(
                                        "ARI event handler failed",
                                        extra={"event_type": event.get("type")},
                                    )
                            if not self._running:
                                break
                        self.ready = False
                        ari_connected.set(0)
            except Exception as error:
                self.ready = False
                ari_connected.set(0)
                logger.warning("ARI listener reconnecting", extra={"error": str(error)})
                await asyncio.sleep(2)

    def stop(self) -> None:
        self._running = False
        self.ready = False
        ari_connected.set(0)
