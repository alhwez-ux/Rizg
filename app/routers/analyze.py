from fastapi import APIRouter, Query, Request

from app.models.schemas import AnalyzeResponse

router = APIRouter(prefix="/api/v1/analyze", tags=["analyze"])


@router.get("/{symbol}", response_model=AnalyzeResponse)
async def analyze_symbol(
    symbol: str,
    request: Request,
    interval: str = Query(default="1d", description="Sahm candle interval: 1d, 1w, 1h, 60m, 30m"),
    limit: int = Query(default=100, ge=1, le=2000),
) -> AnalyzeResponse:
    """Analyze a TASI symbol by fetching candles from Sahm automatically."""

    return await request.app.state.sahm_analysis.analyze(
        symbol,
        interval=interval,
        limit=limit,
    )
