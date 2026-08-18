"""Persist tenant-scoped control-plane audit events."""

from sqlalchemy.orm import Session

from app.auth import Principal
from app.models import AuditEvent


def audit(
    session: Session, principal: Principal | None, action: str, target_id: str | None
) -> None:
    if principal:
        session.add(
            AuditEvent(
                organization_id=principal.organization_id,
                actor_id=principal.user_id,
                action=action,
                target_id=target_id,
            )
        )
