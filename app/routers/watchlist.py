from fastapi import APIRouter, Request, status

from app.models.screener import WatchlistItemIn, WatchlistResponse

router = APIRouter(prefix="/api/v1/watchlist", tags=["watchlist"])


@router.get("", response_model=WatchlistResponse)
async def get_watchlist(request: Request) -> WatchlistResponse:
    symbols = request.app.state.watchlist.symbols()
    return WatchlistResponse(symbols=symbols, count=len(symbols))


@router.post("", response_model=WatchlistResponse, status_code=status.HTTP_200_OK)
async def add_watchlist_symbol(payload: WatchlistItemIn, request: Request) -> WatchlistResponse:
    symbols = request.app.state.watchlist.add(payload.symbol)
    return WatchlistResponse(symbols=symbols, count=len(symbols))


@router.delete("/{symbol}", response_model=WatchlistResponse)
async def remove_watchlist_symbol(symbol: str, request: Request) -> WatchlistResponse:
    symbols = request.app.state.watchlist.remove(symbol)
    return WatchlistResponse(symbols=symbols, count=len(symbols))
