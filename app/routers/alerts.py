from fastapi import APIRouter, Query, Request

from app.models.alert import AlertListResponse, LiquidityAlert

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


@router.get("", response_model=AlertListResponse)
async def list_alerts(
    request: Request,
    symbol: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> AlertListResponse:
    alerts: list[LiquidityAlert] = request.app.state.alerts.recent(symbol)
    sliced = alerts[:limit]
    return AlertListResponse(count=len(sliced), alerts=sliced)


@router.get("/{symbol}", response_model=AlertListResponse)
async def list_symbol_alerts(
    symbol: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
) -> AlertListResponse:
    alerts: list[LiquidityAlert] = request.app.state.alerts.recent(symbol)
    sliced = alerts[:limit]
    return AlertListResponse(count=len(sliced), alerts=sliced)
