from datetime import UTC, datetime, timedelta

from app.auth import Principal
from app.control_routes import KeyRequest, create_key
from app.database import Base
from app.key_management_routes import rotate_key
from app.main import app
from app.models import ApiKey, Organization, PartnerApp
from app.settings import get_settings
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_session_cookie_write_requires_configured_origin() -> None:
    with TestClient(app) as client:
        client.cookies.set("gateway_session", "present")
        denied = client.post("/api/v1/auth/logout")
        allowed = client.post(
            "/api/v1/auth/logout", headers={"Origin": get_settings().web_origin}
        )
    assert denied.status_code == 403
    assert allowed.status_code == 204


def test_api_key_expiry_is_persisted() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        organization = Organization(name="Expiry owner")
        session.add(organization)
        session.flush()
        partner_app = PartnerApp(
            organization_id=organization.id,
            name="Expiry agent",
            agent_slug="expiry-agent",
            scopes="calls:read",
        )
        session.add(partner_app)
        session.commit()
        expires_at = datetime.now(UTC) + timedelta(hours=1)
        result = create_key(
            KeyRequest(name="Expiring", scopes=["calls:read"], expires_at=expires_at),
            partner_app.id,
            Principal("owner", organization.id, "owner"),
            session,
        )
        stored = session.get(ApiKey, result["id"])
        assert stored is not None
        assert stored.expires_at is not None
        assert stored.expires_at.replace(tzinfo=UTC) == expires_at

        rotated = rotate_key(
            stored.id,
            Principal("owner", organization.id, "owner"),
            session,
        )
        session.refresh(stored)
        replacement = session.get(ApiKey, rotated["id"])
        assert stored.revoked_at is not None
        assert replacement is not None
        assert replacement.secret_hash != rotated["key"]
        assert rotated["replaces"] == stored.id
