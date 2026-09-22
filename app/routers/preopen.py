from fastapi import APIRouter, Request

from app.models.schemas import PreOpenScanResponse
from app.services.preopen import scan_preopen

router = APIRouter(prefix="/api/v1/preopen", tags=["preopen"])


@router.get("/scan", response_model=PreOpenScanResponse)
async def scan_preopen_market(request: Request) -> PreOpenScanResponse:
    """Aggregate TASI pre-open order books into early accumulation / distribution signals."""

    feed = getattr(request.app.state, "tickchart", None)
    payload = scan_preopen(feed)
    return PreOpenScanResponse.model_validate(payload)
