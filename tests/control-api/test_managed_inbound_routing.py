"""Managed DID routing preserves legacy agent precedence and tenant identity."""

import asyncio

from app.call_lifecycle import CallLifecycle
from app.database import Base
from app.models import Organization, PartnerApp, PhoneNumber, PhoneNumberOutboundApp
from app.realtime_registry import ConnectionRegistry
from app.telephony import managed_route_id
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


class FakeAri:
    def __init__(self, values: dict[str, str | None]) -> None:
        self.values = values
        self.deleted: list[str] = []

    async def channel_variable(self, session: object, channel_id: str, variable: str) -> str | None:
        return self.values.get(variable)

    async def delete(self, session: object, path: str) -> None:
        self.deleted.append(path)


class FakeConnection:
    def __init__(self, organization_id: str, partner_app_id: str, agent_slug: str) -> None:
        self.id = "connection-1"
        self.organization_id = organization_id
        self.partner_app_id = partner_app_id
        self.agent_slug = agent_slug


def test_managed_did_requires_exact_org_app_slug_and_records_exact_number(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'managed.sqlite3'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        organization = Organization(name="Operator")
        session.add(organization)
        session.flush()
        partner_app = PartnerApp(
            organization_id=organization.id,
            name="Support",
            agent_slug="support-agent",
            enabled=True,
        )
        session.add(partner_app)
        session.flush()
        session.add(
            PhoneNumber(
                id=managed_route_id(organization.id, "+84909998877"),
                organization_id=organization.id,
                partner_app_id=partner_app.id,
                number="+84909998877",
                label="Support",
                enabled=True,
                pbx_applied=True,
            )
        )
        session.commit()
        org_id, app_id = organization.id, partner_app.id

    registry = ConnectionRegistry()
    registry.connections["connection-1"] = FakeConnection(org_id, app_id, "support-agent")
    lifecycle = CallLifecycle.__new__(CallLifecycle)
    lifecycle.registry = registry
    lifecycle.session_factory = lambda: Session(engine)
    lifecycle.ari = FakeAri({"AI_GATEWAY_AGENT": None, "AI_GATEWAY_DID": "+84909998877"})
    activated: list[str] = []

    async def activate(call, channel, connection, session):
        activated.append(call.id)

    lifecycle._activate_call = activate
    asyncio.run(lifecycle._start_inbound("channel-1", {"dialplan": {"exten": "s", "context": "from-pstn"}}, object()))
    call = next(iter(registry.calls.values()))
    assert call.called_number == "+84909998877"
    assert call.partner_app_id == app_id
    assert activated == [call.id]


def test_nonempty_legacy_agent_stays_authoritative() -> None:
    registry = ConnectionRegistry()
    registry.connections["connection-1"] = FakeConnection("org", "app", "legacy-agent")
    lifecycle = CallLifecycle.__new__(CallLifecycle)
    lifecycle.registry = registry
    lifecycle.ari = FakeAri({"AI_GATEWAY_AGENT": "legacy-agent"})
    lifecycle._activate_call = _record_activation
    asyncio.run(lifecycle._start_inbound("channel-1", {"dialplan": {}}, object()))
    assert len(registry.calls) == 1


def test_managed_did_keeps_one_inbound_owner_when_outbound_is_shared(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'shared.sqlite3'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        organization = Organization(name="Operator")
        session.add(organization)
        session.flush()
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
        session.add_all([inbound, outbound])
        session.flush()
        phone = PhoneNumber(
            id=managed_route_id(organization.id, "+84909998878"),
            organization_id=organization.id,
            partner_app_id=inbound.id,
            number="+84909998878",
            label="Shared DID",
            enabled=True,
            pbx_applied=True,
        )
        session.add(phone)
        session.flush()
        session.add(
            PhoneNumberOutboundApp(phone_number_id=phone.id, partner_app_id=outbound.id)
        )
        session.commit()
        organization_id, inbound_id, outbound_id = organization.id, inbound.id, outbound.id

    registry = ConnectionRegistry()
    inbound_connection = FakeConnection(organization_id, inbound_id, "inbound-agent")
    inbound_connection.id = "inbound-connection"
    outbound_connection = FakeConnection(organization_id, outbound_id, "outbound-agent")
    outbound_connection.id = "outbound-connection"
    registry.connections[inbound_connection.id] = inbound_connection
    registry.connections[outbound_connection.id] = outbound_connection
    lifecycle = CallLifecycle.__new__(CallLifecycle)
    lifecycle.registry = registry
    lifecycle.session_factory = lambda: Session(engine)
    lifecycle.ari = FakeAri({"AI_GATEWAY_AGENT": None, "AI_GATEWAY_DID": "+84909998878"})
    activated: list[str] = []

    async def activate(call, channel, connection, session):
        activated.append(connection.agent_slug)

    lifecycle._activate_call = activate
    asyncio.run(
        lifecycle._start_inbound(
            "channel-shared",
            {"dialplan": {"exten": "s", "context": "from-pstn"}},
            object(),
        )
    )
    assert activated == ["inbound-agent"]
    call = next(iter(registry.calls.values()))
    assert call.partner_app_id == inbound_id


async def _record_activation(call, channel, connection, session):
    return None
