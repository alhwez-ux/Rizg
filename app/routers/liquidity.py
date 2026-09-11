from fastapi import APIRouter, Query, Request

from app.models.schemas import LiquiditySnapshot, LiquidityStats

router = APIRouter(prefix="/api/v1/liquidity", tags=["liquidity"])


@router.get("/{symbol}", response_model=LiquiditySnapshot)
async def get_liquidity_snapshot(symbol: str, request: Request) -> LiquiditySnapshot:
    quote = await request.app.state.market_data.get_latest(symbol)
    return request.app.state.liquidity.snapshot(quote)


@router.get("/{symbol}/stats", response_model=LiquidityStats)
async def get_liquidity_stats(
    symbol: str,
    request: Request,
    limit: int = Query(default=200, ge=1, le=5000),
) -> LiquidityStats:
    quotes = await request.app.state.market_data.get_history(symbol, limit=limit)
    return request.app.state.liquidity.history_stats(symbol.upper(), quotes)
