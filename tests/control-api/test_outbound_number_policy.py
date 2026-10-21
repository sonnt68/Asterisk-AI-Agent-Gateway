"""Selection rules for shared outbound caller-number grants."""

from collections.abc import Iterator

import pytest
from app.database import Base
from app.models import Organization, PartnerApp, PhoneNumber, PhoneNumberOutboundApp
from app.outbound_number_policy import resolve_outbound_policy
from app.telephony import managed_route_id
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session


@pytest.fixture
def database_session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _tenant(session: Session) -> tuple[Organization, PartnerApp]:
    organization = Organization(name="Operator")
    session.add(organization)
    session.flush()
    app = PartnerApp(
        organization_id=organization.id,
        name="Support",
        agent_slug="support-agent",
        allowed_destinations="from-internal:123",
        enabled=True,
    )
    session.add(app)
    session.commit()
    return organization, app


def _grant(
    session: Session,
    organization: Organization,
    app: PartnerApp,
    number: str,
    *,
    phone_enabled: bool = True,
    app_enabled: bool = True,
) -> PhoneNumber:
    app.enabled = app_enabled
    phone = PhoneNumber(
        id=managed_route_id(organization.id, number),
        organization_id=organization.id,
        partner_app_id=app.id,
        number=number,
        label="Outbound",
        enabled=phone_enabled,
        pbx_applied=True,
    )
    session.add(phone)
    session.flush()
    session.add(PhoneNumberOutboundApp(phone_number_id=phone.id, partner_app_id=app.id))
    session.commit()
    return phone


def test_no_assignments_preserve_legacy_caller_behavior(database_session: Session) -> None:
    organization, app = _tenant(database_session)
    policy = resolve_outbound_policy(organization.id, app.id, session_factory=lambda: database_session)
    assert policy.allowed_destinations == frozenset({"from-internal:123"})
    assert policy.caller_number is None


def test_disabled_partner_app_is_rejected_even_without_outbound_assignments(
    database_session: Session,
) -> None:
    organization, app = _tenant(database_session)
    app.enabled = False
    database_session.commit()

    with pytest.raises(PermissionError, match="unavailable"):
        resolve_outbound_policy(organization.id, app.id, session_factory=lambda: database_session)


def test_one_enabled_assignment_is_selected_and_disabled_rows_do_not_create_ambiguity(
    database_session: Session,
) -> None:
    organization, app = _tenant(database_session)
    _grant(database_session, organization, app, "+84900000011")
    _grant(
        database_session,
        organization,
        app,
        "+84900000012",
        phone_enabled=False,
    )

    policy = resolve_outbound_policy(organization.id, app.id, session_factory=lambda: database_session)
    assert policy.caller_number == "+84900000011"


def test_multiple_enabled_assignments_require_exact_explicit_selection(
    database_session: Session,
) -> None:
    organization, app = _tenant(database_session)
    _grant(database_session, organization, app, "+84900000021")
    _grant(database_session, organization, app, "+84900000022")

    with pytest.raises(ValueError, match="caller_number"):
        resolve_outbound_policy(organization.id, app.id, session_factory=lambda: database_session)
    selected = resolve_outbound_policy(
        organization.id,
        app.id,
        "+84900000022",
        session_factory=lambda: database_session,
    )
    assert selected.caller_number == "+84900000022"

    with pytest.raises(ValueError, match="exact"):
        resolve_outbound_policy(
            organization.id,
            app.id,
            "+849000-0022",
            session_factory=lambda: database_session,
        )
    with pytest.raises(PermissionError, match="enabled outbound assignment"):
        resolve_outbound_policy(
            organization.id,
            app.id,
            "+84900000099",
            session_factory=lambda: database_session,
        )


def test_stale_disabled_assignment_fails_closed_instead_of_using_legacy_default(
    database_session: Session,
) -> None:
    organization, app = _tenant(database_session)
    _grant(database_session, organization, app, "+84900000031", phone_enabled=False)

    with pytest.raises(PermissionError, match="No enabled"):
        resolve_outbound_policy(organization.id, app.id, session_factory=lambda: database_session)


def test_cross_org_assignment_is_not_returned_as_a_caller_number(
    database_session: Session,
) -> None:
    organization, app = _tenant(database_session)
    foreign_org = Organization(name="Foreign")
    database_session.add(foreign_org)
    database_session.flush()
    foreign_app = PartnerApp(
        organization_id=foreign_org.id,
        name="Foreign inbound",
        agent_slug="foreign-agent",
        enabled=True,
    )
    database_session.add(foreign_app)
    database_session.flush()
    phone = PhoneNumber(
        id=managed_route_id(foreign_org.id, "+84900000041"),
        organization_id=foreign_org.id,
        partner_app_id=foreign_app.id,
        number="+84900000041",
        label="Foreign",
        enabled=True,
        pbx_applied=True,
    )
    database_session.add(phone)
    database_session.flush()
    # A malformed association can exist at the database level; runtime tenant
    # filters must still refuse to expose the foreign number.
    database_session.add(
        PhoneNumberOutboundApp(phone_number_id=phone.id, partner_app_id=app.id)
    )
    database_session.commit()

    with pytest.raises(PermissionError, match="No enabled"):
        resolve_outbound_policy(organization.id, app.id, session_factory=lambda: database_session)
