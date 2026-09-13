from typing import Any

from fastapi import APIRouter, File, Header, Request, UploadFile

from app.core.exceptions import InvalidSymbolError, TickChartNotConfiguredError, TickChartUnauthorizedError
from app.models.schemas import (
    TickChartFollowBody,
    TickChartIngestResponse,
    TickChartStatusResponse,
    TickChartUploadText,
)
from app.models.screener import normalize_tasi_symbol
from app.services.shariah import company_name_for
from app.services.tickchart_autosync import parse_export_text

router = APIRouter(prefix="/api/v1/tickchart", tags=["tickchart"])


@router.get("/status", response_model=TickChartStatusResponse)
async def tickchart_status(request: Request) -> TickChartStatusResponse:
    feed = getattr(request.app.state, "tickchart", None)
    if feed is None:
        return TickChartStatusResponse(enabled=False, connected=False, symbols=[], mode="cloud")
    payload = feed.status()
    payload.setdefault("mode", "cloud")
    payload.pop("autosync_dirs", None)
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


@router.post("/refresh")
async def refresh_tickchart_live(request: Request) -> dict[str, Any]:
    """Subscribe cloud ticks for watched symbols and return the latest rows."""

    feed = _require_feed(request)
    watched = 0
    for symbol in list(getattr(feed, "status", lambda: {})().get("symbols") or []):
        await feed.watch(str(symbol))
        watched += 1
        if hasattr(feed, "hydrate_symbol"):
            await feed.hydrate_symbol(str(symbol))
    rows = feed.market_rows()
    return {
        "success": True,
        "source": "TickChart",
        "watched": watched,
        "count": len(rows),
        "data": rows,
    }


@router.post("/follow")
async def follow_symbol(payload: TickChartFollowBody, request: Request) -> dict[str, Any]:
    try:
        ticker = normalize_tasi_symbol(payload.symbol)
    except ValueError:
        raise InvalidSymbolError(payload.symbol)
    feed = _require_feed(request)
    watchlist = getattr(request.app.state, "watchlist", None)
    if watchlist is not None:
        watchlist.add(ticker)
    await feed.watch(ticker)
    if hasattr(feed, "hydrate_symbol"):
        await feed.hydrate_symbol(ticker)
    report = feed.radar_report(ticker)
    return {
        "success": True,
        "source": "TickChart",
        "symbol": ticker,
        "name": company_name_for(ticker) or ticker,
        "analysis": report,
    }


@router.post("/upload", response_model=TickChartIngestResponse)
async def upload_tickchart_file(
    request: Request,
    file: UploadFile | None = File(default=None),
    x_tickchart_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> TickChartIngestResponse:
    """Ingest a TickChart CSV/JSON snapshot from the browser on any device."""

    feed = _require_feed(request)
    _check_ingest_token(request, x_tickchart_token, authorization)
    filename = file.filename if file is not None else "upload.csv"
    raw = ""
    if file is not None:
        blob = await file.read()
        raw = blob.decode("utf-8-sig", errors="replace")
    else:
        body = await request.json()
        parsed = TickChartUploadText.model_validate(body)
        filename = parsed.filename
        raw = parsed.content
        if parsed.symbol:
            filename = f"{parsed.symbol}_{filename}"
    payloads = parse_export_text(raw, filename or "upload.csv")
    ingested = 0
    for item in payloads:
        ingested += await feed.ingest_message(item)
    return TickChartIngestResponse(success=True, ingested=ingested)


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
