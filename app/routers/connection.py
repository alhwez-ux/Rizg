"""Lightweight connection status. Does not start market feeds by itself."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.services.connection_guard import OWNER_ID

router = APIRouter(prefix="/api/v1/connection", tags=["connection"])


def _guard(request: Request):
    guard = getattr(request.app.state, "connection_guard", None)
    if guard is None:
        from app.services.connection_guard import ConnectionGuard

        guard = ConnectionGuard(plan_active=False, plan_reason="guard_unavailable")
        request.app.state.connection_guard = guard
    return guard


@router.get("")
async def connection_status(request: Request) -> dict:
    return _guard(request).snapshot()


@router.post("/heartbeat")
async def connection_heartbeat(request: Request) -> dict:
    guard = _guard(request)
    guard.beat(OWNER_ID)
    return guard.snapshot()


@router.post("/release")
async def connection_release(request: Request) -> dict:
    guard = _guard(request)
    guard.release(OWNER_ID)
    return guard.snapshot()
