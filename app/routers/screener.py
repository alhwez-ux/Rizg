from fastapi import APIRouter, Request

from app.models.screener import ScreenerSnapshot

router = APIRouter(prefix="/api/v1/screener", tags=["screener"])


@router.get("", response_model=ScreenerSnapshot)
async def get_screener(request: Request) -> ScreenerSnapshot:
    return request.app.state.screener.snapshot()
