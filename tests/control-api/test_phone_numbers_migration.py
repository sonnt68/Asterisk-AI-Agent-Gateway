"""Fresh and upgrade migration proof for exact phone-number mappings."""

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.models import PhoneNumber
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def _upgrade(database_url: str, revision: str) -> None:
    environment = os.environ.copy()
    environment["GATEWAY_DATABASE_URL"] = database_url
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_fresh_upgrade_creates_exact_phone_number_schema(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'gateway.sqlite3'}"
    _upgrade(database_url, "0004_call_destination")
    _upgrade(database_url, "head")
    inspector = inspect(create_engine(database_url))
    assert "phone_numbers" in inspector.get_table_names()
    columns = {column["name"] for column in inspector.get_columns("phone_numbers")}
    assert columns == {
        "id",
        "organization_id",
        "partner_app_id",
        "number",
        "label",
        "enabled",
        "pbx_applied",
        "created_at",
        "updated_at",
    }
    unique_constraints = inspector.get_unique_constraints("phone_numbers")
    assert {item["name"] for item in unique_constraints} == {"uq_phone_numbers_number"}

    partner_columns = {
        column["name"] for column in inspector.get_columns("partner_apps")
    }
    assert "deleted_at" in partner_columns
    assert next(
        column["nullable"]
        for column in inspector.get_columns("partner_apps")
        if column["name"] == "deleted_at"
    ) is True

    api_key_columns = {column["name"] for column in inspector.get_columns("api_keys")}
    assert "encrypted_secret" in api_key_columns
    assert next(
        column["nullable"]
        for column in inspector.get_columns("api_keys")
        if column["name"] == "encrypted_secret"
    ) is True

    outbound = inspector.get_columns("phone_number_outbound_apps")
    assert {column["name"] for column in outbound} == {"phone_number_id", "partner_app_id"}
    primary_key = inspector.get_pk_constraint("phone_number_outbound_apps")
    assert primary_key["constrained_columns"] == ["phone_number_id", "partner_app_id"]
    assert {
        item["name"] for item in inspector.get_indexes("phone_number_outbound_apps")
    } == {"ix_phone_number_outbound_apps_partner_app_id"}

    foreign_keys = inspector.get_foreign_keys("phone_number_outbound_apps")
    assert {
        (item["constrained_columns"][0], item["referred_table"])
        for item in foreign_keys
    } == {
        ("phone_number_id", "phone_numbers"),
        ("partner_app_id", "partner_apps"),
    }


def test_outbound_upgrade_preserves_existing_numbers_without_backfill(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'upgrade.sqlite3'}"
    _upgrade(database_url, "0005_phone_numbers")
    engine = create_engine(database_url)
    when = datetime(2026, 10, 21, 8, 0, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO organizations (id, name, created_at) "
                "VALUES (:id, :name, :created_at)"
            ),
            {"id": "org-existing", "name": "Existing", "created_at": when},
        )
        connection.execute(
            text(
                "INSERT INTO partner_apps "
                "(id, organization_id, name, agent_slug, enabled, scopes, "
                "allowed_destinations, created_at) VALUES "
                "(:id, :organization_id, :name, :agent_slug, :enabled, :scopes, "
                ":allowed_destinations, :created_at)"
            ),
            {
                "id": "app-existing",
                "organization_id": "org-existing",
                "name": "Existing app",
                "agent_slug": "existing-agent",
                "enabled": True,
                "scopes": "calls:read",
                "allowed_destinations": "",
                "created_at": when,
            },
        )
        connection.execute(
            text(
                "INSERT INTO api_keys "
                "(id, organization_id, partner_app_id, name, prefix, secret_hash, "
                "scopes, created_at) VALUES "
                "(:id, :organization_id, :partner_app_id, :name, :prefix, "
                ":secret_hash, :scopes, :created_at)"
            ),
            {
                "id": "key-existing",
                "organization_id": "org-existing",
                "partner_app_id": "app-existing",
                "name": "Existing key",
                "prefix": "existing01",
                "secret_hash": "a" * 64,
                "scopes": "calls:read",
                "created_at": when,
            },
        )
        connection.execute(
            text(
                "INSERT INTO phone_numbers "
                "(id, organization_id, partner_app_id, number, label, enabled, "
                "pbx_applied, created_at, updated_at) VALUES "
                "(:id, :organization_id, :partner_app_id, :number, :label, :enabled, "
                ":pbx_applied, :created_at, :updated_at)"
            ),
            {
                "id": "phone-existing",
                "organization_id": "org-existing",
                "partner_app_id": "app-existing",
                "number": "+84900000001",
                "label": "Existing DID",
                "enabled": True,
                "pbx_applied": False,
                "created_at": when,
                "updated_at": when,
            },
        )

    _upgrade(database_url, "head")
    with Session(engine) as session:
        stored = session.get(PhoneNumber, "phone-existing")
        assert stored is not None
        assert stored.number == "+84900000001"
        assert stored.partner_app_id == "app-existing"
        assert session.execute(
            text("SELECT deleted_at FROM partner_apps WHERE id = 'app-existing'")
        ).scalar_one() is None
        assert session.execute(
            text("SELECT encrypted_secret FROM api_keys WHERE id = 'key-existing'")
        ).scalar_one() is None
        assert session.execute(text("SELECT COUNT(*) FROM phone_number_outbound_apps")).scalar_one() == 0


def test_outbound_upgrade_enforces_both_foreign_keys(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'foreign-keys.sqlite3'}"
    _upgrade(database_url, "head")
    engine = create_engine(database_url)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    with Session(engine) as session:
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO phone_number_outbound_apps "
                    "(phone_number_id, partner_app_id) VALUES (:phone, :app)"
                ),
                {"phone": "missing-phone", "app": "missing-app"},
            )
            session.commit()
