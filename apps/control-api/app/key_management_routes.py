"""Tenant-safe API-key rotation with one-time secret reveal."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit_log import audit
from app.auth import Principal, require_role
from app.database import get_session
from app.models import ApiKey
from app.security import hash_api_secret, issue_api_key
from app.settings import get_settings

router = APIRouter(tags=["management"])


@router.post("/api-keys/{key_id}/rotate", status_code=201)
def rotate_key(
    key_id: str,
    principal: Principal = Depends(require_role("owner", "admin", "developer")),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    current = session.scalar(
        select(ApiKey).where(
            ApiKey.id == key_id,
            ApiKey.organization_id == principal.organization_id,
        )
    )
    if not current:
        raise HTTPException(status_code=404, detail="API key not found")
    if current.revoked_at:
        raise HTTPException(status_code=409, detail="API key is already revoked")
    plaintext, prefix, secret = issue_api_key()
    replacement = ApiKey(
        organization_id=current.organization_id,
        partner_app_id=current.partner_app_id,
        name=f"{current.name} (rotated)",
        prefix=prefix,
        secret_hash=hash_api_secret(secret, get_settings()),
        scopes=current.scopes,
        expires_at=current.expires_at,
    )
    current.revoked_at = datetime.now(UTC)
    session.add(replacement)
    session.flush()
    audit(session, principal, "api_key.rotated", replacement.id)
    session.commit()
    return {
        "id": replacement.id,
        "prefix": replacement.prefix,
        "key": plaintext,
        "scopes": replacement.scopes.split(","),
        "replaces": current.id,
    }
