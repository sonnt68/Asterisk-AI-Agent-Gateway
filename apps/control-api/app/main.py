"""ASGI entry point for the gateway control API."""

from fastapi import FastAPI
from sqlalchemy import select

from app.control_routes import router as control_router
from app.database import Base, SessionLocal, engine
from app.models import Membership, Organization, User
from app.security import hash_password
from app.settings import get_settings
from app.system_routes import router as system_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Asterisk AI Agent Gateway Control API",
        version="1.0.0",
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
    )
    app.include_router(system_router, prefix="/api/v1")
    app.include_router(control_router, prefix="/api/v1")

    @app.on_event("startup")
    def initialize_database() -> None:
        Base.metadata.create_all(engine)
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
    return app


app = create_app()
