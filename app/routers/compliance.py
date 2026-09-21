from fastapi import APIRouter, Query, Request

from app.models.schemas import (
    ComplianceChangeOut,
    ComplianceSyncRequest,
    ComplianceSyncResponse,
    ShariahScreenResponse,
)
from app.services.financial_sync import FinancialSyncService
from app.services.shariah import screen_universe

router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"])


@router.get("/screen", response_model=ShariahScreenResponse)
async def get_shariah_screen(
    filter: str = Query(default="all", description="all or pure"),
) -> ShariahScreenResponse:
    """TASI Shariah screen: نقي / مختلط. محرم is never returned."""

    mode = (filter or "all").strip().lower()
    pure_only = mode in {"pure", "نقي"}
    rows = screen_universe(pure_only=pure_only)
    return ShariahScreenResponse(
        success=True,
        filter="pure" if pure_only else "all",
        count=len(rows),
        data=rows,
    )


@router.post("/sync", response_model=ComplianceSyncResponse)
async def sync_scheduled_classifications(
    payload: ComplianceSyncRequest,
    request: Request,
) -> ComplianceSyncResponse:
    service: FinancialSyncService = request.app.state.financial_sync
    changes = service.sync_scheduled(item.model_dump() for item in payload.items)
    return ComplianceSyncResponse(
        updated=len(changes),
        changes=[ComplianceChangeOut.model_validate(row) for row in changes],
    )
