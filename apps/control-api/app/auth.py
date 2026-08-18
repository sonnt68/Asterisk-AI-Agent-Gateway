"""Browser session authentication and role enforcement."""

from dataclasses import dataclass

from fastapi import Cookie, Depends, HTTPException, status
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import Membership
from app.settings import get_settings


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: str
    organization_id: str
    role: str


def session_serializer() -> URLSafeSerializer:
    return URLSafeSerializer(get_settings().session_secret, salt="gateway-browser-v1")


def create_session(principal: Principal) -> str:
    return session_serializer().dumps(
        {"user_id": principal.user_id, "organization_id": principal.organization_id, "role": principal.role}
    )


def require_principal(
    gateway_session: str | None = Cookie(default=None),
    session: Session = Depends(get_session),
) -> Principal:
    if not gateway_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        data = session_serializer().loads(gateway_session)
    except BadSignature as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session") from error
    membership = session.scalar(
        select(Membership).where(
            Membership.user_id == data["user_id"], Membership.organization_id == data["organization_id"]
        )
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session membership is no longer valid")
    return Principal(data["user_id"], data["organization_id"], membership.role)


def require_role(*roles: str):
    def dependency(principal: Principal = Depends(require_principal)) -> Principal:
        if principal.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient organization role")
        return principal

    return dependency
