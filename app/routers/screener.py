import asyncio

from fastapi import APIRouter, Request

from app.models.screener import ScreenerSnapshot

router = APIRouter(prefix="/api/v1/screener", tags=["screener"])


@router.get("", response_model=ScreenerSnapshot)
async def get_screener(request: Request) -> ScreenerSnapshot:
    feed = getattr(request.app.state, "tickchart", None)
    sync = getattr(feed, "sync_screener", None)
    if callable(sync):
        await asyncio.to_thread(sync)
    return request.app.state.screener.snapshot()
