from fastapi import APIRouter, Request

from app.models.schemas import CorrectionRadarResponse
from app.services.correction_radar import scan_correction_radar
from app.services.tickchart_integration import warm_public_quotes

router = APIRouter(prefix="/api/v1/correction-radar", tags=["correction-radar"])


@router.get("/scan", response_model=CorrectionRadarResponse)
async def scan_correction_market(request: Request) -> CorrectionRadarResponse:
    """List names where measured volume, flow, blocks, or price location match a correction alert."""

    feed = getattr(request.app.state, "tickchart", None)
    await warm_public_quotes(feed)
    payload = scan_correction_radar(feed)
    return CorrectionRadarResponse.model_validate(payload)
