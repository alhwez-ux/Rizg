import asyncio

from fastapi import APIRouter, Query, Request

from app.models.schemas import DailyOpportunitiesResponse
from app.services.daily_opportunities import scan_daily_opportunities
from app.services.tasi_clock import now_riyadh, session_phase
from app.services.tickchart_integration import warm_public_quotes

router = APIRouter(prefix="/api/v1/opportunities", tags=["opportunities"])


@router.get("/daily", response_model=DailyOpportunitiesResponse)
async def get_daily_opportunities(
    request: Request,
    pure_only: bool = Query(default=False, description="الأسهم النقية فقط"),
) -> DailyOpportunitiesResponse:
    """High-probability intraday longs with a locked entry and at least 1:2 reward."""

    feed = getattr(request.app.state, "tickchart", None)
    await warm_public_quotes(feed)
    recommendations = _cached_recommendations(feed)
    if not recommendations and feed is not None:
        builder = getattr(feed, "close_recommendations", None)
        if callable(builder):
            try:
                built = await asyncio.to_thread(builder)
            except Exception:
                built = None
            if isinstance(built, list) and built:
                recommendations = built
    payload = scan_daily_opportunities(
        feed,
        recommendations=recommendations,
        pure_only=pure_only,
    )
    return DailyOpportunitiesResponse.model_validate(payload)


def _cached_recommendations(feed: object) -> list[dict] | None:
    cached = getattr(feed, "cached_recommendations", None)
    if not callable(cached):
        return None
    live = session_phase(now_riyadh()) == "open"
    try:
        rows = cached(live=live)
    except TypeError:
        rows = cached()
    except Exception:
        return None
    if isinstance(rows, list) and rows:
        return rows
    if live:
        try:
            fallback = cached(live=False)
        except Exception:
            return None
        return fallback if isinstance(fallback, list) else None
    return None
