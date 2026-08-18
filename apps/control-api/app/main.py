"""ASGI entry point and owned service lifecycle."""

import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from gateway.audiosocket_server import AudioSocketServer
from gateway.external_media_manager import ExternalMediaManager
from sqlalchemy import select

from app.ari_listener import AriEventListener
from app.auth_routes import router as auth_router
from app.browser_security import BrowserOriginMiddleware
from app.call_lifecycle import CallLifecycle
from app.control_routes import router as control_router
from app.database import SessionLocal
from app.key_management_routes import router as key_management_router
from app.management_routes import router as management_router
from app.models import Membership, Organization, User
from app.presence import RedisPresence
from app.realtime_registry import registry
from app.realtime_socket import router as realtime_router
from app.runtime_routes import router as runtime_router
from app.security import hash_password
from app.settings import get_settings
from app.system_routes import router as system_router


def bootstrap_database() -> None:
    settings = get_settings()
    if not settings.bootstrap_email or not settings.bootstrap_password:
        return
    with SessionLocal() as session:
        existing = session.scalar(select(User).where(User.email == settings.bootstrap_email.lower()))
        if existing:
            return
        organization = Organization(name="Default organization")
        user = User(email=settings.bootstrap_email.lower(), password_hash=hash_password(settings.bootstrap_password))
        session.add_all([organization, user])
        session.flush()
        session.add(Membership(organization_id=organization.id, user_id=user.id, role="owner"))
        session.commit()


def create_app() -> FastAPI:
    settings = get_settings()
    lifecycle: CallLifecycle

    async def media_uuid(connection_id: str, call_id: str) -> bool:
        return await lifecycle.on_media_uuid(connection_id, call_id)

    async def media_audio(connection_id: str, payload: bytes) -> None:
        await lifecycle.on_media_audio(connection_id, payload)

    async def media_disconnect(connection_id: str) -> None:
        await lifecycle.on_media_disconnect(connection_id)

    async def media_dtmf(connection_id: str, digit: str) -> None:
        await lifecycle.on_media_dtmf(connection_id, digit)

    audio_server = AudioSocketServer(
        settings.audiosocket_host,
        settings.audiosocket_port,
        media_uuid,
        media_audio,
        media_disconnect,
        media_dtmf,
    )
    external_media = ExternalMediaManager(settings.external_media_host)
    lifecycle = CallLifecycle(settings, registry, audio_server, external_media)
    listener = AriEventListener(settings, lifecycle.on_ari_event)
    presence = RedisPresence(settings.redis_url) if settings.redis_url else None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        bootstrap_database()
        if presence and not await presence.ready():
            raise RuntimeError("Redis presence store is unavailable")
        await audio_server.start()
        app.state.audio_server = audio_server
        app.state.call_lifecycle = lifecycle
        app.state.presence = presence
        app.state.ari_listener = listener
        listener_task = asyncio.create_task(listener.run())
        yield
        listener.stop()
        listener_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await listener_task
        await audio_server.stop()
        external_media.close_all()
        if presence:
            await presence.close()

    app = FastAPI(
        title="Asterisk AI Agent Gateway Control API",
        version="1.0.0",
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(BrowserOriginMiddleware, allowed_origin=settings.web_origin)
    app.include_router(system_router, prefix="/api/v1")
    app.include_router(control_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(management_router, prefix="/api/v1")
    app.include_router(key_management_router, prefix="/api/v1")
    app.include_router(runtime_router, prefix="/api/v1")
    app.include_router(realtime_router)
    return app


app = create_app()
