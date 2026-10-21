"""Persistent tenant, identity, and partner-integration records."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def now() -> datetime:
    return datetime.now(UTC)


def identifier() -> str:
    return str(uuid4())


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))


class PartnerApp(Base):
    __tablename__ = "partner_apps"
    __table_args__ = (UniqueConstraint("organization_id", "agent_slug"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    agent_slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    scopes: Mapped[str] = mapped_column(Text, default="calls:read,media:stream")
    allowed_destinations: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PhoneNumber(Base):
    """Exact DID ownership and local PBX-apply state."""

    __tablename__ = "phone_numbers"
    __table_args__ = (UniqueConstraint("number", name="uq_phone_numbers_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    partner_app_id: Mapped[str] = mapped_column(
        ForeignKey("partner_apps.id"), index=True
    )
    number: Mapped[str] = mapped_column(String(33), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    pbx_applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, onupdate=now
    )


class PhoneNumberOutboundApp(Base):
    """Outbound caller-number grants; inbound ownership stays on PhoneNumber."""

    __tablename__ = "phone_number_outbound_apps"
    __table_args__ = (Index("ix_phone_number_outbound_apps_partner_app_id", "partner_app_id"),)

    phone_number_id: Mapped[str] = mapped_column(
        ForeignKey("phone_numbers.id", ondelete="CASCADE"), primary_key=True
    )
    partner_app_id: Mapped[str] = mapped_column(
        ForeignKey("partner_apps.id", ondelete="CASCADE"), primary_key=True
    )


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    partner_app_id: Mapped[str] = mapped_column(ForeignKey("partner_apps.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    prefix: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    secret_hash: Mapped[str] = mapped_column(String(64))
    scopes: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(100))
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CallRecord(Base):
    """Durable, partner-safe call metadata and its latest normalized state."""

    __tablename__ = "call_records"
    __table_args__ = (
        Index(
            "ix_call_records_org_app_created_call",
            "organization_id",
            "partner_app_id",
            "created_at",
            "call_id",
        ),
        Index(
            "ix_call_records_org_created_call",
            "organization_id",
            "created_at",
            "call_id",
        ),
    )
    call_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    partner_app_id: Mapped[str | None] = mapped_column(
        ForeignKey("partner_apps.id"), nullable=True, index=True
    )
    agent_slug: Mapped[str | None] = mapped_column(String(80), nullable=True)
    called_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    routing_context: Mapped[str | None] = mapped_column(String(80), nullable=True)
    direction: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32))
    terminal: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    answered: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    hangup_cause: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dial_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    answered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    talk_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    history_complete: Mapped[bool] = mapped_column(Boolean, default=True)


class CallSignal(Base):
    """An immutable normalized status snapshot for one call sequence."""

    __tablename__ = "call_signals"
    __table_args__ = (UniqueConstraint("call_id", "sequence"),)
    call_id: Mapped[str] = mapped_column(
        ForeignKey("call_records.call_id", ondelete="CASCADE"), primary_key=True
    )
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(32))
    terminal: Mapped[bool] = mapped_column(Boolean, default=False)
    answered: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    hangup_cause: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dial_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
