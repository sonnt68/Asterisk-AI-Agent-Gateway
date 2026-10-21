"""Focused proof for PBX administration and exact managed-DID state."""

import asyncio
from collections.abc import Iterator

import pytest
from app.asterisk_routes import apply_asterisk, create_trunk, update_trunk
from app.auth import Principal, require_principal
from app.database import Base
from app.freepbx_client import BridgeError
from app.main import app as control_app
from app.models import Organization, PartnerApp, PhoneNumber
from app.phone_number_routes import create_phone_number, update_phone_number
from app.telephony import managed_route_id
from app.telephony_access import sanitize_trunk
from app.telephony_schemas import PhoneNumberCreate, PhoneNumberPatch, TrunkCreate, TrunkPatch
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


class FakeBridge:
    def __init__(self) -> None:
        self.trunk_payloads: list[dict[str, object]] = []
        self.trunk_inventory: list[dict[str, object]] = []
        self.did_payloads: list[dict[str, object]] = []
        self.apply_result: dict[str, object] = {"applied_routes": []}
        self.fail_did = False

    @property
    def configured(self) -> bool:
        return True

    async def save_trunk(self, payload: dict[str, object]) -> dict[str, object]:
        self.trunk_payloads.append(payload)
        return {
            "id": str(payload.get("id", "trunk-1")),
            "name": payload.get("name", "carrier"),
            "host": payload.get("host", "sip.example.test"),
            "password": "must-never-return",
            "password_set": True,
        }

    async def list_trunks(self) -> dict[str, object]:
        return {"trunks": self.trunk_inventory}

    async def save_did(self, payload: dict[str, object]) -> dict[str, object]:
        if self.fail_did:
            raise BridgeError("FreePBX bridge rejected request", status_code=409)
        self.did_payloads.append(payload)
        return {"route_id": payload["route_id"], "number": payload["number"]}

    async def apply(self) -> dict[str, object]:
        return self.apply_result


@pytest.fixture
def database_session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def tenant(database_session: Session, monkeypatch: pytest.MonkeyPatch) -> tuple[Principal, Organization, PartnerApp]:
    organization = Organization(name="Operator")
    database_session.add(organization)
    database_session.flush()
    app = PartnerApp(
        organization_id=organization.id,
        name="Support",
        agent_slug="support-agent",
        enabled=True,
    )
    database_session.add(app)
    database_session.commit()
    monkeypatch.setenv("FREEPBX_OPERATOR_ORGANIZATION_ID", organization.id)
    monkeypatch.setenv("FREEPBX_BRIDGE_URL", "http://bridge.test")
    monkeypatch.setenv("FREEPBX_BRIDGE_TOKEN", "bridge-secret")
    return Principal("user-owner", organization.id, "owner"), organization, app


def test_trunk_password_is_forwarded_once_and_never_returned(
    database_session: Session,
    tenant: tuple[Principal, Organization, PartnerApp],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal, _, _ = tenant
    bridge = FakeBridge()
    monkeypatch.setattr("app.asterisk_routes.bridge_client", lambda settings: bridge)
    result = asyncio.run(
        create_trunk(
            TrunkCreate(name="carrier", host="sip.example.test", password="sip-secret"),
            principal,
            database_session,
        )
    )
    assert result["password_set"] is True
    assert "password" not in result
    assert bridge.trunk_payloads[0]["password"] == "sip-secret"

    bridge.trunk_payloads.clear()
    bridge_result = asyncio.run(
        create_trunk(
            TrunkCreate(name="carrier-2", host="sip.example.test"),
            principal,
            database_session,
        )
    )
    assert bridge_result["id"] == "trunk-1"

    asyncio.run(
        update_trunk(
            "trunk-1", TrunkPatch(name="renamed"), principal, database_session
        )
    )
    assert "password" not in bridge.trunk_payloads[-1]
    assert "username" not in bridge.trunk_payloads[-1]
    assert "from_domain" not in bridge.trunk_payloads[-1]


def test_trunk_patch_forwards_explicit_empty_optional_fields(
    database_session: Session,
    tenant: tuple[Principal, Organization, PartnerApp],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal, _, _ = tenant
    bridge = FakeBridge()
    monkeypatch.setattr("app.asterisk_routes.bridge_client", lambda settings: bridge)

    asyncio.run(
        update_trunk(
            "trunk-1",
            TrunkPatch(
                username="",
                auth_username="",
                from_domain="",
                from_user="",
                contact_user="",
            ),
            principal,
            database_session,
        )
    )

    payload = bridge.trunk_payloads[-1]
    assert payload["username"] == ""
    assert payload["auth_username"] == ""
    assert payload["from_domain"] == ""
    assert payload["from_user"] == ""
    assert payload["contact_user"] == ""


def test_trunk_patch_rejects_unsupported_native_mode_before_mutation(
    database_session: Session,
    tenant: tuple[Principal, Organization, PartnerApp],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal, _, _ = tenant
    bridge = FakeBridge()
    bridge.trunk_inventory = [
        {"id": "trunk-1", "authentication": "both", "registration": "receive"}
    ]
    monkeypatch.setattr("app.asterisk_routes.bridge_client", lambda settings: bridge)

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            update_trunk(
                "trunk-1", TrunkPatch(name="renamed"), principal, database_session
            )
        )

    assert error.value.status_code == 422
    assert bridge.trunk_payloads == []


def test_trunk_inventory_preserves_unknown_native_modes_for_read_only_display() -> None:
    trunk = sanitize_trunk(
        {"id": 7, "authentication": "both", "registration": "receive"}
    )

    assert trunk["id"] == "7"
    assert trunk["authentication"] == "both"
    assert trunk["registration"] == "receive"


def test_phone_number_reserves_exact_id_and_rolls_back_bridge_failure(
    database_session: Session,
    tenant: tuple[Principal, Organization, PartnerApp],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal, organization, app = tenant
    bridge = FakeBridge()
    monkeypatch.setattr("app.phone_number_routes.bridge_client", lambda settings: bridge)
    result = asyncio.run(
        create_phone_number(
            PhoneNumberCreate(number="+84901234567", label="Support", partner_app_id=app.id),
            principal,
            database_session,
        )
    )
    expected_id = managed_route_id(organization.id, "+84901234567")
    assert result["id"] == expected_id
    assert result["pbx_applied"] is False
    stored = database_session.scalar(select(PhoneNumber).where(PhoneNumber.id == expected_id))
    assert stored is not None

    bridge.fail_did = True
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            create_phone_number(
                PhoneNumberCreate(number="+84901234568", label="Fail", partner_app_id=app.id),
                principal,
                database_session,
            )
        )
    assert error.value.status_code == 409
    assert database_session.scalar(
        select(PhoneNumber).where(PhoneNumber.number == "+84901234568")
    ) is None


def test_phone_mapping_can_be_disabled_when_current_app_is_disabled(
    database_session: Session,
    tenant: tuple[Principal, Organization, PartnerApp],
) -> None:
    principal, organization, app = tenant
    route_id = managed_route_id(organization.id, "+84901234569")
    database_session.add(
        PhoneNumber(
            id=route_id,
            organization_id=organization.id,
            partner_app_id=app.id,
            number="+84901234569",
            label="Recoverable",
            enabled=True,
        )
    )
    database_session.commit()
    app.enabled = False
    database_session.commit()

    result = update_phone_number(
        route_id, PhoneNumberPatch(enabled=False), principal, database_session
    )

    assert result["enabled"] is False
    assert result["partner_app_id"] == app.id


def test_phone_mapping_can_reassign_and_enable_with_enabled_app(
    database_session: Session,
    tenant: tuple[Principal, Organization, PartnerApp],
) -> None:
    principal, organization, disabled_app = tenant
    replacement = PartnerApp(
        organization_id=organization.id,
        name="Replacement",
        agent_slug="replacement-agent",
        enabled=True,
    )
    database_session.add(replacement)
    database_session.flush()
    route_id = managed_route_id(organization.id, "+84901234570")
    database_session.add(
        PhoneNumber(
            id=route_id,
            organization_id=organization.id,
            partner_app_id=disabled_app.id,
            number="+84901234570",
            label="Recovery",
            enabled=False,
        )
    )
    database_session.commit()
    disabled_app.enabled = False
    database_session.commit()

    result = update_phone_number(
        route_id,
        PhoneNumberPatch(partner_app_id=replacement.id, enabled=True),
        principal,
        database_session,
    )

    assert result["partner_app_id"] == replacement.id
    assert result["enabled"] is True


def test_phone_mapping_cannot_enable_against_disabled_app(
    database_session: Session,
    tenant: tuple[Principal, Organization, PartnerApp],
) -> None:
    principal, organization, app = tenant
    route_id = managed_route_id(organization.id, "+84901234571")
    database_session.add(
        PhoneNumber(
            id=route_id,
            organization_id=organization.id,
            partner_app_id=app.id,
            number="+84901234571",
            label="Disabled app",
            enabled=False,
        )
    )
    database_session.commit()
    app.enabled = False
    database_session.commit()

    with pytest.raises(HTTPException) as error:
        update_phone_number(
            route_id, PhoneNumberPatch(enabled=True), principal, database_session
        )

    assert error.value.status_code == 422
    stored = database_session.get(PhoneNumber, route_id)
    assert stored is not None and stored.enabled is False


def test_apply_marks_only_exact_readback_and_rejects_active_calls(
    database_session: Session,
    tenant: tuple[Principal, Organization, PartnerApp],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal, organization, app = tenant
    route_id = managed_route_id(organization.id, "+84901112233")
    database_session.add(
        PhoneNumber(
            id=route_id,
            organization_id=organization.id,
            partner_app_id=app.id,
            number="+84901112233",
            label="Inbound",
            enabled=True,
            pbx_applied=False,
        )
    )
    database_session.commit()
    bridge = FakeBridge()
    bridge.apply_result = {"applied_routes": [{"route_id": route_id, "number": "+84901112233"}]}
    monkeypatch.setattr("app.asterisk_routes.bridge_client", lambda settings: bridge)
    result = asyncio.run(apply_asterisk(principal, database_session))
    assert result["applied_routes"] == bridge.apply_result["applied_routes"]
    assert database_session.get(PhoneNumber, route_id).pbx_applied is True


def test_apply_readback_failure_clears_previously_applied_routes(
    database_session: Session,
    tenant: tuple[Principal, Organization, PartnerApp],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal, organization, app = tenant
    applied_id = managed_route_id(organization.id, "+84901112234")
    pending_id = managed_route_id(organization.id, "+84901112235")
    database_session.add_all(
        [
            PhoneNumber(
                id=applied_id,
                organization_id=organization.id,
                partner_app_id=app.id,
                number="+84901112234",
                label="Previously applied",
                enabled=True,
                pbx_applied=True,
            ),
            PhoneNumber(
                id=pending_id,
                organization_id=organization.id,
                partner_app_id=app.id,
                number="+84901112235",
                label="Pending",
                enabled=True,
                pbx_applied=False,
            ),
        ]
    )
    database_session.commit()
    bridge = FakeBridge()
    monkeypatch.setattr("app.asterisk_routes.bridge_client", lambda settings: bridge)

    with pytest.raises(HTTPException) as error:
        asyncio.run(apply_asterisk(principal, database_session))

    assert error.value.status_code == 502
    assert database_session.get(PhoneNumber, applied_id).pbx_applied is False
    assert database_session.get(PhoneNumber, pending_id).pbx_applied is False


@pytest.mark.parametrize(
    "body",
    [
        ["password-secret"],
        {"name": "carrier", "host": "1.2.3.4", "extra": "password-secret"},
        {
            "name": "carrier",
            "host": "1.2.3.4",
            "password": {"nested": "password-secret"},
        },
    ],
)
def test_asterisk_validation_never_echoes_malformed_password_body(
    body: object,
    tenant: tuple[Principal, Organization, PartnerApp],
) -> None:
    principal, _, _ = tenant
    control_app.dependency_overrides[require_principal] = lambda: principal
    client = TestClient(control_app)
    try:
        response = client.post("/api/v1/asterisk/trunks", json=body)
    finally:
        client.close()
        control_app.dependency_overrides.pop(require_principal, None)

    assert response.status_code == 422
    assert "password-secret" not in response.text
    assert all("input" not in item and "ctx" not in item for item in response.json()["detail"])
