from fastapi import APIRouter, Request

from app.models.schemas import RankingMatrixResponse, SectorCompaniesResponse, SectorRotationResponse
from app.services.company_ranker import SAMPLE_COMPANIES, CompanyRankingEngine
from app.services.financial_sync_service import FinancialSyncService
from app.services.ranking_store import RankingStore
from app.services.sector_rotation import (
    SAMPLE_SECTOR_TAPE,
    SectorRotationEngine,
    companies_for_sector,
    rows_from_screener,
)

router = APIRouter(prefix="/api/v1/market", tags=["market"])

_LIVE_MESSAGE = "تم استرجاع أحدث تصنيف مالي حي بنجاح"


@router.get("/ranking-matrix", response_model=RankingMatrixResponse)
async def get_market_ranking_matrix(request: Request) -> RankingMatrixResponse:
    return _live_rankings_response(request, fallback_sample=True)


@router.get("/live-rankings", response_model=RankingMatrixResponse)
async def get_live_rankings_from_db(request: Request) -> RankingMatrixResponse:
    """جلب مصفوفة التصنيف الجاهزة مباشرة من قاعدة البيانات المحدثة."""

    return _live_rankings_response(request, fallback_sample=False)


@router.get("/sector-rotation", response_model=SectorRotationResponse)
async def get_sector_rotation_analysis(request: Request) -> SectorRotationResponse:
    """جلب تحليل تدوير السيولة القطاعية في السوق السعودي."""

    screener = getattr(request.app.state, "screener", None)
    rows = rows_from_screener(screener) if screener is not None else []
    engine = SectorRotationEngine(rows or SAMPLE_SECTOR_TAPE)
    payload = engine.ranked_payload()
    return SectorRotationResponse.model_validate(payload)


@router.get("/sector-companies/{sector_name}", response_model=SectorCompaniesResponse)
async def get_companies_by_sector(sector_name: str, request: Request) -> SectorCompaniesResponse:
    """إرجاع قائمة الشركات والأسهم التابعة لقطاع معين في تاسي."""

    screener = getattr(request.app.state, "screener", None)
    payload = companies_for_sector(sector_name, screener)
    return SectorCompaniesResponse.model_validate(payload)


@router.post("/ranking-matrix/sync", response_model=RankingMatrixResponse)
async def sync_market_ranking_matrix(request: Request) -> RankingMatrixResponse:
    service = _sync_service(request)
    result = service.sync_market_financials()
    rows = result.get("data") or service.store.snapshot()
    return RankingMatrixResponse(
        success=True,
        message=_LIVE_MESSAGE,
        total_companies=len(rows),
        synced_at=result.get("synced_at"),
        data=rows,
    )


def _live_rankings_response(request: Request, *, fallback_sample: bool) -> RankingMatrixResponse:
    store = _ranking_store(request)
    rows = store.snapshot()
    synced_at = store.synced_at()
    if not rows:
        service = getattr(request.app.state, "market_financial_sync", None) or getattr(
            request.app.state, "sync_service", None
        )
        if isinstance(service, FinancialSyncService):
            result = service.sync_market_financials()
            rows = result.get("data") or service.store.snapshot()
            synced_at = result.get("synced_at") or service.store.synced_at()
        elif fallback_sample:
            rows = CompanyRankingEngine(SAMPLE_COMPANIES).get_ranked_payload()
    return RankingMatrixResponse(
        success=True,
        message=_LIVE_MESSAGE,
        total_companies=len(rows),
        synced_at=synced_at,
        data=rows,
    )


def _ranking_store(request: Request) -> RankingStore:
    store = getattr(request.app.state, "ranking_store", None)
    if isinstance(store, RankingStore):
        return store
    service = _sync_service(request)
    request.app.state.ranking_store = service.store
    return service.store


def _sync_service(request: Request) -> FinancialSyncService:
    service = getattr(request.app.state, "market_financial_sync", None) or getattr(
        request.app.state, "sync_service", None
    )
    if isinstance(service, FinancialSyncService):
        return service
    store = RankingStore()
    service = FinancialSyncService(store=store, enable_scheduler=False)
    request.app.state.market_financial_sync = service
    request.app.state.sync_service = service
    request.app.state.ranking_store = service.store
    return service
