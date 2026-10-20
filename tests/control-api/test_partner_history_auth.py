"""Integration proof for partner API-key authentication and tenant isolation."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from app.call_history_routes import router
from app.database import Base, get_session
from app.models import ApiKey, CallRecord, Organization, PartnerApp
from app.security import hash_api_secret, issue_api_key
from app.settings import get_settings
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ORG_ID = "40000000-0000-0000-0000-000000000001"
OTHER_ORG_ID = "40000000-0000-0000-0000-000000000002"
APP_ID = "50000000-0000-0000-0000-000000000001"
OTHER_APP_ID = "50000000-0000-0000-0000-000000000002"
DISABLED_APP_ID = "50000000-0000-0000-0000-000000000003"
OWNED_CALL_ID = "60000000-0000-0000-0000-000000000001"
OTHER_APP_CALL_ID = "60000000-0000-0000-0000-000000000002"
OTHER_ORG_CALL_ID = "60000000-0000-0000-0000-000000000003"


def _app_for_engine(engine):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    return app


@dataclass
class AuthFixture:
    engine: object
    db_path: Path
    client: TestClient
    valid_key: str
    no_scope_key: str
    revoked_key: str
    expired_key: str
    disabled_key: str


def _key(
    session: Session,
    key_id: str,
    app: PartnerApp,
    *,
    scopes: str = "calls:read",
    expires_at: datetime | None = None,
    revoked_at: datetime | None = None,
) -> str:
    plaintext, prefix, secret = issue_api_key()
    session.add(
        ApiKey(
            id=key_id,
            organization_id=app.organization_id,
            partner_app_id=app.id,
            name=key_id,
            prefix=prefix,
            secret_hash=hash_api_secret(secret, get_settings()),
            scopes=scopes,
            expires_at=expires_at,
            revoked_at=revoked_at,
        )
    )
    return plaintext


def _call(session: Session, call_id: str, organization_id: str, partner_app_id: str) -> None:
    when = datetime(2026, 10, 20, 8, 0, tzinfo=UTC)
    session.add(
        CallRecord(
            call_id=call_id,
            organization_id=organization_id,
            partner_app_id=partner_app_id,
            agent_slug="support-agent",
            direction="outbound",
            source="gateway",
            status="completed",
            terminal=True,
            answered=True,
            reason="completed",
            sequence=2,
            created_at=when,
            updated_at=when,
            ended_at=when,
            duration_seconds=1,
            talk_seconds=1,
            history_complete=True,
        )
    )


@pytest.fixture
def auth_history(tmp_path: Path) -> Iterator[AuthFixture]:
    db_path = tmp_path / "partner-history-auth.sqlite3"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as session:
        organization = Organization(id=ORG_ID, name="Customer")
        other_org = Organization(id=OTHER_ORG_ID, name="Other customer")
        app = PartnerApp(
            id=APP_ID,
            organization_id=ORG_ID,
            name="Support",
            agent_slug="support-agent",
            scopes="calls:read,media:stream",
        )
        other_app = PartnerApp(
            id=OTHER_APP_ID,
            organization_id=ORG_ID,
            name="Sales",
            agent_slug="sales-agent",
            scopes="calls:read",
        )
        disabled_app = PartnerApp(
            id=DISABLED_APP_ID,
            organization_id=ORG_ID,
            name="Disabled",
            agent_slug="disabled-agent",
            scopes="calls:read",
            enabled=False,
        )
        session.add_all([organization, other_org, app, other_app, disabled_app])
        session.flush()
        valid_key = _key(session, "70000000-0000-0000-0000-000000000001", app)
        no_scope_key = _key(
            session, "70000000-0000-0000-0000-000000000002", app, scopes="media:stream"
        )
        revoked_key = _key(
            session,
            "70000000-0000-0000-0000-000000000003",
            app,
            revoked_at=now,
        )
        expired_key = _key(
            session,
            "70000000-0000-0000-0000-000000000004",
            app,
            expires_at=now - timedelta(seconds=1),
        )
        disabled_key = _key(
            session, "70000000-0000-0000-0000-000000000005", disabled_app
        )
        _call(session, OWNED_CALL_ID, ORG_ID, APP_ID)
        _call(session, OTHER_APP_CALL_ID, ORG_ID, OTHER_APP_ID)
        _call(session, OTHER_ORG_CALL_ID, OTHER_ORG_ID, OTHER_APP_ID)
        session.commit()

    app = _app_for_engine(engine)
    with TestClient(app) as client:
        yield AuthFixture(
            engine, db_path, client, valid_key, no_scope_key, revoked_key, expired_key, disabled_key
        )
    engine.dispose()


def _get_calls(fixture: AuthFixture, token: str | None):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    return fixture.client.get("/api/v1/partner/calls", headers=headers)


def test_valid_key_reads_only_its_organization_and_partner_app(auth_history: AuthFixture) -> None:
    response = _get_calls(auth_history, auth_history.valid_key)
    assert response.status_code == 200
    assert [item["call_id"] for item in response.json()["items"]] == [OWNED_CALL_ID]


@pytest.mark.parametrize("attribute", ["revoked_key", "expired_key", "disabled_key", "no_scope_key"])
def test_revoked_expired_disabled_and_missing_scope_keys_are_denied(
    auth_history: AuthFixture, attribute: str
) -> None:
    response = _get_calls(auth_history, getattr(auth_history, attribute))
    assert response.status_code == (403 if attribute in {"disabled_key", "no_scope_key"} else 401)


def test_wrong_secret_is_denied_without_disclosing_key_state(auth_history: AuthFixture) -> None:
    parts = auth_history.valid_key.split("_", 3)
    wrong = "_".join(parts[:3] + ["wrong-secret"])
    response = _get_calls(auth_history, wrong)
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid API key"}


def test_missing_or_malformed_bearer_header_is_401(auth_history: AuthFixture) -> None:
    assert _get_calls(auth_history, None).status_code == 401
    malformed = auth_history.client.get(
        "/api/v1/partner/calls", headers={"Authorization": "Basic abc"}
    )
    assert malformed.status_code == 401


def test_app_scope_reduction_applies_immediately_to_existing_key(auth_history: AuthFixture) -> None:
    assert _get_calls(auth_history, auth_history.valid_key).status_code == 200
    with Session(auth_history.engine) as session:
        app = session.get(PartnerApp, APP_ID)
        assert app is not None
        app.scopes = "media:stream"
        session.commit()
    response = _get_calls(auth_history, auth_history.valid_key)
    assert response.status_code == 403
    assert response.json() == {"detail": "calls:read scope required"}


def test_same_org_other_app_and_other_org_ids_are_generic_404(auth_history: AuthFixture) -> None:
    responses = [
        auth_history.client.get(
            f"/api/v1/partner/calls/{OTHER_APP_CALL_ID}",
            headers={"Authorization": f"Bearer {auth_history.valid_key}"},
        ),
        auth_history.client.get(
            f"/api/v1/partner/calls/{OTHER_ORG_CALL_ID}",
            headers={"Authorization": f"Bearer {auth_history.valid_key}"},
        ),
        auth_history.client.get(
            "/api/v1/partner/calls/60000000-0000-0000-0000-000000000099",
            headers={"Authorization": f"Bearer {auth_history.valid_key}"},
        ),
    ]
    assert all(response.status_code == 404 for response in responses)
    assert all(response.json() == {"detail": "Call not found"} for response in responses)


def test_signal_reads_use_the_same_partner_scope(auth_history: AuthFixture) -> None:
    response = auth_history.client.get(
        f"/api/v1/partner/calls/{OTHER_APP_CALL_ID}/signals",
        headers={"Authorization": f"Bearer {auth_history.valid_key}"},
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Call not found"}

