from typing import Any

from fastapi import APIRouter, Header, Request

from app.core.exceptions import TickChartNotConfiguredError, TickChartUnauthorizedError
from app.models.schemas import TickChartIngestResponse, TickChartStatusResponse

router = APIRouter(prefix="/api/v1/tickchart", tags=["tickchart"])


@router.get("/status", response_model=TickChartStatusResponse)
async def tickchart_status(request: Request) -> TickChartStatusResponse:
    feed = getattr(request.app.state, "tickchart", None)
    if feed is None:
        return TickChartStatusResponse(enabled=False, connected=False, symbols=[])
    payload = feed.status()
    return TickChartStatusResponse.model_validate(payload)


@router.get("/market")
async def tickchart_market(request: Request) -> dict[str, Any]:
    feed = getattr(request.app.state, "tickchart", None)
    rows = feed.market_rows() if feed is not None else []
    return {"success": True, "source": "TickChart", "count": len(rows), "data": rows}


@router.get("/opportunities")
async def tickchart_opportunities(request: Request) -> dict[str, Any]:
    feed = getattr(request.app.state, "tickchart", None)
    rows = feed.opportunities() if feed is not None else []
    return {"success": True, "source": "TickChart", "count": len(rows), "data": rows}


@router.get("/alerts")
async def tickchart_alerts(request: Request) -> dict[str, Any]:
    feed = getattr(request.app.state, "tickchart", None)
    rows = feed.alerts() if feed is not None else []
    return {"success": True, "source": "TickChart", "count": len(rows), "data": rows}


@router.post("/ingest", response_model=TickChartIngestResponse)
async def ingest_tickchart_payload(
    request: Request,
    payload: dict[str, Any],
    x_tickchart_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> TickChartIngestResponse:
    """Push ticks or depth from an external TickChart bridge."""

    feed = _require_feed(request)
    _check_ingest_token(request, x_tickchart_token, authorization)
    ingested = await feed.ingest_message(payload)
    return TickChartIngestResponse(success=True, ingested=ingested)


def _require_feed(request: Request):
    feed = getattr(request.app.state, "tickchart", None)
    if feed is None or not getattr(feed, "enabled", False):
        raise TickChartNotConfiguredError()
    return feed


def _check_ingest_token(
    request: Request,
    header_token: str | None,
    authorization: str | None,
) -> None:
    settings = getattr(request.app.state, "settings", None)
    expected = str(getattr(settings, "tickchart_ingest_token", "") or "").strip()
    if not expected:
        return
    bearer = ""
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()
    provided = (header_token or bearer).strip()
    if provided != expected:
        raise TickChartUnauthorizedError()
