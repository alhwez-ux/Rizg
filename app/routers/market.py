from datetime import datetime, timezone
import asyncio

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request

from app.models.schemas import (
    RankingMatrixResponse,
    SectorCompaniesResponse,
    SectorRotationResponse,
    MarketRecommendationsResponse,
    DailySyncStatusResponse,
    SchedulerRunResponse,
    SchedulerStatusResponse,
    DividendsResponse,
)
from app.services.ranking_store import RankingStore
from app.services.sector_rotation import SAMPLE_SECTOR_TAPE, SectorRotationEngine, companies_for_sector
from app.services.signals import keep_long_recommendations
from app.services.tasi_clock import now_riyadh, phase_label, session_phase

router = APIRouter(prefix="/api/v1/market", tags=["market"])

_LIVE_MESSAGE = "تم استرجاع أحدث تصنيف حي من تكرتشارت بنجاح"
_CACHED_MESSAGE = "آخر لقطة مالية محفوظة مع أسعار تكرتشارت اللحظية"
_EMPTY_MESSAGE = "لا توجد بيانات تكرتشارت حية حالياً"


@router.get("/ranking-matrix", response_model=RankingMatrixResponse)
async def get_market_ranking_matrix(request: Request) -> RankingMatrixResponse:
    return await _live_rankings_response(request)


@router.get("/dividends", response_model=DividendsResponse)
async def get_active_dividends(
    request: Request,
    pure_only: bool = Query(default=False, description="الأسهم النقية فقط"),
) -> DividendsResponse:
    """Upcoming TASI cash dividends. Eligibility date < today is dropped."""

    del request
    from app.services.dividends import active_dividends

    today = now_riyadh().date()
    rows = active_dividends(today=today, pure_only=pure_only)
    return DividendsResponse(
        success=True,
        count=len(rows),
        as_of=today.isoformat(),
        timezone="Asia/Riyadh",
        hint="تُحذف الشركة تلقائياً بعد مرور تاريخ الأحقية (توقيت الرياض، الأحد–الخميس)",
        data=rows,
    )


@router.get("/live-rankings", response_model=RankingMatrixResponse)
async def get_live_rankings_from_db(request: Request) -> RankingMatrixResponse:
    return await _live_rankings_response(request)


@router.get("/sector-rotation", response_model=SectorRotationResponse)
async def get_sector_rotation_analysis(request: Request) -> SectorRotationResponse:
    rows = _tickchart_rows(request)
    source = "TickChart"
    quote_mode = _tape_quote_mode(rows)
    if not rows:
        rows = [dict(item, quote_mode="last_close") for item in SAMPLE_SECTOR_TAPE]
        source = "last_close"
        quote_mode = "last_close"
    payload = SectorRotationEngine(rows).ranked_payload()
    payload["source"] = source
    payload["quote_mode"] = quote_mode
    return SectorRotationResponse.model_validate(payload)


@router.get("/sector-companies/{sector_name}", response_model=SectorCompaniesResponse)
async def get_companies_by_sector(sector_name: str, request: Request) -> SectorCompaniesResponse:
    rows = _tickchart_rows(request)
    payload = companies_for_sector(sector_name, live_rows=rows, tape_only=True)
    return SectorCompaniesResponse.model_validate(payload)


@router.get("/recommendations", response_model=MarketRecommendationsResponse)
async def get_market_recommendations(
    request: Request,
    background_tasks: BackgroundTasks,
    limit: int = Query(12, ge=1, le=50),
    offset: int = Query(0, ge=0),
) -> MarketRecommendationsResponse:
    phase = session_phase(now_riyadh())
    live = phase == "open"
    feed = getattr(request.app.state, "tickchart", None)
    cached = _cached_recommendation_rows(feed, live=live)
    if cached is not None:
        rows = cached
        source = "cached"
        if feed is not None and getattr(feed, "recommendations_stale", None):
            if feed.recommendations_stale(live=live):
                background_tasks.add_task(_refresh_recommendations, feed, live)
    else:
        rows = await asyncio.to_thread(_recommendation_rows, request, live=live)
        source = "TickChart"
    rows = keep_long_recommendations(rows)
    page = rows[offset : offset + limit]
    return MarketRecommendationsResponse(
        success=True,
        count=len(page),
        total=len(rows),
        source=source,
        scan_mode="live" if live else "end_of_day",
        session_phase=phase,
        session_label=phase_label(phase),
        scan_build="smc-long-1",
        data=page,
    )


@router.post("/ranking-matrix/sync", response_model=RankingMatrixResponse)
async def sync_market_ranking_matrix(request: Request) -> RankingMatrixResponse:
    return await _live_rankings_response(request)


@router.get("/scheduler", response_model=SchedulerStatusResponse)
async def get_tasi_scheduler_status(request: Request) -> SchedulerStatusResponse:
    scheduler = _tasi_scheduler(request)
    return SchedulerStatusResponse.model_validate(scheduler.status())


@router.post("/scheduler/run/{job}", response_model=SchedulerRunResponse)
async def run_tasi_scheduler_job(job: str, request: Request) -> SchedulerRunResponse:
    key = job.strip().lower()
    if key not in {"open", "scan", "close"}:
        raise HTTPException(status_code=422, detail="المهمة يجب أن تكون open أو scan أو close")
    scheduler = _tasi_scheduler(request)
    result = await scheduler.run(key, force=key == "scan")
    return SchedulerRunResponse(success=True, job=key, result=result)


@router.get("/daily-sync", response_model=DailySyncStatusResponse)
async def get_tadawul_daily_sync_status(request: Request) -> DailySyncStatusResponse:
    current = now_riyadh()
    phase = session_phase(current)
    return DailySyncStatusResponse(
        success=True,
        enabled=False,
        running=False,
        timezone="Asia/Riyadh",
        clock=current.isoformat(),
        hour=16,
        minute=0,
        phase=phase,
        phase_label=phase_label(phase),
        as_of=None,
        symbols=0,
        jobs=[],
        last={"disabled": "tickchart_only"},
    )


@router.post("/daily-sync/run", response_model=SchedulerRunResponse)
async def run_tadawul_daily_sync(_request: Request) -> SchedulerRunResponse:
    return SchedulerRunResponse(
        success=True,
        job="daily_close",
        result={"skipped": True, "reason": "tickchart_only"},
    )


async def _live_rankings_response(request: Request) -> RankingMatrixResponse:
    store = _ranking_store(request)
    tape = {str(row.get("symbol")): row for row in _tickchart_rows(request)}
    cached = store.snapshot() or []
    rows: list[dict] = []
    for row in cached:
        symbol = str(row.get("symbol") or "").upper()
        live = tape.get(symbol) or {}
        merged = dict(row)
        if live.get("last_price") is not None:
            merged["last_price"] = live["last_price"]
        if live.get("volume"):
            merged["volume"] = live["volume"]
        rows.append(merged)
    if not rows and tape:
        rows = [
            {
                "symbol": item["symbol"],
                "name": item.get("name"),
                "last_price": item.get("last_price"),
                "volume": item.get("volume"),
                "matrix_score": 0,
                "category": "تكرتشارت لحظي",
            }
            for item in tape.values()
        ]
    synced_at = datetime.now(timezone.utc).isoformat()
    if rows:
        return RankingMatrixResponse(
            success=True,
            message=_LIVE_MESSAGE if tape else _CACHED_MESSAGE,
            source="TickChart",
            total_companies=len(rows),
            synced_at=store.synced_at() or synced_at,
            data=rows,
        )
    return RankingMatrixResponse(
        success=True,
        message=_EMPTY_MESSAGE,
        source="TickChart",
        total_companies=0,
        synced_at=synced_at,
        data=[],
    )


def _tickchart_rows(request: Request) -> list[dict]:
    feed = getattr(request.app.state, "tickchart", None)
    if feed is None:
        return []
    return feed.market_rows()


def _tape_quote_mode(rows: list[dict]) -> str:
    if any(str(row.get("quote_mode") or "") == "live" or row.get("live") for row in rows):
        return "live"
    if rows:
        return "last_close"
    return "waiting"


def _cached_recommendation_rows(feed, *, live: bool) -> list[dict] | None:
    if feed is None:
        return None
    lookup = getattr(feed, "cached_recommendations", None)
    if not callable(lookup):
        return None
    rows = lookup(live=live)
    return list(rows) if rows is not None else None


def _refresh_recommendations(feed, live: bool) -> None:
    if live:
        live_scan = getattr(feed, "live_recommendations", None)
        if callable(live_scan):
            live_scan()
        return
    closer = getattr(feed, "close_recommendations", None)
    if callable(closer):
        closer()


def _recommendation_rows(request: Request, *, live: bool) -> list[dict]:
    feed = getattr(request.app.state, "tickchart", None)
    if feed is None:
        return []
    if live:
        live_scan = getattr(feed, "live_recommendations", None)
        if callable(live_scan):
            return live_scan()
        opportunities = getattr(feed, "opportunities", None)
        if callable(opportunities):
            return opportunities()
    closer = getattr(feed, "close_recommendations", None)
    if callable(closer):
        return closer()
    opportunities = getattr(feed, "opportunities", None)
    if callable(opportunities):
        return opportunities()
    return []


def _ranking_store(request: Request) -> RankingStore:
    store = getattr(request.app.state, "ranking_store", None)
    if isinstance(store, RankingStore):
        return store
    store = RankingStore()
    request.app.state.ranking_store = store
    return store


def _tasi_scheduler(request: Request):
    scheduler = getattr(request.app.state, "tasi_scheduler", None)
    if scheduler is None:
        raise HTTPException(status_code=503, detail="مجدول تاسي غير مهيأ")
    return scheduler
