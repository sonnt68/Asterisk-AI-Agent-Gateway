"""Proof for persistent API-key recovery and encrypted secret boundaries."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import app.control_routes as control_routes
import app.key_management_routes as key_management_routes
import pytest
from app.auth import Principal, require_principal
from app.browser_security import BrowserOriginMiddleware
from app.control_routes import router as control_router
from app.database import Base, get_session
from app.key_management_routes import router as key_management_router
from app.management_routes import router as management_router
from app.models import ApiKey, AuditEvent, Organization, PartnerApp
from app.partner_auth import authenticate_api_key
from app.settings import get_settings
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

ALLOWED_ORIGIN = "http://allowed.test"
ENCRYPTION_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
WRONG_ENCRYPTION_KEY = "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE="
ORG_ID = "91000000-0000-0000-0000-000000000001"
OTHER_ORG_ID = "91000000-0000-0000-0000-000000000002"
APP_ID = "92000000-0000-0000-0000-000000000001"
SECOND_APP_ID = "92000000-0000-0000-0000-000000000002"
DISABLED_APP_ID = "92000000-0000-0000-0000-000000000003"
OTHER_APP_ID = "92000000-0000-0000-0000-000000000004"


@dataclass
class CopyFixture:
    engine: object
    client: TestClient
    organization_id: str
    app_id: str


def _configure_encryption(monkeypatch: pytest.MonkeyPatch, key: str | None) -> None:
    if key is None:
        monkeypatch.delenv("GATEWAY_API_KEY_ENCRYPTION_KEY", raising=False)
    else:
        monkeypatch.setenv("GATEWAY_API_KEY_ENCRYPTION_KEY", key)
    settings = get_settings()
    monkeypatch.setattr(control_routes, "settings", settings, raising=False)
    monkeypatch.setattr(key_management_routes, "settings", settings, raising=False)


def _client_for(engine: object, principal: Principal) -> TestClient:
    app = FastAPI()
    app.add_middleware(BrowserOriginMiddleware, allowed_origin=ALLOWED_ORIGIN)
    app.include_router(control_router, prefix="/api/v1")
    app.include_router(management_router, prefix="/api/v1")
    app.include_router(key_management_router, prefix="/api/v1")

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_principal] = lambda: principal
    return TestClient(app)


@pytest.fixture
def copy_fixture(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[CopyFixture]:
    _configure_encryption(monkeypatch, ENCRYPTION_KEY)
    engine = create_engine(
        f"sqlite:///{tmp_path / 'api-key-copy.sqlite3'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                Organization(id=ORG_ID, name="Customer"),
                Organization(id=OTHER_ORG_ID, name="Other customer"),
                PartnerApp(
                    id=APP_ID,
                    organization_id=ORG_ID,
                    name="Support",
                    agent_slug="support-agent",
                    scopes="calls:read,media:stream",
                ),
                PartnerApp(
                    id=SECOND_APP_ID,
                    organization_id=ORG_ID,
                    name="Sales",
                    agent_slug="sales-agent",
                    scopes="calls:read,media:stream",
                ),
                PartnerApp(
                    id=DISABLED_APP_ID,
                    organization_id=ORG_ID,
                    name="Disabled",
                    agent_slug="disabled-agent",
                    scopes="calls:read",
                    enabled=False,
                ),
                PartnerApp(
                    id=OTHER_APP_ID,
                    organization_id=OTHER_ORG_ID,
                    name="Other",
                    agent_slug="other-agent",
                    scopes="calls:read",
                ),
            ]
        )
        session.commit()

    principal = Principal("owner", ORG_ID, "owner")
    client = _client_for(engine, principal)
    with client:
        yield CopyFixture(engine, client, ORG_ID, APP_ID)
    engine.dispose()


def _create_key(fixture: CopyFixture, app_id: str = APP_ID, name: str = "Copy") -> dict:
    response = fixture.client.post(
        f"/api/v1/partner-apps/{app_id}/api-keys",
        json={"name": name, "scopes": ["calls:read"]},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _stored_key(fixture: CopyFixture, key_id: str) -> ApiKey:
    with Session(fixture.engine) as session:
        key = session.get(ApiKey, key_id)
        assert key is not None
        session.expunge(key)
        return key


def _set_secret(fixture: CopyFixture, key_id: str, value: str | None) -> None:
    with Session(fixture.engine) as session:
        key = session.get(ApiKey, key_id)
        assert key is not None
        key.encrypted_secret = value
        session.commit()


def test_encrypted_create_list_reveal_and_authentication(copy_fixture: CopyFixture) -> None:
    created = _create_key(copy_fixture)
    stored = _stored_key(copy_fixture, created["id"])
    assert stored.encrypted_secret
    assert created["key"] not in stored.secret_hash

    listed = copy_fixture.client.get(f"/api/v1/partner-apps/{APP_ID}/api-keys")
    assert listed.status_code == 200
    assert created["key"] not in listed.text
    metadata = listed.json()[0]
    assert metadata["copy_available"] is True
    assert "key" not in metadata
    assert "secret_hash" not in metadata
    assert "encrypted_secret" not in metadata

    revealed = copy_fixture.client.post(
        f"/api/v1/api-keys/{created['id']}/reveal",
        headers={"Origin": ALLOWED_ORIGIN},
    )
    assert revealed.status_code == 200
    assert revealed.json()["key"] == created["key"]
    assert revealed.json()["partner_app_id"] == APP_ID
    assert revealed.json()["agent_slug"] == "support-agent"
    assert "no-store" in revealed.headers["cache-control"].lower()
    assert revealed.headers["pragma"].lower() == "no-cache"

    with Session(copy_fixture.engine) as session:
        identity = authenticate_api_key(f"Bearer {created['key']}", session)
        assert identity.partner_app_id == APP_ID
        events = session.scalars(
            select(AuditEvent).where(
                AuditEvent.action == "api_key.copied",
                AuditEvent.target_id == created["id"],
            )
        ).all()
        assert len(events) == 1
    audit = copy_fixture.client.get("/api/v1/audit-events")
    assert audit.status_code == 200
    assert created["key"] not in audit.text


def test_rotate_returns_owner_app_and_replacement_is_recoverable(
    copy_fixture: CopyFixture,
) -> None:
    created = _create_key(copy_fixture)
    rotated = copy_fixture.client.post(f"/api/v1/api-keys/{created['id']}/rotate")
    assert rotated.status_code == 201, rotated.text
    body = rotated.json()
    assert body["partner_app_id"] == APP_ID
    assert body["replaces"] == created["id"]
    assert body["key"] != created["key"]
    assert _stored_key(copy_fixture, created["id"]).revoked_at is not None
    assert _stored_key(copy_fixture, body["id"]).encrypted_secret

    revealed = copy_fixture.client.post(f"/api/v1/api-keys/{body['id']}/reveal")
    assert revealed.status_code == 200
    assert revealed.json()["key"] == body["key"]


def test_legacy_hash_only_key_has_no_recovery_after_encryption_is_enabled(
    copy_fixture: CopyFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_encryption(monkeypatch, None)
    created = _create_key(copy_fixture, name="Legacy")
    stored = _stored_key(copy_fixture, created["id"])
    assert stored.encrypted_secret is None

    listed = copy_fixture.client.get(f"/api/v1/partner-apps/{APP_ID}/api-keys")
    assert listed.json()[0]["copy_available"] is False

    _configure_encryption(monkeypatch, ENCRYPTION_KEY)
    revealed = copy_fixture.client.post(f"/api/v1/api-keys/{created['id']}/reveal")
    assert revealed.status_code == 409


@pytest.mark.parametrize("configured_key", [WRONG_ENCRYPTION_KEY, None])
def test_reveal_fails_closed_for_wrong_or_missing_cipher_key(
    copy_fixture: CopyFixture,
    monkeypatch: pytest.MonkeyPatch,
    configured_key: str | None,
) -> None:
    created = _create_key(copy_fixture)
    _configure_encryption(monkeypatch, configured_key)
    response = copy_fixture.client.post(f"/api/v1/api-keys/{created['id']}/reveal")
    assert response.status_code == 503
    assert "key" not in response.text.lower()


def test_reveal_rejects_tampered_ciphertext_and_cross_row_swap(
    copy_fixture: CopyFixture,
) -> None:
    first = _create_key(copy_fixture, APP_ID, "First")
    second = _create_key(copy_fixture, SECOND_APP_ID, "Second")
    first_stored = _stored_key(copy_fixture, first["id"])
    second_stored = _stored_key(copy_fixture, second["id"])
    assert first_stored.encrypted_secret and second_stored.encrypted_secret

    _set_secret(
        copy_fixture,
        first["id"],
        first_stored.encrypted_secret[:-1]
        + ("A" if first_stored.encrypted_secret[-1] != "A" else "B"),
    )
    tampered = copy_fixture.client.post(f"/api/v1/api-keys/{first['id']}/reveal")
    assert tampered.status_code == 503

    _set_secret(copy_fixture, first["id"], second_stored.encrypted_secret)
    _set_secret(copy_fixture, second["id"], first_stored.encrypted_secret)
    assert copy_fixture.client.post(
        f"/api/v1/api-keys/{first['id']}/reveal"
    ).status_code == 503
    assert copy_fixture.client.post(
        f"/api/v1/api-keys/{second['id']}/reveal"
    ).status_code == 503


def test_reveal_requires_active_nonexpired_enabled_app_and_allowed_role(
    copy_fixture: CopyFixture,
) -> None:
    with Session(copy_fixture.engine) as session:
        session.get(PartnerApp, DISABLED_APP_ID).enabled = True
        session.commit()
    disabled_key = _create_key(copy_fixture, DISABLED_APP_ID, "Disabled")
    expired_key = _create_key(copy_fixture, SECOND_APP_ID, "Expired")
    revoked_key = _create_key(copy_fixture, APP_ID, "Revoked")

    with Session(copy_fixture.engine) as session:
        session.get(PartnerApp, DISABLED_APP_ID).enabled = False
        session.get(ApiKey, expired_key["id"]).expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    copy_fixture.client.delete(f"/api/v1/api-keys/{revoked_key['id']}")

    assert copy_fixture.client.post(
        f"/api/v1/api-keys/{disabled_key['id']}/reveal"
    ).status_code == 409
    assert copy_fixture.client.post(
        f"/api/v1/api-keys/{expired_key['id']}/reveal"
    ).status_code == 409
    assert copy_fixture.client.post(
        f"/api/v1/api-keys/{revoked_key['id']}/reveal"
    ).status_code == 409
    assert _stored_key(copy_fixture, revoked_key["id"]).encrypted_secret is None
    metadata = {
        item["id"]: item
        for item in copy_fixture.client.get(
            f"/api/v1/partner-apps/{APP_ID}/api-keys"
        ).json()
    }
    assert metadata[revoked_key["id"]]["copy_available"] is False

    developer = _client_for(copy_fixture.engine, Principal("developer", ORG_ID, "developer"))
    with developer:
        active = _create_key(copy_fixture)
        allowed = developer.post(f"/api/v1/api-keys/{active['id']}/reveal")
        assert allowed.status_code == 200

    viewer = _client_for(copy_fixture.engine, Principal("viewer", ORG_ID, "viewer"))
    with viewer:
        forbidden = viewer.post(f"/api/v1/api-keys/{active['id']}/reveal")
        assert forbidden.status_code == 403


def test_reveal_origin_and_tenant_boundaries(copy_fixture: CopyFixture) -> None:
    created = _create_key(copy_fixture)
    copy_fixture.client.cookies.set("gateway_session", "session")
    bad_origin = copy_fixture.client.post(
        f"/api/v1/api-keys/{created['id']}/reveal",
        headers={"Origin": "http://evil.test"},
    )
    assert bad_origin.status_code == 403

    foreign = _client_for(
        copy_fixture.engine, Principal("foreign", OTHER_ORG_ID, "owner")
    )
    with foreign:
        response = foreign.post(f"/api/v1/api-keys/{created['id']}/reveal")
        assert response.status_code == 404
