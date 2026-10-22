"""Tenant, retention, and authorization proof for logical Partner App deletion."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

import app.control_routes as control_routes
import app.key_management_routes as key_management_routes
import pytest
from app.auth import Principal, require_principal
from app.browser_security import BrowserOriginMiddleware
from app.call_history_routes import router as history_router
from app.control_routes import router as control_router
from app.database import Base, get_session
from app.key_management_routes import router as key_management_router
from app.management_routes import router as management_router
from app.models import (
    ApiKey,
    AuditEvent,
    CallRecord,
    CallSignal,
    Organization,
    PartnerApp,
    PhoneNumber,
    PhoneNumberOutboundApp,
)
from app.partner_auth import authenticate_api_key
from app.phone_number_routes import router as phone_number_router
from app.settings import get_settings
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

ALLOWED_ORIGIN = "http://allowed.test"
ENCRYPTION_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
ORG_ID = "93000000-0000-0000-0000-000000000001"
OTHER_ORG_ID = "93000000-0000-0000-0000-000000000002"
APP_ID = "94000000-0000-0000-0000-000000000001"
DISABLED_APP_ID = "94000000-0000-0000-0000-000000000002"
FOREIGN_APP_ID = "94000000-0000-0000-0000-000000000003"
PHONE_ID = "95000000-0000-0000-0000-000000000001"
CALL_ID = "96000000-0000-0000-0000-000000000001"


@dataclass
class DeleteFixture:
    engine: object
    client: TestClient
    organization_id: str
    app_id: str
    key_id: str
    plaintext_key: str


def _revoke_fixture_key(fixture: DeleteFixture) -> None:
    response = fixture.client.delete(
        f"/api/v1/api-keys/{fixture.key_id}",
        headers={"Origin": ALLOWED_ORIGIN},
    )
    assert response.status_code == 204


def _configure_encryption(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GATEWAY_API_KEY_ENCRYPTION_KEY", ENCRYPTION_KEY)
    settings = get_settings()
    monkeypatch.setattr(control_routes, "settings", settings, raising=False)
    monkeypatch.setattr(key_management_routes, "settings", settings, raising=False)


def _client_for(engine: object, principal: Principal) -> TestClient:
    app = FastAPI()
    app.add_middleware(BrowserOriginMiddleware, allowed_origin=ALLOWED_ORIGIN)
    for router in (
        control_router,
        management_router,
        key_management_router,
        history_router,
        phone_number_router,
    ):
        app.include_router(router, prefix="/api/v1")

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_principal] = lambda: principal
    return TestClient(app)


@pytest.fixture
def deletion_fixture(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[DeleteFixture]:
    _configure_encryption(monkeypatch)
    monkeypatch.setenv("FREEPBX_OPERATOR_ORGANIZATION_ID", ORG_ID)
    engine = create_engine(
        f"sqlite:///{tmp_path / 'partner-app-delete.sqlite3'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    when = datetime(2026, 10, 21, 8, 0, tzinfo=UTC)
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
                    id=DISABLED_APP_ID,
                    organization_id=ORG_ID,
                    name="Disabled",
                    agent_slug="disabled-agent",
                    enabled=False,
                    scopes="calls:read",
                ),
                PartnerApp(
                    id=FOREIGN_APP_ID,
                    organization_id=OTHER_ORG_ID,
                    name="Foreign",
                    agent_slug="foreign-agent",
                    scopes="calls:read",
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                PhoneNumber(
                    id=PHONE_ID,
                    organization_id=ORG_ID,
                    partner_app_id=APP_ID,
                    number="+84900000091",
                    label="Retained DID",
                    pbx_applied=True,
                ),
                CallRecord(
                    call_id=CALL_ID,
                    organization_id=ORG_ID,
                    partner_app_id=APP_ID,
                    agent_slug="support-agent",
                    called_number="+84900000091",
                    direction="inbound",
                    source="ari",
                    status="completed",
                    terminal=True,
                    answered=True,
                    reason="completed",
                    sequence=1,
                    created_at=when,
                    updated_at=when,
                    ended_at=when,
                    history_complete=True,
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                CallSignal(
                    call_id=CALL_ID,
                    sequence=1,
                    status="completed",
                    terminal=True,
                    answered=True,
                    updated_at=when,
                ),
                PhoneNumberOutboundApp(phone_number_id=PHONE_ID, partner_app_id=APP_ID),
            ]
        )
        session.commit()

    principal = Principal("owner", ORG_ID, "owner")
    client = _client_for(engine, principal)
    with client:
        response = client.post(
            f"/api/v1/partner-apps/{APP_ID}/api-keys",
            json={"name": "Delete proof", "scopes": ["calls:read"]},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        yield DeleteFixture(engine, client, ORG_ID, APP_ID, body["id"], body["key"])
    engine.dispose()


def test_revoke_allows_delete_and_retains_history_and_mappings(
    deletion_fixture: DeleteFixture,
) -> None:
    fixture = deletion_fixture
    _revoke_fixture_key(fixture)
    with Session(fixture.engine) as session:
        revoked_at_before_delete = session.get(ApiKey, fixture.key_id).revoked_at
        assert revoked_at_before_delete is not None
        assert session.get(ApiKey, fixture.key_id).encrypted_secret is None

    response = fixture.client.delete(
        f"/api/v1/partner-apps/{fixture.app_id}",
        headers={"Origin": ALLOWED_ORIGIN},
    )
    assert response.status_code == 204

    with Session(fixture.engine) as session:
        app = session.get(PartnerApp, fixture.app_id)
        assert app is not None
        assert app.deleted_at is not None
        assert app.enabled is False
        key = session.get(ApiKey, fixture.key_id)
        assert key is not None
        assert key.revoked_at == revoked_at_before_delete
        assert key.encrypted_secret is None
        assert session.get(PhoneNumber, PHONE_ID) is not None
        assert session.get(PhoneNumberOutboundApp, (PHONE_ID, fixture.app_id)) is not None
        assert session.get(CallRecord, CALL_ID) is not None
        assert session.get(CallSignal, (CALL_ID, 1)) is not None
        event = session.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "partner_app.deleted",
                AuditEvent.target_id == fixture.app_id,
            )
        )
        assert event is not None

    history = fixture.client.get(f"/api/v1/call-history/{CALL_ID}")
    assert history.status_code == 200
    assert history.json()["call_id"] == CALL_ID
    phone_rows = fixture.client.get("/api/v1/phone-numbers")
    assert phone_rows.status_code == 200
    assert [row["id"] for row in phone_rows.json()] == [PHONE_ID]


@pytest.mark.parametrize("disable_before_delete", [False, True])
def test_delete_rejects_unrevoked_keys_without_mutation(
    deletion_fixture: DeleteFixture,
    disable_before_delete: bool,
) -> None:
    fixture = deletion_fixture
    with Session(fixture.engine) as session:
        app = session.get(PartnerApp, fixture.app_id)
        key = session.get(ApiKey, fixture.key_id)
        assert app is not None and key is not None
        if disable_before_delete:
            app.enabled = False
            session.commit()
        enabled_before = app.enabled
        encrypted_before = key.encrypted_secret
        revoked_before = key.revoked_at
        assert revoked_before is None
        assert encrypted_before is not None

    response = fixture.client.delete(
        f"/api/v1/partner-apps/{fixture.app_id}",
        headers={"Origin": ALLOWED_ORIGIN},
    )
    assert response.status_code == 409

    with Session(fixture.engine) as session:
        app = session.get(PartnerApp, fixture.app_id)
        key = session.get(ApiKey, fixture.key_id)
        assert app is not None and key is not None
        assert app.deleted_at is None
        assert app.enabled is enabled_before
        assert key.revoked_at == revoked_before
        assert key.encrypted_secret == encrypted_before
        assert session.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "partner_app.deleted",
                AuditEvent.target_id == fixture.app_id,
            )
        ) is None


def test_delete_rejects_expired_unrevoked_key_without_mutation(
    deletion_fixture: DeleteFixture,
) -> None:
    fixture = deletion_fixture
    expired_at = datetime(2020, 1, 1, tzinfo=UTC)
    with Session(fixture.engine) as session:
        key = session.get(ApiKey, fixture.key_id)
        assert key is not None
        key.expires_at = expired_at
        session.commit()
        encrypted_before = key.encrypted_secret

    response = fixture.client.delete(
        f"/api/v1/partner-apps/{fixture.app_id}",
        headers={"Origin": ALLOWED_ORIGIN},
    )
    assert response.status_code == 409

    with Session(fixture.engine) as session:
        app = session.get(PartnerApp, fixture.app_id)
        key = session.get(ApiKey, fixture.key_id)
        assert app is not None and key is not None
        assert app.deleted_at is None
        assert app.enabled is True
        assert key.revoked_at is None
        assert key.encrypted_secret == encrypted_before
        assert key.expires_at is not None
        assert session.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "partner_app.deleted",
                AuditEvent.target_id == fixture.app_id,
            )
        ) is None


def test_deleted_app_is_hidden_but_existing_disabled_app_remains_listable(
    deletion_fixture: DeleteFixture,
) -> None:
    fixture = deletion_fixture
    _revoke_fixture_key(fixture)
    assert fixture.client.delete(f"/api/v1/partner-apps/{fixture.app_id}").status_code == 204
    listed = fixture.client.get(
        f"/api/v1/organizations/{fixture.organization_id}/partner-apps"
    )
    assert listed.status_code == 200
    ids = {item["id"] for item in listed.json()}
    assert DISABLED_APP_ID in ids
    assert fixture.app_id not in ids


def test_partner_app_name_patch_trims_and_preserves_identity_and_routing_policy(
    deletion_fixture: DeleteFixture,
) -> None:
    fixture = deletion_fixture
    with Session(fixture.engine) as session:
        app = session.get(PartnerApp, fixture.app_id)
        assert app is not None
        app.allowed_destinations = "from-internal:9899,from-pstn"
        session.commit()

    response = fixture.client.patch(
        f"/api/v1/partner-apps/{fixture.app_id}",
        json={"name": "  Renamed Support  "},
        headers={"Origin": ALLOWED_ORIGIN},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Renamed Support"
    assert body["agent_slug"] == "support-agent"
    assert body["allowed_destinations"] == ["from-internal:9899", "from-pstn"]

    with Session(fixture.engine) as session:
        app = session.get(PartnerApp, fixture.app_id)
        key = session.get(ApiKey, fixture.key_id)
        phone = session.get(PhoneNumber, PHONE_ID)
        call = session.get(CallRecord, CALL_ID)
        assert app is not None and key is not None and phone is not None and call is not None
        assert app.name == "Renamed Support"
        assert app.agent_slug == "support-agent"
        assert app.allowed_destinations == "from-internal:9899,from-pstn"
        assert key.name == "Delete proof"
        assert phone.partner_app_id == fixture.app_id
        assert call.agent_slug == "support-agent"

    history = fixture.client.get(f"/api/v1/call-history/{CALL_ID}")
    assert history.status_code == 200
    assert history.json()["agent_slug"] == "support-agent"


@pytest.mark.parametrize("invalid_name", ["   ", "x" * 121])
def test_partner_app_name_patch_rejects_blank_and_overlong_values(
    deletion_fixture: DeleteFixture,
    invalid_name: str,
) -> None:
    fixture = deletion_fixture
    response = fixture.client.patch(
        f"/api/v1/partner-apps/{fixture.app_id}",
        json={"name": invalid_name},
        headers={"Origin": ALLOWED_ORIGIN},
    )
    assert response.status_code == 422

    with Session(fixture.engine) as session:
        app = session.get(PartnerApp, fixture.app_id)
        assert app is not None
        assert app.name == "Support"
        assert app.agent_slug == "support-agent"


def test_partner_app_name_patch_cannot_cross_organization(
    deletion_fixture: DeleteFixture,
) -> None:
    fixture = deletion_fixture
    response = fixture.client.patch(
        f"/api/v1/partner-apps/{FOREIGN_APP_ID}",
        json={"name": "Hijacked"},
        headers={"Origin": ALLOWED_ORIGIN},
    )
    assert response.status_code == 404

    with Session(fixture.engine) as session:
        foreign = session.get(PartnerApp, FOREIGN_APP_ID)
        assert foreign is not None
        assert foreign.name == "Foreign"
        assert session.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "partner_app.updated",
                AuditEvent.target_id == FOREIGN_APP_ID,
            )
        ) is None


def test_delete_is_tenant_safe_role_gated_and_repeat_safe(
    deletion_fixture: DeleteFixture,
) -> None:
    fixture = deletion_fixture
    foreign = fixture.client.delete(f"/api/v1/partner-apps/{FOREIGN_APP_ID}")
    assert foreign.status_code == 404

    developer = _client_for(fixture.engine, Principal("developer", ORG_ID, "developer"))
    with developer:
        forbidden = developer.delete(f"/api/v1/partner-apps/{fixture.app_id}")
        assert forbidden.status_code == 403

    _revoke_fixture_key(fixture)
    first = fixture.client.delete(f"/api/v1/partner-apps/{fixture.app_id}")
    assert first.status_code == 204
    with Session(fixture.engine) as session:
        first_deleted_at = session.get(PartnerApp, fixture.app_id).deleted_at
    second = fixture.client.delete(f"/api/v1/partner-apps/{fixture.app_id}")
    assert second.status_code in {204, 404}
    with Session(fixture.engine) as session:
        assert session.get(PartnerApp, fixture.app_id).deleted_at == first_deleted_at


def test_deleted_app_rejects_management_key_routes_and_slug_reuse(
    deletion_fixture: DeleteFixture,
) -> None:
    fixture = deletion_fixture
    _revoke_fixture_key(fixture)
    assert fixture.client.delete(f"/api/v1/partner-apps/{fixture.app_id}").status_code == 204

    assert fixture.client.patch(
        f"/api/v1/partner-apps/{fixture.app_id}", json={"name": "Changed"}
    ).status_code == 404
    assert fixture.client.get(
        f"/api/v1/partner-apps/{fixture.app_id}/api-keys"
    ).status_code == 404
    assert fixture.client.post(
        f"/api/v1/partner-apps/{fixture.app_id}/api-keys",
        json={"name": "New", "scopes": ["calls:read"]},
    ).status_code == 404
    assert fixture.client.post(
        f"/api/v1/api-keys/{fixture.key_id}/rotate"
    ).status_code == 404
    assert fixture.client.post(
        f"/api/v1/api-keys/{fixture.key_id}/reveal"
    ).status_code == 404

    duplicate = fixture.client.post(
        f"/api/v1/organizations/{fixture.organization_id}/partner-apps",
        json={"name": "Replacement", "agent_slug": "support-agent"},
    )
    assert duplicate.status_code == 409

    partner_history = fixture.client.get(
        "/api/v1/partner/calls",
        headers={"Authorization": f"Bearer {fixture.plaintext_key}"},
    )
    assert partner_history.status_code == 401

    with Session(fixture.engine) as session:
        key = session.get(ApiKey, fixture.key_id)
        assert key is not None
        key.revoked_at = None
        session.commit()
        with pytest.raises(HTTPException) as error:
            authenticate_api_key(f"Bearer {fixture.plaintext_key}", session)
        assert getattr(error.value, "status_code", None) == 403


def test_delete_request_with_session_requires_configured_origin(
    deletion_fixture: DeleteFixture,
) -> None:
    fixture = deletion_fixture
    fixture.client.cookies.set("gateway_session", "session")
    response = fixture.client.delete(
        f"/api/v1/partner-apps/{fixture.app_id}",
        headers={"Origin": "http://evil.test"},
    )
    assert response.status_code == 403
