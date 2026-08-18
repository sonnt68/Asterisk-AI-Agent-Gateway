"""Unauthenticated system endpoints; partner endpoints are added separately."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    service: Literal["control-api"]
    status: Literal["ok"]
    version: str


@router.get("/system/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report that this ASGI service can accept control-plane requests."""
    return HealthResponse(service="control-api", status="ok", version="1.0.0")
