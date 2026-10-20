"""Customer API-key and internal session views over persisted call records."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import Principal, require_principal
from app.call_history_queries import (
    HistoryAccess,
    get_history,
    list_history,
    list_history_agents,
    list_signals,
)
from app.call_history_schemas import (
    CallHistoryAgents,
    CallHistoryItem,
    CallHistoryPage,
    CallSignalPage,
    HistoryFilters,
)
from app.database import get_session
from app.partner_auth import PartnerIdentity, require_call_reader

router = APIRouter(tags=["call history"])


def partner_access(identity: PartnerIdentity = Depends(require_call_reader)) -> HistoryAccess:
    return HistoryAccess(identity.organization_id, identity.partner_app_id)


def browser_access(principal: Principal = Depends(require_principal)) -> HistoryAccess:
    return HistoryAccess(
        principal.organization_id, include_imported=principal.role in {"owner", "admin"}
    )


@router.get("/partner/calls", response_model=CallHistoryPage)
def partner_calls(
    filters: HistoryFilters = Depends(),
    access: HistoryAccess = Depends(partner_access),
    session: Session = Depends(get_session),
) -> CallHistoryPage:
    return list_history(session, access, filters)


@router.get("/partner/calls/{call_id}", response_model=CallHistoryItem)
def partner_call(
    call_id: str,
    access: HistoryAccess = Depends(partner_access),
    session: Session = Depends(get_session),
) -> CallHistoryItem:
    return CallHistoryItem.model_validate(get_history(session, access, call_id))


@router.get("/partner/calls/{call_id}/signals", response_model=CallSignalPage)
def partner_signals(
    call_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=200),
    access: HistoryAccess = Depends(partner_access),
    session: Session = Depends(get_session),
) -> CallSignalPage:
    return list_signals(session, access, call_id, limit, cursor)


@router.get("/call-history", response_model=CallHistoryPage)
def browser_calls(
    filters: HistoryFilters = Depends(),
    access: HistoryAccess = Depends(browser_access),
    session: Session = Depends(get_session),
) -> CallHistoryPage:
    return list_history(session, access, filters)


@router.get("/call-history/agents", response_model=CallHistoryAgents)
def browser_history_agents(
    access: HistoryAccess = Depends(browser_access),
    session: Session = Depends(get_session),
) -> CallHistoryAgents:
    return CallHistoryAgents(items=list_history_agents(session, access))


@router.get("/call-history/{call_id}", response_model=CallHistoryItem)
def browser_call(
    call_id: str,
    access: HistoryAccess = Depends(browser_access),
    session: Session = Depends(get_session),
) -> CallHistoryItem:
    return CallHistoryItem.model_validate(get_history(session, access, call_id))


@router.get("/call-history/{call_id}/signals", response_model=CallSignalPage)
def browser_signals(
    call_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=200),
    access: HistoryAccess = Depends(browser_access),
    session: Session = Depends(get_session),
) -> CallSignalPage:
    return list_signals(session, access, call_id, limit, cursor)
