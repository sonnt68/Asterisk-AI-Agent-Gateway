"""Tenant-safe outbound caller-number assignments and selection."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import PartnerApp, PhoneNumber, PhoneNumberOutboundApp

CALLER_NUMBER_PATTERN = re.compile(r"^\+?[0-9]{1,32}$")
_MISSING = object()


@dataclass(frozen=True, slots=True)
class OutboundPolicy:
    allowed_destinations: frozenset[str]
    caller_number: str | None


def outbound_apps_for_phone(
    session: Session, phone_number_id: str, organization_id: str
) -> list[PartnerApp]:
    return list(
        session.scalars(
            select(PartnerApp)
            .join(
                PhoneNumberOutboundApp,
                PhoneNumberOutboundApp.partner_app_id == PartnerApp.id,
            )
            .join(PhoneNumber, PhoneNumber.id == PhoneNumberOutboundApp.phone_number_id)
            .where(
                PhoneNumberOutboundApp.phone_number_id == phone_number_id,
                PhoneNumber.organization_id == organization_id,
                PartnerApp.organization_id == organization_id,
            )
            .order_by(PartnerApp.name, PartnerApp.id)
        )
    )


def _selected_apps(
    session: Session,
    organization_id: str,
    app_ids: list[str],
    existing_ids: set[str],
) -> list[PartnerApp]:
    if len(app_ids) != len(set(app_ids)):
        raise ValueError("Outbound Partner App assignments must be unique")
    if not app_ids:
        return []
    apps = list(
        session.scalars(
            select(PartnerApp).where(
                PartnerApp.organization_id == organization_id,
                PartnerApp.id.in_(app_ids),
            )
        )
    )
    by_id = {app.id: app for app in apps}
    if set(by_id) != set(app_ids):
        raise ValueError("Outbound Partner App must belong to this organization")
    if any(not by_id[app_id].enabled for app_id in set(app_ids) - existing_ids):
        raise ValueError("New outbound Partner App assignments must be enabled")
    return [by_id[app_id] for app_id in app_ids]


def replace_outbound_apps(
    session: Session,
    phone: PhoneNumber,
    organization_id: str,
    app_ids: list[str],
) -> list[PartnerApp]:
    existing = outbound_apps_for_phone(session, phone.id, organization_id)
    apps = _selected_apps(session, organization_id, app_ids, {app.id for app in existing})
    session.execute(
        delete(PhoneNumberOutboundApp).where(
            PhoneNumberOutboundApp.phone_number_id == phone.id
        )
    )
    session.add_all(
        [
            PhoneNumberOutboundApp(phone_number_id=phone.id, partner_app_id=app.id)
            for app in apps
        ]
    )
    return apps


def _caller_number(value: object) -> str | None:
    if value is _MISSING:
        return None
    if not isinstance(value, str) or not CALLER_NUMBER_PATTERN.fullmatch(value):
        raise ValueError("Caller number must be an exact + or digit string")
    return value


def resolve_outbound_policy(
    organization_id: str,
    partner_app_id: str,
    caller_number: object = _MISSING,
    *,
    session_factory: Callable[[], Session] = SessionLocal,
) -> OutboundPolicy:
    requested = _caller_number(caller_number)
    with session_factory() as session:
        app = session.scalar(
            select(PartnerApp).where(
                PartnerApp.id == partner_app_id,
                PartnerApp.organization_id == organization_id,
            )
        )
        if not app or not app.enabled:
            raise PermissionError("Partner application is unavailable")
        rows = session.execute(
            select(PhoneNumber, PartnerApp)
            .join(
                PhoneNumberOutboundApp,
                PhoneNumberOutboundApp.phone_number_id == PhoneNumber.id,
            )
            .join(PartnerApp, PartnerApp.id == PhoneNumberOutboundApp.partner_app_id)
            .where(PhoneNumberOutboundApp.partner_app_id == partner_app_id)
        ).all()
        eligible = sorted(
            {
                phone.number
                for phone, assigned_app in rows
                if phone.organization_id == organization_id
                and assigned_app.organization_id == organization_id
                and phone.enabled
                and assigned_app.enabled
            }
        )
        if requested is not None:
            if requested not in eligible:
                raise PermissionError("Caller number is not an enabled outbound assignment")
            selected = requested
        elif not rows:
            selected = None
        elif not eligible:
            raise PermissionError("No enabled outbound caller number is available")
        elif len(eligible) > 1:
            raise ValueError("Multiple outbound caller numbers require caller_number")
        else:
            selected = eligible[0]
        allowed = frozenset(app.allowed_destinations.split(","))
        return OutboundPolicy(allowed, selected)


async def resolve_outbound_policy_async(
    organization_id: str,
    partner_app_id: str,
    caller_number: object = _MISSING,
    *,
    session_factory: Callable[[], Session] = SessionLocal,
) -> OutboundPolicy:
    return await asyncio.to_thread(
        resolve_outbound_policy,
        organization_id,
        partner_app_id,
        caller_number,
        session_factory=session_factory,
    )
