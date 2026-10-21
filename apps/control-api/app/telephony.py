"""Shared managed-DID identity and resolution helpers."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import PartnerApp, PhoneNumber


def managed_route_id(organization_id: str, number: str) -> str:
    """Return the stable bridge route ID for one exact tenant/DID pair."""
    return str(uuid5(NAMESPACE_URL, f"{organization_id}:{number}"))


@dataclass(frozen=True, slots=True)
class ManagedRoute:
    route_id: str
    organization_id: str
    partner_app_id: str
    agent_slug: str
    number: str


def resolve_managed_route(
    number: str, session_factory: Callable[[], Session] = SessionLocal
) -> ManagedRoute | None:
    """Resolve only an enabled, applied local mapping and enabled app."""
    with session_factory() as session:
        row = session.execute(
            select(PhoneNumber, PartnerApp)
            .join(PartnerApp, PartnerApp.id == PhoneNumber.partner_app_id)
            .where(
                PhoneNumber.number == number,
                PhoneNumber.enabled.is_(True),
                PhoneNumber.pbx_applied.is_(True),
                PartnerApp.organization_id == PhoneNumber.organization_id,
                PartnerApp.enabled.is_(True),
            )
        ).first()
        if not row:
            return None
        phone, app = row
        return ManagedRoute(
            route_id=phone.id,
            organization_id=phone.organization_id,
            partner_app_id=app.id,
            agent_slug=app.agent_slug,
            number=phone.number,
        )


async def resolve_managed_route_async(
    number: str, session_factory: Callable[[], Session] = SessionLocal
) -> ManagedRoute | None:
    """Run synchronous SQLAlchemy work away from the ARI event loop."""
    return await asyncio.to_thread(resolve_managed_route, number, session_factory)
