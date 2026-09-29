from fastapi import APIRouter, Request

from app.models.schemas import SmartMoneyScanResponse
from app.services.smart_money import scan_smart_money
from app.services.tickchart_integration import warm_public_quotes

router = APIRouter(prefix="/api/v1/smart-money", tags=["smart-money"])


@router.get("/scan", response_model=SmartMoneyScanResponse)
async def scan_smart_money_market(request: Request) -> SmartMoneyScanResponse:
    """Scan TASI tapes for institutional block prints and smart-money accumulation."""

    feed = getattr(request.app.state, "tickchart", None)
    await warm_public_quotes(feed)
    payload = scan_smart_money(feed)
    return SmartMoneyScanResponse.model_validate(payload)
