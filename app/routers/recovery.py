from fastapi import APIRouter, Request

from app.models.schemas import RecoveryPlanRequest, RecoveryPlanResponse
from app.services.recovery import plan_from_feed

router = APIRouter(prefix="/api/v1/recovery", tags=["recovery"])


@router.post("/plan", response_model=RecoveryPlanResponse)
async def recovery_plan(payload: RecoveryPlanRequest, request: Request) -> RecoveryPlanResponse:
    """Compute the live loss on a TASI position and rotate recovery capital into momentum names."""

    feed = getattr(request.app.state, "tickchart", None)
    plan = plan_from_feed(
        feed,
        symbol=payload.symbol,
        quantity=payload.quantity,
        avg_price=payload.avg_price,
    )
    return RecoveryPlanResponse.model_validate(plan)
