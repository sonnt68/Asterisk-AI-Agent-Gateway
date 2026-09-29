from datetime import UTC, datetime

import pytest
from app.auth import Principal
from app.control_routes import KeyRequest, create_key, list_partner_apps
from app.database import Base
from app.key_management_routes import delete_revoked_key
from app.models import ApiKey, AuditEvent, Organization, PartnerApp
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


@pytest.fixture
def database_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_tenant_cannot_list_another_organizations_apps(database_session: Session) -> None:
    first = Organization(name="First")
    second = Organization(name="Second")
    database_session.add_all([first, second])
    database_session.flush()
    database_session.add(
        PartnerApp(
            organization_id=second.id,
            name="Private agent",
            agent_slug="private-agent",
        )
    )
    database_session.commit()

    with pytest.raises(HTTPException) as error:
        list_partner_apps(
            second.id,
            Principal("user-first", first.id, "owner"),
            database_session,
        )
    assert error.value.status_code == 404


def test_key_scope_must_be_subset_and_plaintext_is_not_stored(
    database_session: Session,
) -> None:
    organization = Organization(name="Owner")
    database_session.add(organization)
    database_session.flush()
    app = PartnerApp(
        organization_id=organization.id,
        name="Scoped agent",
        agent_slug="scoped-agent",
        scopes="calls:read,media:stream",
    )
    database_session.add(app)
    database_session.commit()
    principal = Principal("user-owner", organization.id, "owner")

    with pytest.raises(HTTPException) as error:
        create_key(
            KeyRequest(name="Too broad", scopes=["calls:read", "calls:transfer"]),
            app.id,
            principal,
            database_session,
        )
    assert error.value.status_code == 422

    result = create_key(
        KeyRequest(name="Read only", scopes=["calls:read"]),
        app.id,
        principal,
        database_session,
    )
    stored = database_session.get(ApiKey, result["id"])
    assert stored is not None
    assert result["key"] not in stored.secret_hash
    assert stored.secret_hash != result["key"]


def test_only_revoked_keys_can_be_deleted_and_audited(database_session: Session) -> None:
    owner = Organization(name="Owner")
    other = Organization(name="Other")
    database_session.add_all([owner, other])
    database_session.flush()

    owner_app = PartnerApp(
        organization_id=owner.id,
        name="Owner app",
        agent_slug="owner-app",
        scopes="calls:read",
    )
    other_app = PartnerApp(
        organization_id=other.id,
        name="Other app",
        agent_slug="other-app",
        scopes="calls:read",
    )
    database_session.add_all([owner_app, other_app])
    database_session.flush()

    revoked = ApiKey(
        organization_id=owner.id,
        partner_app_id=owner_app.id,
        name="Revoked",
        prefix="revoked001",
        secret_hash="a" * 64,
        scopes="calls:read",
        revoked_at=datetime.now(UTC),
    )
    active = ApiKey(
        organization_id=owner.id,
        partner_app_id=owner_app.id,
        name="Active",
        prefix="active0001",
        secret_hash="b" * 64,
        scopes="calls:read",
    )
    other_revoked = ApiKey(
        organization_id=other.id,
        partner_app_id=other_app.id,
        name="Other revoked",
        prefix="other00001",
        secret_hash="c" * 64,
        scopes="calls:read",
        revoked_at=datetime.now(UTC),
    )
    database_session.add_all([revoked, active, other_revoked])
    database_session.commit()
    principal = Principal("user-owner", owner.id, "owner")

    response = delete_revoked_key(revoked.id, principal, database_session)

    assert response.status_code == 204
    assert database_session.get(ApiKey, revoked.id) is None
    event = database_session.scalar(select(AuditEvent).where(AuditEvent.target_id == revoked.id))
    assert event is not None
    assert event.organization_id == owner.id
    assert event.action == "api_key.deleted"

    with pytest.raises(HTTPException) as active_error:
        delete_revoked_key(active.id, principal, database_session)
    assert active_error.value.status_code == 409
    assert database_session.get(ApiKey, active.id) is not None

    with pytest.raises(HTTPException) as tenant_error:
        delete_revoked_key(other_revoked.id, principal, database_session)
    assert tenant_error.value.status_code == 404
    assert database_session.get(ApiKey, other_revoked.id) is not None
