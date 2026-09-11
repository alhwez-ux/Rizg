from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from app.core.exceptions import SymbolNotFoundError
from app.models.quote import Quote
from app.models.schemas import LiquiditySnapshot, LiquidityStats, QuoteOut


class LiquidityService:
    """Compute top-of-book and rolling-window liquidity metrics."""

    def snapshot(self, quote: Quote) -> LiquiditySnapshot:
        mid = quote.mid_price
        spread = quote.ask - quote.bid
        relative_spread = spread / mid if mid else 0.0
        effective_spread = None
        if quote.last_price is not None:
            effective_spread = 2 * abs(quote.last_price - mid)

        return LiquiditySnapshot(
            symbol=quote.symbol,
            bid=quote.bid,
            ask=quote.ask,
            bid_size=quote.bid_size,
            ask_size=quote.ask_size,
            last_price=quote.last_price,
            volume=quote.volume,
            mid_price=mid,
            spread=spread,
            spread_bps=relative_spread * 10_000,
            relative_spread=relative_spread,
            quoted_depth=quote.bid_size + quote.ask_size,
            effective_spread=effective_spread,
            timestamp=quote.timestamp,
        )

    def history_stats(self, symbol: str, quotes: list[Quote]) -> LiquidityStats:
        if not quotes:
            raise SymbolNotFoundError(symbol)

        frame = pd.DataFrame([quote.model_dump() for quote in quotes])
        frame["mid_price"] = (frame["bid"] + frame["ask"]) / 2
        frame["spread"] = frame["ask"] - frame["bid"]
        frame["spread_bps"] = (frame["spread"] / frame["mid_price"]) * 10_000
        frame["quoted_depth"] = frame["bid_size"] + frame["ask_size"]

        vwap = None
        last_prices = frame["last_price"].dropna()
        volumes = frame.loc[last_prices.index, "volume"] if not last_prices.empty else None
        if volumes is not None and volumes.sum() > 0:
            vwap = float((last_prices * volumes).sum() / volumes.sum())

        return LiquidityStats(
            symbol=symbol,
            observations=int(len(frame)),
            avg_spread=float(frame["spread"].mean()),
            avg_spread_bps=float(frame["spread_bps"].mean()),
            min_spread=float(frame["spread"].min()),
            max_spread=float(frame["spread"].max()),
            avg_quoted_depth=float(frame["quoted_depth"].mean()),
            avg_volume=float(frame["volume"].mean()),
            vwap=vwap,
            window_start=_as_utc(frame["timestamp"].min()),
            window_end=_as_utc(frame["timestamp"].max()),
        )

    def to_quote_out(self, quote: Quote) -> QuoteOut:
        return QuoteOut(
            symbol=quote.symbol,
            bid=quote.bid,
            ask=quote.ask,
            bid_size=quote.bid_size,
            ask_size=quote.ask_size,
            last_price=quote.last_price,
            volume=quote.volume,
            timestamp=quote.timestamp,
            mid_price=quote.mid_price,
        )


def _as_utc(value: datetime | pd.Timestamp) -> datetime:
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
