from fastapi import APIRouter, Query, Request

from app.core.exceptions import TickChartNoTickError, TickChartNotConfiguredError
from app.models.schemas import AnalyzeResponse, MarketLevelsOut
from app.models.trade import SessionFlow

router = APIRouter(prefix="/api/v1/analyze", tags=["analyze"])


@router.get("/{symbol}", response_model=AnalyzeResponse)
async def analyze_symbol(
    symbol: str,
    request: Request,
    interval: str = Query(default="1d", description="kept for compatibility; analysis uses TickChart ticks"),
    limit: int = Query(default=100, ge=1, le=2000),
) -> AnalyzeResponse:
    """Analyze a TASI symbol from TickChart ticks and Level-2 depth."""

    analysis = getattr(request.app.state, "sahm_analysis", None)
    if analysis is not None:
        return await analysis.analyze(symbol, interval=interval, limit=limit)

    feed = getattr(request.app.state, "tickchart", None)
    if feed is None or not getattr(feed, "enabled", False):
        raise TickChartNotConfiguredError()

    ticker = symbol.strip().upper()
    report = await feed.ensure_radar(ticker)
    if not report.get("last_price"):
        raise TickChartNoTickError(ticker)

    trades = int(report.get("trade_count") or 0)
    session = SessionFlow(
        symbol=ticker,
        inflow=report.get("inflow") or 0,
        outflow=report.get("outflow") or 0,
        net_flow=report.get("net_flow") or 0,
        last_price=report.get("last_price"),
        last_different_price=None,
        last_side=None,
        trade_count=trades,
        classified_count=trades,
        buy_volume=report.get("buy_volume") or 0,
        sell_volume=report.get("sell_volume") or 0,
    )
    return AnalyzeResponse(
        symbol=ticker,
        interval=interval,
        source="TickChart",
        bars=trades,
        session=session,
        levels=MarketLevelsOut(
            symbol=ticker,
            vwap=report.get("vwap"),
            atr=report.get("atr"),
            last_price=report.get("last_price"),
            book_pressure=report.get("book_pressure"),
        ),
        candles=[],
    )
