from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from datetime import timezone
from typing import AsyncIterator

from app.core.config import Settings, get_settings
from app.models.quote import Quote


class MarketDataStore:
    """In-memory quote store used as the application database layer.

    The interface is intentionally small so it can be replaced with Redis
    or a time-series database without changing routers or services.
    """

    def __init__(self, history_limit: int) -> None:
        self._history_limit = history_limit
        self._history: dict[str, deque[Quote]] = defaultdict(
            lambda: deque(maxlen=self._history_limit)
        )
        self._latest: dict[str, Quote] = {}
        self._lock = asyncio.Lock()

    async def upsert_quote(self, quote: Quote) -> Quote:
        if quote.timestamp.tzinfo is None:
            quote = quote.model_copy(
                update={"timestamp": quote.timestamp.replace(tzinfo=timezone.utc)}
            )
        async with self._lock:
            self._latest[quote.symbol] = quote
            self._history[quote.symbol].append(quote)
        return quote

    async def get_latest(self, symbol: str) -> Quote | None:
        async with self._lock:
            return self._latest.get(symbol)

    async def get_history(self, symbol: str, limit: int | None = None) -> list[Quote]:
        async with self._lock:
            quotes = list(self._history.get(symbol, ()))
        if limit is not None:
            return quotes[-limit:]
        return quotes

    async def list_symbols(self) -> list[str]:
        async with self._lock:
            return sorted(self._latest.keys())

    async def ping(self) -> bool:
        return True


_store: MarketDataStore | None = None


def init_store(settings: Settings | None = None) -> MarketDataStore:
    global _store
    settings = settings or get_settings()
    _store = MarketDataStore(history_limit=settings.quote_history_limit)
    return _store


def get_store() -> MarketDataStore:
    if _store is None:
        raise RuntimeError("Market data store has not been initialized")
    return _store


async def close_store() -> None:
    global _store
    _store = None


async def get_store_dependency() -> AsyncIterator[MarketDataStore]:
    yield get_store()
