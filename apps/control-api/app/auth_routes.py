"""Browser login, logout, and current-session endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit_log import audit
from app.auth import Principal, create_session, require_principal
from app.database import get_session
from app.models import Membership, User
from app.security import verify_password
from app.settings import get_settings

router = APIRouter(tags=["authentication"])


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=12)


@router.post("/auth/login")
def login(
    payload: LoginRequest, response: Response, session: Session = Depends(get_session)
) -> dict[str, str]:
    user = session.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    membership = session.scalar(select(Membership).where(Membership.user_id == user.id))
    if not membership:
        raise HTTPException(status_code=403, detail="No organization membership")
    principal = Principal(user.id, membership.organization_id, membership.role)
    settings = get_settings()
    response.set_cookie(
        "gateway_session",
        create_session(principal),
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
        max_age=settings.browser_session_max_age,
    )
    audit(session, principal, "auth.login", user.id)
    session.commit()
    return {"organization_id": principal.organization_id, "role": principal.role}


@router.post("/auth/logout", status_code=204)
def logout(response: Response) -> Response:
    response.delete_cookie("gateway_session")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/auth/session")
def browser_session(principal: Principal = Depends(require_principal)) -> Principal:
    return principal
