from fastapi import APIRouter, Request

from app.models.schemas import (
    ComplianceChangeOut,
    ComplianceSyncRequest,
    ComplianceSyncResponse,
)
from app.services.financial_sync import FinancialSyncService

router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"])


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
