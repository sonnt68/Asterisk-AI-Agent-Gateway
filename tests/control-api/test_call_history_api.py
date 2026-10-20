"""Integration proof for durable call-history visibility, queries, and persistence."""

import base64
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from app.auth import Principal, create_session
from app.call_history_routes import router
from app.database import Base, get_session
from app.models import ApiKey, CallRecord, CallSignal, Membership, Organization, PartnerApp, User
from app.security import hash_api_secret, hash_password, issue_api_key
from app.settings import get_settings
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _app_for_engine(engine):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    return app


@dataclass
class HistoryFixture:
    engine: object
    db_path: Path
    client: TestClient
    organization_id: str
    app_one_id: str
    app_two_id: str
    partner_key: str
    call_one: str
    imported_call: str


@pytest.fixture
def history(tmp_path: Path) -> Iterator[HistoryFixture]:
    db_path = tmp_path / "call-history.sqlite3"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        organization = Organization(id="00000000-0000-0000-0000-000000000001", name="Acme")
        other_org = Organization(id="00000000-0000-0000-0000-000000000002", name="Other")
        app_one = PartnerApp(
            id="10000000-0000-0000-0000-000000000001",
            organization_id=organization.id,
            name="Support",
            agent_slug="support-agent",
            scopes="calls:read,media:stream",
        )
        app_two = PartnerApp(
            id="10000000-0000-0000-0000-000000000002",
            organization_id=organization.id,
            name="Sales",
            agent_slug="sales-agent",
            scopes="calls:read",
        )
        other_app = PartnerApp(
            id="10000000-0000-0000-0000-000000000003",
            organization_id=other_org.id,
            name="Other",
            agent_slug="other-agent",
            scopes="calls:read",
        )
        owner = User(
            id="20000000-0000-0000-0000-000000000001",
            email="owner@example.test",
            password_hash=hash_password("owner-password-long"),
        )
        developer = User(
            id="20000000-0000-0000-0000-000000000002",
            email="developer@example.test",
            password_hash=hash_password("developer-password-long"),
        )
        admin = User(
            id="20000000-0000-0000-0000-000000000003",
            email="admin@example.test",
            password_hash=hash_password("admin-password-long"),
        )
        session.add_all([organization, other_org, app_one, app_two, other_app, owner, developer, admin])
        session.flush()
        organization_id = organization.id
        app_one_id = app_one.id
        app_two_id = app_two.id
        partner_key, prefix, secret = issue_api_key()
        session.add(
            ApiKey(
                id="30000000-0000-0000-0000-000000000001",
                organization_id=organization.id,
                partner_app_id=app_one.id,
                name="History reader",
                prefix=prefix,
                secret_hash=hash_api_secret(secret, get_settings()),
                scopes="calls:read",
            )
        )
        session.add_all(
            [
                Membership(organization_id=organization.id, user_id=owner.id, role="owner"),
                Membership(organization_id=organization.id, user_id=developer.id, role="developer"),
                Membership(organization_id=organization.id, user_id=admin.id, role="admin"),
            ]
        )
        session.commit()
        call_one = _add_call(session, organization.id, app_one.id, "00000000-0000-0000-0000-000000000101")
        imported_call = _add_call(
            session, organization.id, None, "00000000-0000-0000-0000-000000000199", source="imported"
        )
        _add_call(session, organization.id, app_two.id, "00000000-0000-0000-0000-000000000102")
        _add_call(session, other_org.id, other_app.id, "00000000-0000-0000-0000-000000000201")
        session.commit()

    app = _app_for_engine(engine)
    with TestClient(app) as client:
        yield HistoryFixture(
            engine, db_path, client, organization_id, app_one_id, app_two_id,
            partner_key, call_one, imported_call,
        )
    engine.dispose()


def _add_call(
    session: Session,
    organization_id: str,
    partner_app_id: str | None,
    call_id: str,
    *,
    source: str = "gateway",
    status: str = "completed",
    direction: str = "outbound",
    created_at: datetime | None = None,
) -> str:
    when = created_at or datetime.now(UTC)
    session.add(
        CallRecord(
            call_id=call_id,
            organization_id=organization_id,
            partner_app_id=partner_app_id,
            agent_slug="support-agent" if partner_app_id else None,
            direction=direction,
            source=source,
            status=status,
            terminal=True,
            answered=status == "completed",
            reason="completed" if status == "completed" else status,
            hangup_cause=16 if status == "completed" else None,
            dial_status="ANSWER" if status == "completed" else None,
            sequence=3,
            created_at=when,
            updated_at=when + timedelta(seconds=30),
            answered_at=when + timedelta(seconds=5) if status == "completed" else None,
            ended_at=when + timedelta(seconds=30),
            duration_seconds=30,
            talk_seconds=25,
            history_complete=source != "imported",
        )
    )
    return call_id


def _cookie_for(role: str, organization_id: str = "00000000-0000-0000-0000-000000000001") -> str:
    user_ids = {
        "owner": "20000000-0000-0000-0000-000000000001",
        "developer": "20000000-0000-0000-0000-000000000002",
        "admin": "20000000-0000-0000-0000-000000000003",
    }
    return create_session(Principal(user_ids[role], organization_id, role))


def _browser_client(history: HistoryFixture, role: str) -> TestClient:
    app = _app_for_engine(history.engine)
    client = TestClient(app)
    client.cookies.set("gateway_session", _cookie_for(role))
    return client


def test_partner_list_scopes_to_app_and_hides_imported_and_foreign_records(history: HistoryFixture) -> None:
    response = history.client.get(
        "/api/v1/partner/calls",
        headers={"Authorization": f"Bearer {history.partner_key}"},
    )
    assert response.status_code == 200
    ids = {item["call_id"] for item in response.json()["items"]}
    assert ids == {history.call_one}


def test_browser_owner_sees_imported_history_but_developer_does_not(history: HistoryFixture) -> None:
    owner = _browser_client(history, "owner")
    developer = _browser_client(history, "developer")
    admin = _browser_client(history, "admin")
    try:
        owner_response = owner.get("/api/v1/call-history")
        developer_response = developer.get("/api/v1/call-history")
        admin_response = admin.get("/api/v1/call-history")
    finally:
        owner.close()
        developer.close()
        admin.close()
    assert owner_response.status_code == developer_response.status_code == admin_response.status_code == 200
    owner_ids = {item["call_id"] for item in owner_response.json()["items"]}
    developer_ids = {item["call_id"] for item in developer_response.json()["items"]}
    admin_ids = {item["call_id"] for item in admin_response.json()["items"]}
    assert history.imported_call in owner_ids
    assert history.imported_call not in developer_ids
    assert history.imported_call in admin_ids


def test_browser_detail_and_signals_have_safe_shape_and_order(history: HistoryFixture) -> None:
    with Session(history.engine) as session:
        for sequence, status in enumerate(("dialing", "ringing", "answered"), start=1):
            session.add(
                CallSignal(
                    call_id=history.call_one,
                    sequence=sequence,
                    status=status,
                    terminal=status == "answered",
                    answered=status == "answered",
                    reason=None,
                    hangup_cause=None,
                    dial_status=None,
                    updated_at=datetime(2026, 10, 20, 12, sequence, tzinfo=UTC),
                )
            )
        session.commit()
    client = _browser_client(history, "owner")
    try:
        detail = client.get(f"/api/v1/call-history/{history.call_one}")
        first = client.get(f"/api/v1/call-history/{history.call_one}/signals", params={"limit": 2})
        second = client.get(
            f"/api/v1/call-history/{history.call_one}/signals",
            params={"limit": 2, "cursor": first.json()["next_cursor"]},
        )
        invalid_signal_limit = client.get(
            f"/api/v1/call-history/{history.call_one}/signals", params={"limit": 101}
        )
    finally:
        client.close()
    assert detail.status_code == 200
    assert set(detail.json()) == {
        "call_id", "partner_app_id", "agent_slug", "direction", "source", "status", "terminal",
        "answered", "reason", "hangup_cause", "dial_status", "sequence", "created_at",
        "updated_at", "answered_at", "ended_at", "duration_seconds", "talk_seconds", "history_complete",
    }
    assert not any(secret in detail.text.lower() for secret in ("phone", "channel_id", "organization_id"))
    assert first.status_code == second.status_code == 200
    assert [item["sequence"] for item in first.json()["items"]] == [1, 2]
    assert [item["sequence"] for item in second.json()["items"]] == [3]
    assert all(item["type"] == "call.status" for item in first.json()["items"] + second.json()["items"])
    assert invalid_signal_limit.status_code == 422


def test_list_filters_and_stable_tie_cursor_pagination(history: HistoryFixture) -> None:
    tie = datetime(2026, 10, 20, 10, 0, tzinfo=UTC)
    with Session(history.engine) as session:
        for suffix, status, direction in (("301", "busy", "inbound"), ("302", "busy", "inbound"), ("303", "busy", "outbound")):
            _add_call(
                session, history.organization_id, history.app_one_id,
                f"00000000-0000-0000-0000-000000000{suffix}",
                status=status, direction=direction, created_at=tie,
            )
        session.commit()
    headers = {"Authorization": f"Bearer {history.partner_key}"}
    first = history.client.get(
        "/api/v1/partner/calls", headers=headers, params={"status": "busy", "limit": 2}
    )
    assert first.status_code == 200
    assert [item["call_id"] for item in first.json()["items"]] == [
        "00000000-0000-0000-0000-000000000303",
        "00000000-0000-0000-0000-000000000302",
    ]
    second = history.client.get(
        "/api/v1/partner/calls",
        headers=headers,
        params={"status": "busy", "limit": 2, "cursor": first.json()["next_cursor"]},
    )
    assert [item["call_id"] for item in second.json()["items"]] == [
        "00000000-0000-0000-0000-000000000301"
    ]
    inbound = history.client.get(
        "/api/v1/partner/calls",
        headers=headers,
        params={"status": "busy", "direction": "inbound", "limit": 100},
    )
    assert [item["call_id"] for item in inbound.json()["items"]] == [
        "00000000-0000-0000-0000-000000000302",
        "00000000-0000-0000-0000-000000000301",
    ]
    date_range = history.client.get(
        "/api/v1/partner/calls",
        headers=headers,
        params={
            "status": "busy",
            "started_after": "2026-10-20T09:00:00Z",
            "started_before": "2026-10-20T11:00:00Z",
            "limit": 100,
        },
    )
    assert [item["call_id"] for item in date_range.json()["items"]] == [
        "00000000-0000-0000-0000-000000000303",
        "00000000-0000-0000-0000-000000000302",
        "00000000-0000-0000-0000-000000000301",
    ]


def test_unknown_and_foreign_details_use_same_generic_not_found(history: HistoryFixture) -> None:
    client = _browser_client(history, "owner")
    try:
        responses = [
            client.get("/api/v1/call-history/00000000-0000-0000-0000-000000000201"),
            client.get("/api/v1/call-history/00000000-0000-0000-0000-000000000999"),
        ]
    finally:
        client.close()
    assert [response.status_code for response in responses] == [404, 404]
    assert responses[0].json() == responses[1].json() == {"detail": "Call not found"}


def test_invalid_history_limits_cursors_and_time_filters_are_rejected(history: HistoryFixture) -> None:
    client = _browser_client(history, "owner")
    try:
        for params in ({"limit": 0}, {"limit": 101}, {"cursor": '{"call_id":"x"}'}, {"status": "not-a-status"}, {"direction": "sideways"}):
            response = client.get("/api/v1/call-history", params=params)
            assert response.status_code == 422, (params, response.text)
        naive = client.get("/api/v1/call-history", params={"started_after": "2026-10-20T00:00:00"})
        reversed_range = client.get(
            "/api/v1/call-history",
            params={"started_after": "2026-10-21T00:00:00Z", "started_before": "2026-10-20T00:00:00Z"},
        )
        for payload in (["2026-10-20T00:00:00Z", 1], [1, "bad-id"], {"a": 1, "b": 2}):
            cursor = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
            response = client.get("/api/v1/call-history", params={"cursor": cursor})
            assert response.status_code == 422
        for cursor in ("²", "١", "-1", "1.0"):
            response = client.get(
                f"/api/v1/call-history/{history.call_one}/signals", params={"cursor": cursor}
            )
            assert response.status_code == 422
    finally:
        client.close()
    assert naive.status_code == reversed_range.status_code == 422


def test_rows_survive_engine_restart_and_reopen(history: HistoryFixture) -> None:
    history.engine.dispose()
    reopened = create_engine(
        f"sqlite:///{history.db_path}", connect_args={"check_same_thread": False}
    )
    app = _app_for_engine(reopened)
    client = TestClient(app)
    client.cookies.set("gateway_session", _cookie_for("owner"))
    try:
        response = client.get(f"/api/v1/call-history/{history.call_one}")
    finally:
        client.close()
        reopened.dispose()
    assert response.status_code == 200
    assert response.json()["call_id"] == history.call_one

