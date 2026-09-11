from app.core.database import MarketDataStore
from app.core.exceptions import SymbolNotFoundError
from app.models.quote import Quote
from app.models.schemas import QuoteIn
from app.services.broadcaster import ConnectionManager
from app.services.liquidity import LiquidityService


class MarketDataService:
    def __init__(
        self,
        store: MarketDataStore,
        liquidity: LiquidityService,
        broadcaster: ConnectionManager,
    ) -> None:
        self._store = store
        self._liquidity = liquidity
        self._broadcaster = broadcaster

    async def ingest_quote(self, payload: QuoteIn) -> Quote:
        quote = await self._store.upsert_quote(payload.to_quote())
        snapshot = self._liquidity.snapshot(quote)
        await self._broadcaster.publish(
            quote.symbol,
            {"type": "quote", "data": snapshot.model_dump(mode="json")},
        )
        return quote

    async def get_latest(self, symbol: str) -> Quote:
        quote = await self._store.get_latest(symbol.upper())
        if quote is None:
            raise SymbolNotFoundError(symbol)
        return quote

    async def get_history(self, symbol: str, limit: int | None = None) -> list[Quote]:
        quotes = await self._store.get_history(symbol.upper(), limit=limit)
        if not quotes:
            raise SymbolNotFoundError(symbol)
        return quotes

    async def list_symbols(self) -> list[str]:
        return await self._store.list_symbols()
