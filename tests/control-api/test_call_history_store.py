"""Focused proof for durable call history and the legacy summary boundary."""

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from app.call_history_import import import_legacy_json
from app.call_history_store import CallHistoryStore
from app.database import Base
from app.models import CallRecord, CallSignal, Organization
from app.realtime_registry import Connection, ConnectionRegistry
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


class FakeSocket:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    async def send_json(self, payload: dict[str, object]) -> None:
        self.messages.append(payload)


def _database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'history.db'}", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return engine, factory


def _connection() -> Connection:
    return Connection(
        id="connection-1",
        organization_id="org-1",
        partner_app_id="app-1",
        agent_slug="support-agent",
        scopes={"calls:read"},
        socket=FakeSocket(),
    )


def test_start_captures_immutable_owner_and_initial_signal(tmp_path) -> None:
    _, factory = _database(tmp_path)
    with factory() as session:
        session.add(Organization(id="org-1", name="Operator"))
        session.commit()

    store = CallHistoryStore(factory)
    registry = ConnectionRegistry(store)
    connection = _connection()
    call = registry.reserve_call(connection)
    call.called_number = "123"
    call.routing_context = "from-internal"
    asyncio.run(registry.persist_start(call))

    with factory() as session:
        record = session.get(CallRecord, call.id)
        signal = session.get(CallSignal, (call.id, 0))
    assert record is not None
    assert record.organization_id == "org-1"
    assert record.partner_app_id == "app-1"
    assert record.called_number == "123"
    assert record.routing_context == "from-internal"
    assert record.direction == "outbound"
    assert record.source == "gateway"
    assert record.history_complete is True
    assert signal is None


def test_destination_metadata_is_immutable_after_start(tmp_path) -> None:
    _, factory = _database(tmp_path)
    with factory() as session:
        session.add(Organization(id="org-1", name="Operator"))
        session.commit()
    store = CallHistoryStore(factory)
    registry = ConnectionRegistry(store)
    call = registry.reserve_call(_connection())
    call.called_number = "123"
    call.routing_context = "from-internal"
    asyncio.run(registry.persist_start(call))

    call.called_number = "999"
    call.routing_context = "other-context"
    call.sequence = 1
    assert asyncio.run(
        store.record(call, {"status": "ringing", "sequence": 1})
    ) is False

    with factory() as session:
        record = session.get(CallRecord, call.id)
        signal = session.get(CallSignal, (call.id, 1))
    assert record is not None
    assert (record.called_number, record.routing_context) == ("123", "from-internal")
    assert signal is None


def test_record_is_ordered_and_duplicate_sequence_is_idempotent(tmp_path) -> None:
    _, factory = _database(tmp_path)
    with factory() as session:
        session.add(Organization(id="org-1", name="Operator"))
        session.commit()
    store = CallHistoryStore(factory)
    registry = ConnectionRegistry(store)
    call = registry.reserve_call(_connection())
    asyncio.run(registry.persist_start(call))

    call.status = "answered"
    call.answered = True
    call.answered_at = datetime.now(UTC)
    call.sequence = 1
    call.updated_at = datetime.now(UTC).isoformat()
    snapshot = {
        "status": "answered",
        "terminal": False,
        "answered": True,
        "sequence": 1,
        "updated_at": call.updated_at,
    }
    assert asyncio.run(store.record(call, snapshot)) is True
    assert asyncio.run(store.record(call, snapshot)) is True

    with factory() as session:
        signals = session.scalars(
            select(CallSignal).where(CallSignal.call_id == call.id).order_by(CallSignal.sequence)
        ).all()
        record = session.get(CallRecord, call.id)
    assert [signal.sequence for signal in signals] == [1]
    assert record is not None and record.status == "answered" and record.history_complete is True


def test_record_failure_is_observable_and_flushable(tmp_path) -> None:
    _, factory = _database(tmp_path)
    with factory() as session:
        session.add(Organization(id="org-1", name="Operator"))
        session.commit()
    store = CallHistoryStore(factory, retry_attempts=1)
    registry = ConnectionRegistry(store)
    call = registry.reserve_call(_connection())
    asyncio.run(registry.persist_start(call))
    call.sequence = 1
    call.status = "ringing"
    snapshot = {"status": "ringing", "sequence": 1, "updated_at": call.updated_at}
    original = store._record_sync

    def fail(payload):
        raise RuntimeError("database offline")

    store._record_sync = fail
    assert asyncio.run(store.record(call, snapshot)) is False
    store._record_sync = original
    assert asyncio.run(store.flush_pending()) == 1

    with factory() as session:
        assert session.get(CallSignal, (call.id, 1)) is not None


def test_pending_older_signal_is_kept_after_newer_sequence_commits(tmp_path) -> None:
    _, factory = _database(tmp_path)
    with factory() as session:
        session.add(Organization(id="org-1", name="Operator"))
        session.commit()
    store = CallHistoryStore(factory, retry_attempts=1)
    registry = ConnectionRegistry(store)
    call = registry.reserve_call(_connection())
    asyncio.run(registry.persist_start(call))
    original = store._record_sync
    failed_once = True

    def fail_first(payload):
        nonlocal failed_once
        if failed_once and payload.sequence == 1:
            failed_once = False
            raise RuntimeError("database offline")
        return original(payload)

    store._record_sync = fail_first
    call.sequence = 1
    call.status = "ringing"
    first = {"status": "ringing", "sequence": 1, "updated_at": call.updated_at}
    assert asyncio.run(store.record(call, first)) is False
    call.sequence = 2
    call.status = "answered"
    call.answered = True
    second = {"status": "answered", "sequence": 2, "answered": True, "updated_at": call.updated_at}
    assert asyncio.run(store.record(call, second)) is True
    assert asyncio.run(store.flush_pending()) == 1

    with factory() as session:
        signals = session.scalars(
            select(CallSignal).where(CallSignal.call_id == call.id).order_by(CallSignal.sequence)
        ).all()
        record = session.get(CallRecord, call.id)
    assert [signal.sequence for signal in signals] == [1, 2]
    assert record is not None and record.sequence == 2 and record.history_complete is True


def test_originate_http_failure_is_durable_without_call_status_notification(
    tmp_path, monkeypatch
) -> None:
    _, factory = _database(tmp_path)
    with factory() as session:
        session.add(Organization(id="org-1", name="Operator"))
        session.commit()
    store = CallHistoryStore(factory)
    registry = ConnectionRegistry(store)
    connection = _connection()
    connection.scopes.add("calls:originate")
    registry.connections[connection.id] = connection

    class PartnerSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, model, app_id):
            return SimpleNamespace(allowed_destinations="from-internal:123")

        def scalar(self, statement):
            return SimpleNamespace(
                id="app-1",
                organization_id="org-1",
                enabled=True,
                allowed_destinations="from-internal:123",
            )

        def execute(self, statement):
            return SimpleNamespace(all=lambda: [])

    class Response:
        def __init__(self, status):
            self.status = status

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def json(self):
            return {}

    class AriSession:
        def __init__(self, *args, **kwargs):
            self.posts = []
            self.deletes = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def post(self, url, **kwargs):
            self.posts.append((url, kwargs))
            return Response(503)

        def delete(self, url):
            self.deletes.append(url)
            return Response(204)

    from app import outbound_calls

    monkeypatch.setattr(outbound_calls, "registry", registry)
    monkeypatch.setattr(outbound_calls, "SessionLocal", PartnerSession)
    monkeypatch.setattr(
        outbound_calls,
        "get_settings",
        lambda: SimpleNamespace(
            ari_base_url="http://ari.test", ari_username=None, ari_password=None
        ),
    )
    monkeypatch.setattr(outbound_calls.aiohttp, "ClientSession", AriSession)

    with pytest.raises(RuntimeError, match="ARI originate returned 503"):
        asyncio.run(
            outbound_calls.originate(
                connection,
                {
                    "payload": {
                        "context": "from-internal",
                        "extension": "123",
                        "timeout": 4,
                    }
                },
            )
        )

    with factory() as session:
        record = session.scalar(select(CallRecord))
        failure = session.scalar(
            select(CallSignal).where(CallSignal.status == "failed")
        )
    assert registry.calls == {}
    assert connection.socket.messages == []
    assert record is not None
    assert record.status == "failed"
    assert record.reason == "originate_failed"
    assert record.terminal is True
    assert record.ended_at is not None
    assert failure is not None and failure.sequence == 1


def test_recover_interrupted_marks_restart_without_fake_end_time(tmp_path) -> None:
    _, factory = _database(tmp_path)
    with factory() as session:
        session.add(Organization(id="org-1", name="Operator"))
        session.commit()
    store = CallHistoryStore(factory)
    registry = ConnectionRegistry(store)
    call = registry.reserve_call(_connection())
    asyncio.run(registry.persist_start(call))
    assert asyncio.run(store.recover_interrupted()) == 1

    with factory() as session:
        record = session.get(CallRecord, call.id)
        signal = session.get(CallSignal, (call.id, 1))
    assert record is not None
    assert record.status == "failed"
    assert record.reason == "gateway_restarted"
    assert record.ended_at is None
    assert record.duration_seconds is None
    assert signal is not None and signal.reason == "gateway_restarted"


def test_legacy_import_is_grouped_idempotent_and_unassigned(tmp_path) -> None:
    _, factory = _database(tmp_path)
    with factory() as session:
        session.add(Organization(id="org-1", name="Operator"))
        session.commit()
    source = tmp_path / "legacy.json"
    source.write_text(
        json.dumps(
            {
                "timezone": "ICT",
                "records": [
                    {
                        "linkedid": "linked-1",
                        "uniqueid": "leg-1",
                        "calldate": "2026-10-20 10:00:00",
                        "disposition": "ANSWERED",
                        "duration": 23,
                        "billsec": 20,
                    },
                    {
                        "linkedid": "linked-1",
                        "uniqueid": "leg-2",
                        "calldate": "2026-10-20 10:00:01",
                        "disposition": "ANSWERED",
                        "duration": 0,
                        "billsec": 0,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    first = import_legacy_json(source, "org-1", session_factory=factory)
    second = import_legacy_json(source, "org-1", session_factory=factory)
    assert first.inserted == 1 and second.skipped == 1

    with factory() as session:
        record = session.scalar(select(CallRecord))
        assert record is not None
        assert record.source == "imported"
        assert record.partner_app_id is None
        assert record.agent_slug is None
        assert record.called_number is None
        assert record.routing_context is None
        assert record.history_complete is False
        assert session.scalar(select(CallSignal)) is None
