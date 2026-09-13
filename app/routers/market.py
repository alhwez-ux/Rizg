from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from app.core.exceptions import SahmApiError
from app.models.schemas import (
    RankingMatrixResponse,
    SectorCompaniesResponse,
    SectorRotationResponse,
    MarketRecommendationsResponse,
)
from app.services.ranking_store import RankingStore
from app.services.recommendations_engine import live_market_recommendations
from app.services.sahm_data_provider import SahmDataProvider
from app.services.sahm_live_market import live_ranking_rows, live_sector_rows
from app.services.sector_rotation import (
    SectorRotationEngine,
    companies_for_sector,
    rows_from_screener,
)

router = APIRouter(prefix="/api/v1/market", tags=["market"])

_LIVE_MESSAGE = "تم استرجاع أحدث تصنيف مالي حي من Sahm API بنجاح"
_CACHED_MESSAGE = "آخر لقطة حقيقية محفوظة من Sahm — ليست أرقاماً مولَّدة"
_EMPTY_MESSAGE = "لا توجد بيانات تصنيف حية من Sahm حالياً"


@router.get("/ranking-matrix", response_model=RankingMatrixResponse)
async def get_market_ranking_matrix(request: Request) -> RankingMatrixResponse:
    return await _live_rankings_response(request)


@router.get("/live-rankings", response_model=RankingMatrixResponse)
async def get_live_rankings_from_db(request: Request) -> RankingMatrixResponse:
    """جلب مصفوفة التصنيف الحية من Sahm مع الاعتماد على آخر لقطة محفوظة عند الحاجة."""

    return await _live_rankings_response(request)


@router.get("/sector-rotation", response_model=SectorRotationResponse)
async def get_sector_rotation_analysis(request: Request) -> SectorRotationResponse:
    """جلب تحليل تدوير السيولة القطاعية من لوحات Sahm الحية."""

    rows: list[dict] = []
    provider = _sahm(request, required=False)
    if provider is not None and provider.enabled:
        try:
            rows = await live_sector_rows(provider)
        except SahmApiError:
            rows = []
    screener = getattr(request.app.state, "screener", None)
    if screener is not None:
        rows = _prefer_live(rows, rows_from_screener(screener))
    payload = SectorRotationEngine(rows).ranked_payload()
    payload["source"] = "Sahm API"
    return SectorRotationResponse.model_validate(payload)


@router.get("/sector-companies/{sector_name}", response_model=SectorCompaniesResponse)
async def get_companies_by_sector(sector_name: str, request: Request) -> SectorCompaniesResponse:
    """إرجاع قائمة الشركات والأسهم التابعة لقطاع معين في تاسي."""

    live_rows: list[dict] = []
    provider = _sahm(request, required=False)
    if provider is not None and provider.enabled:
        try:
            live_rows = await live_sector_rows(provider)
        except SahmApiError:
            live_rows = []
    screener = getattr(request.app.state, "screener", None)
    payload = companies_for_sector(sector_name, screener, live_rows=live_rows)
    return SectorCompaniesResponse.model_validate(payload)


@router.get("/recommendations", response_model=MarketRecommendationsResponse)
async def get_market_recommendations(request: Request) -> MarketRecommendationsResponse:
    """فرص الارتداد الإيجابي واستمرار الزخم من أسعار الإغلاق والسيولة الحية."""

    rows: list[dict] = []
    provider = _sahm(request, required=False)
    if provider is not None and provider.enabled:
        try:
            rows = await live_market_recommendations(provider)
        except SahmApiError:
            rows = []
    return MarketRecommendationsResponse(
        success=True,
        count=len(rows),
        source="Sahm API",
        data=rows,
    )


@router.post("/ranking-matrix/sync", response_model=RankingMatrixResponse)
async def sync_market_ranking_matrix(request: Request) -> RankingMatrixResponse:
    return await _live_rankings_response(request, persist=True)


async def _live_rankings_response(request: Request, *, persist: bool = True) -> RankingMatrixResponse:
    provider = _sahm(request, required=False)
    store = _ranking_store(request)
    rows: list[dict] = []
    if provider is not None and provider.enabled:
        try:
            rows = await live_ranking_rows(provider, stored=store.snapshot())
        except SahmApiError:
            rows = []
    synced_at = datetime.now(timezone.utc).isoformat()
    if rows:
        if persist:
            store.replace(rows, synced_at, source="Sahm API")
        return RankingMatrixResponse(
            success=True,
            message=_LIVE_MESSAGE,
            source="Sahm API",
            total_companies=len(rows),
            synced_at=synced_at,
            data=rows,
        )
    cached = store.snapshot()
    if cached:
        return RankingMatrixResponse(
            success=True,
            message=_CACHED_MESSAGE,
            source="cached",
            total_companies=len(cached),
            synced_at=store.synced_at(),
            data=cached,
        )
    return RankingMatrixResponse(
        success=True,
        message=_EMPTY_MESSAGE,
        source="Sahm API",
        total_companies=0,
        synced_at=synced_at,
        data=[],
    )


def _prefer_live(primary: list[dict], extra: list[dict]) -> list[dict]:
    merged = {str(row.get("symbol") or "").upper(): row for row in extra if row.get("symbol")}
    for row in primary:
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        current = merged.get(symbol, {})
        merged[symbol] = {**current, **{key: value for key, value in row.items() if value not in (None, "")}}
    return list(merged.values())


def _sahm(request: Request, *, required: bool = True) -> SahmDataProvider | None:
    provider = getattr(request.app.state, "sahm", None)
    if isinstance(provider, SahmDataProvider):
        return provider
    if required:
        raise HTTPException(status_code=503, detail="مزود بيانات Sahm غير مهيأ")
    return None


def _ranking_store(request: Request) -> RankingStore:
    store = getattr(request.app.state, "ranking_store", None)
    if isinstance(store, RankingStore):
        return store
    store = RankingStore()
    request.app.state.ranking_store = store
    return store
