from fastapi import APIRouter, Request, status

from app.models.screener import UnderWatchResponse, WatchlistItemIn, WatchlistResponse

router = APIRouter(prefix="/api/v1/watchlist", tags=["watchlist"])


@router.get("", response_model=WatchlistResponse)
async def get_watchlist(request: Request) -> WatchlistResponse:
    symbols = request.app.state.watchlist.symbols()
    return WatchlistResponse(symbols=symbols, count=len(symbols))


@router.get("/under-watch", response_model=UnderWatchResponse)
async def get_under_watch(request: Request) -> UnderWatchResponse:
    store = getattr(request.app.state, "under_watch", None)
    feed = getattr(request.app.state, "tickchart", None)
    if store is None and feed is not None:
        store = getattr(feed, "under_watch", None)
    getter = getattr(store, "snapshot", None)
    rows = list(getter() or []) if callable(getter) else []
    latest = max((str(row.get("updated_at") or "") for row in rows), default="") or None
    return UnderWatchResponse(success=True, count=len(rows), data=rows, updated_at=latest)


@router.post("", response_model=WatchlistResponse, status_code=status.HTTP_200_OK)
async def add_watchlist_symbol(payload: WatchlistItemIn, request: Request) -> WatchlistResponse:
    symbols = request.app.state.watchlist.add(payload.symbol)
    return WatchlistResponse(symbols=symbols, count=len(symbols))


@router.delete("/{symbol}", response_model=WatchlistResponse)
async def remove_watchlist_symbol(symbol: str, request: Request) -> WatchlistResponse:
    symbols = request.app.state.watchlist.remove(symbol)
    return WatchlistResponse(symbols=symbols, count=len(symbols))
