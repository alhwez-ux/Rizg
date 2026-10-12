from fastapi import APIRouter, Query, Request

from app.models.schemas import AnalystConsensusResponse
from app.services.analyst_consensus import collect_last_prices, consensus_payload, default_analyst_store
from app.services.tasi_clock import now_riyadh

router = APIRouter(prefix="/api/v1/analysts", tags=["analysts"])


@router.get("/consensus", response_model=AnalystConsensusResponse)
async def get_analyst_consensus(
    request: Request,
    pure_only: bool = Query(default=False, description="الأسهم النقية فقط"),
    window_days: int | None = Query(default=None, ge=1, le=30, description="نافذة النشر بالأيام"),
) -> AnalystConsensusResponse:
    """House picks whose entry is the live print at first sight, then locked.

    `window_days` switches to dated buy reports inside that rolling window.
    """

    feed = getattr(request.app.state, "tickchart", None)
    store = getattr(request.app.state, "analyst_entry_store", None) or default_analyst_store()
    payload = consensus_payload(
        today=now_riyadh().date(),
        pure_only=pure_only,
        last_prices=collect_last_prices(feed),
        store=store,
        window_days=window_days,
    )
    return AnalystConsensusResponse.model_validate(payload)
