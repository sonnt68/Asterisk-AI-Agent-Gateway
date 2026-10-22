"""Tenant-safe API-key rotation and deletion of revoked keys."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_key_secrets import (
    ApiKeySecretConfigurationError,
    ApiKeySecretCorruptError,
    decrypt_api_key_secret,
    encrypt_api_key_secret,
)
from app.audit_log import audit
from app.auth import Principal, require_role
from app.database import get_session
from app.models import ApiKey, PartnerApp
from app.security import hash_api_secret, issue_api_key, timestamp_expired
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
    app = session.scalar(
        select(PartnerApp)
        .where(
            PartnerApp.id == current.partner_app_id,
            PartnerApp.organization_id == principal.organization_id,
            PartnerApp.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if not app:
        raise HTTPException(status_code=404, detail="API key not found")
    current = session.scalar(
        select(ApiKey)
        .where(
            ApiKey.id == key_id,
            ApiKey.organization_id == principal.organization_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
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
    session.add(replacement)
    try:
        session.flush()
        replacement.encrypted_secret = encrypt_api_key_secret(
            key_id=replacement.id,
            organization_id=replacement.organization_id,
            partner_app_id=replacement.partner_app_id,
            plaintext=plaintext,
            settings=get_settings(),
        )
    except ApiKeySecretConfigurationError:
        session.rollback()
        raise HTTPException(
            status_code=503, detail="Secret recovery is unavailable"
        ) from None
    current.encrypted_secret = None
    current.revoked_at = datetime.now(UTC)
    audit(session, principal, "api_key.rotated", replacement.id)
    session.commit()
    return {
        "id": replacement.id,
        "prefix": replacement.prefix,
        "key": plaintext,
        "scopes": replacement.scopes.split(","),
        "replaces": current.id,
        "partner_app_id": replacement.partner_app_id,
    }


@router.post("/api-keys/{key_id}/reveal")
def reveal_key(
    key_id: str,
    response: Response,
    principal: Principal = Depends(require_role("owner", "admin", "developer")),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    current = session.scalar(
        select(ApiKey).where(
            ApiKey.id == key_id,
            ApiKey.organization_id == principal.organization_id,
        )
    )
    if not current:
        raise HTTPException(status_code=404, detail="API key not found")
    app = session.get(PartnerApp, current.partner_app_id)
    if not app or app.organization_id != principal.organization_id or app.deleted_at is not None:
        raise HTTPException(status_code=404, detail="API key not found")
    if not app.enabled or current.revoked_at is not None or timestamp_expired(current.expires_at):
        raise HTTPException(status_code=409, detail="API key cannot be revealed")
    if not current.encrypted_secret:
        raise HTTPException(status_code=409, detail="API key secret is unavailable")
    try:
        plaintext = decrypt_api_key_secret(
            ciphertext=current.encrypted_secret,
            key_id=current.id,
            organization_id=current.organization_id,
            partner_app_id=current.partner_app_id,
            prefix=current.prefix,
            secret_hash=current.secret_hash,
            settings=get_settings(),
        )
    except (ApiKeySecretConfigurationError, ApiKeySecretCorruptError):
        raise HTTPException(
            status_code=503, detail="Secret recovery is unavailable"
        ) from None
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    audit(session, principal, "api_key.copied", current.id)
    session.commit()
    return {"key": plaintext, "partner_app_id": app.id, "agent_slug": app.agent_slug}


@router.delete("/api-keys/{key_id}/purge", status_code=204)
def delete_revoked_key(
    key_id: str,
    principal: Principal = Depends(require_role("owner", "admin", "developer")),
    session: Session = Depends(get_session),
) -> Response:
    key = session.scalar(
        select(ApiKey).where(
            ApiKey.id == key_id,
            ApiKey.organization_id == principal.organization_id,
        )
    )
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    if key.revoked_at is None:
        raise HTTPException(status_code=409, detail="Only revoked API keys can be deleted")

    audit(session, principal, "api_key.deleted", key.id)
    session.delete(key)
    session.commit()
    return Response(status_code=204)
