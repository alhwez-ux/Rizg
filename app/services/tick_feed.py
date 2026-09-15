from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone
from decimal import Decimal

from app.core.config import Settings
from app.models.trade import LiquidityStreamMessage
from app.services.alerts import AlertService
from app.services.broadcaster import ConnectionManager
from app.services.liquidity_engine import LiquidityEngine

logger = logging.getLogger(__name__)

_TICK_SIZE = Decimal("0.01")
_BASE_PRICES: dict[str, Decimal] = {
    "AAPL": Decimal("189.15"),
    "MSFT": Decimal("420.50"),
    "TSLA": Decimal("248.30"),
    "NVDA": Decimal("118.40"),
    "4030": Decimal("24.85"),
}


class MockTickFeed:
    """Async mock tape used when no live market-data session is connected.

    Each iteration emits a random-walk trade, runs it through `LiquidityEngine`,
    and broadcasts net flow / buy-sell volume to symbol subscribers.
    """

    def __init__(
        self,
        engine: LiquidityEngine,
        manager: ConnectionManager,
        settings: Settings,
        *,
        alerts: AlertService | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self._engine = engine
        self._manager = manager
        self._settings = settings
        self._alerts = alerts
        self._rng = rng or random.Random()
        self._last_price: dict[str, Decimal] = {}
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run(), name="mock-tick-feed")
        logger.info(
            "mock tick feed started interval=%.2fs symbols=%s",
            self._settings.mock_feed_interval_seconds,
            self._settings.mock_feed_symbols,
        )

    async def stop(self) -> None:
        self._running = False
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        logger.info("mock tick feed stopped")

    def next_tick(self, symbol: str) -> tuple[Decimal, Decimal]:
        ticker = symbol.upper()
        last = self._last_price.get(ticker) or _BASE_PRICES.get(ticker, Decimal("100.00"))
        step = self._rng.choice((-2, -1, -1, 0, 0, 0, 1, 1, 2))
        price = last + (_TICK_SIZE * step)
        if price <= Decimal("0"):
            price = _TICK_SIZE
        volume = Decimal(self._rng.randint(50, 1500))
        self._last_price[ticker] = price
        return price, volume

    async def emit_symbol(self, symbol: str) -> LiquidityStreamMessage | None:
        ticker = symbol.upper()
        try:
            price, volume = self.next_tick(ticker)
            result = self._engine.process_trade(
                ticker,
                price,
                volume,
                timestamp=datetime.now(timezone.utc),
            )
            message = self._engine.stream_message(result)
            await self._manager.broadcast(ticker, message.as_json())
            if self._alerts is not None:
                await self._alerts.handle_trade(result)
            return message
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("failed to emit mock tick for %s", ticker)
            return None

    def _active_symbols(self) -> list[str]:
        configured = {item.strip().upper() for item in self._settings.mock_feed_symbols if item.strip()}
        subscribed = self._manager.subscribed_symbols()
        return sorted(configured | subscribed)

    async def _run(self) -> None:
        interval = self._settings.mock_feed_interval_seconds
        try:
            while self._running:
                try:
                    for symbol in self._active_symbols():
                        if not self._running:
                            break
                        await self.emit_symbol(symbol)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("mock tick feed iteration failed")
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("mock tick feed cancelled")
            raise
