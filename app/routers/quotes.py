from fastapi import APIRouter, Query, Request, status

from app.models.schemas import QuoteHistoryResponse, QuoteIn, QuoteOut, SymbolListResponse

router = APIRouter(prefix="/api/v1/quotes", tags=["quotes"])


@router.post("", response_model=QuoteOut, status_code=status.HTTP_201_CREATED)
async def ingest_quote(payload: QuoteIn, request: Request) -> QuoteOut:
    quote = await request.app.state.market_data.ingest_quote(payload)
    return request.app.state.liquidity.to_quote_out(quote)


@router.get("/symbols", response_model=SymbolListResponse)
async def list_symbols(request: Request) -> SymbolListResponse:
    symbols = await request.app.state.market_data.list_symbols()
    return SymbolListResponse(symbols=symbols, count=len(symbols))


@router.get("/{symbol}", response_model=QuoteOut)
async def get_latest_quote(symbol: str, request: Request) -> QuoteOut:
    analysis = getattr(request.app.state, "sahm_analysis", None)
    if analysis is not None:
        await analysis.ensure_seeded(symbol)
    quote = await request.app.state.market_data.get_latest(symbol)
    return request.app.state.liquidity.to_quote_out(quote)


@router.get("/{symbol}/history", response_model=QuoteHistoryResponse)
async def get_quote_history(
    symbol: str,
    request: Request,
    limit: int = Query(default=100, ge=1, le=5000),
) -> QuoteHistoryResponse:
    quotes = await request.app.state.market_data.get_history(symbol, limit=limit)
    return QuoteHistoryResponse(
        symbol=symbol.upper(),
        count=len(quotes),
        quotes=[request.app.state.liquidity.to_quote_out(quote) for quote in quotes],
    )
