import pytest
from app.auth import Principal
from app.control_routes import KeyRequest, create_key, list_partner_apps
from app.database import Base
from app.models import ApiKey, Organization, PartnerApp
from fastapi import HTTPException
from sqlalchemy import create_engine
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
