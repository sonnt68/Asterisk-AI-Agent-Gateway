"""Tenant-safe management tests for shared outbound caller numbers."""

import asyncio
from collections.abc import Iterator

import pytest
from app.auth import Principal
from app.database import Base
from app.models import Organization, PartnerApp, PhoneNumber, PhoneNumberOutboundApp
from app.phone_number_routes import create_phone_number, update_phone_number
from app.telephony import managed_route_id
from app.telephony_schemas import PhoneNumberCreate, PhoneNumberPatch
from fastapi import HTTPException
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session


class FakeBridge:
    async def save_did(self, payload: dict[str, object]) -> dict[str, object]:
        return {"route_id": payload["route_id"], "number": payload["number"]}


@pytest.fixture
def database_session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def tenant(database_session: Session, monkeypatch: pytest.MonkeyPatch):
    organization = Organization(name="Operator")
    other_organization = Organization(name="Other")
    database_session.add_all([organization, other_organization])
    database_session.flush()
    inbound = PartnerApp(
        organization_id=organization.id,
        name="Inbound",
        agent_slug="inbound-agent",
        enabled=True,
    )
    outbound = PartnerApp(
        organization_id=organization.id,
        name="Outbound",
        agent_slug="outbound-agent",
        enabled=True,
    )
    disabled = PartnerApp(
        organization_id=organization.id,
        name="Disabled",
        agent_slug="disabled-agent",
        enabled=False,
    )
    foreign = PartnerApp(
        organization_id=other_organization.id,
        name="Foreign",
        agent_slug="foreign-agent",
        enabled=True,
    )
    database_session.add_all([inbound, outbound, disabled, foreign])
    database_session.commit()
    monkeypatch.setenv("FREEPBX_OPERATOR_ORGANIZATION_ID", organization.id)
    monkeypatch.setenv("FREEPBX_BRIDGE_URL", "http://bridge.test")
    monkeypatch.setenv("FREEPBX_BRIDGE_TOKEN", "bridge-token")
    monkeypatch.setattr("app.phone_number_routes.bridge_client", lambda settings: FakeBridge())
    return (
        Principal("owner", organization.id, "owner"),
        organization,
        inbound,
        outbound,
        disabled,
        foreign,
    )


def _create(
    session: Session,
    principal: Principal,
    app: PartnerApp,
    number: str,
    outbound_ids: list[str] | None = None,
) -> dict[str, object]:
    payload = PhoneNumberCreate(
        number=number,
        label="Call routing",
        partner_app_id=app.id,
        **({} if outbound_ids is None else {"outbound_partner_app_ids": outbound_ids}),
    )
    return asyncio.run(create_phone_number(payload, principal, session))


def test_create_serializes_inbound_and_shared_outbound_directions(
    database_session: Session, tenant
) -> None:
    principal, organization, inbound, outbound, _, _ = tenant
    result = _create(
        database_session,
        principal,
        inbound,
        "+84900000001",
        [outbound.id],
    )

    assert result["partner_app_id"] == inbound.id
    assert result["outbound_partner_app_ids"] == [outbound.id]
    assert result["outbound_partner_apps"] == [
        {
            "id": outbound.id,
            "name": outbound.name,
            "agent_slug": outbound.agent_slug,
            "enabled": True,
        }
    ]
    phone_id = managed_route_id(organization.id, "+84900000001")
    association = database_session.get(
        PhoneNumberOutboundApp, (phone_id, outbound.id)
    )
    assert association is not None


def test_patch_omitted_preserves_and_empty_list_clears_assignments(
    database_session: Session, tenant
) -> None:
    principal, _, inbound, outbound, _, _ = tenant
    result = _create(database_session, principal, inbound, "+84900000002", [outbound.id])

    preserved = update_phone_number(
        str(result["id"]), PhoneNumberPatch(label="Renamed"), principal, database_session
    )
    assert preserved["outbound_partner_app_ids"] == [outbound.id]

    cleared = update_phone_number(
        str(result["id"]),
        PhoneNumberPatch(outbound_partner_app_ids=[]),
        principal,
        database_session,
    )
    assert cleared["outbound_partner_app_ids"] == []
    assert database_session.scalars(select(PhoneNumberOutboundApp)).all() == []


def test_existing_disabled_assignment_is_retained_but_new_disabled_assignment_is_rejected(
    database_session: Session, tenant
) -> None:
    principal, _, inbound, outbound, disabled, _ = tenant
    result = _create(database_session, principal, inbound, "+84900000003", [outbound.id])
    outbound.enabled = False
    database_session.commit()

    retained = update_phone_number(
        str(result["id"]),
        PhoneNumberPatch(outbound_partner_app_ids=[outbound.id]),
        principal,
        database_session,
    )
    assert retained["outbound_partner_app_ids"] == [outbound.id]
    assert retained["outbound_partner_apps"][0]["enabled"] is False

    with pytest.raises(HTTPException) as error:
        update_phone_number(
            str(result["id"]),
            PhoneNumberPatch(outbound_partner_app_ids=[disabled.id]),
            principal,
            database_session,
        )
    assert getattr(error.value, "status_code", None) == 422
    assert database_session.scalars(select(PhoneNumberOutboundApp)).all()[0].partner_app_id == outbound.id


def test_cross_org_assignment_fails_without_changing_inbound_owner(
    database_session: Session, tenant
) -> None:
    principal, _, inbound, _, _, foreign = tenant
    result = _create(database_session, principal, inbound, "+84900000004")

    with pytest.raises(HTTPException) as error:
        update_phone_number(
            str(result["id"]),
            PhoneNumberPatch(outbound_partner_app_ids=[foreign.id]),
            principal,
            database_session,
        )
    assert getattr(error.value, "status_code", None) == 422
    phone = database_session.get(PhoneNumber, result["id"])
    assert phone is not None and phone.partner_app_id == inbound.id


def test_admin_has_the_same_operator_assignment_access(
    database_session: Session, tenant
) -> None:
    _, organization, inbound, outbound, _, _ = tenant
    admin = Principal("admin", organization.id, "admin")
    result = _create(database_session, admin, inbound, "+84900000005", [outbound.id])
    assert result["outbound_partner_app_ids"] == [outbound.id]
