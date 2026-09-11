from __future__ import annotations

import math
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any

from app.core.exceptions import InvalidTradeError, SymbolNotFoundError
from app.models.trade import SessionFlow, TickType, TradeResult, TradeSide

Number = Decimal | float | int | str

PRICE_QUANTUM = Decimal("0.00000001")
VOLUME_QUANTUM = Decimal("0.00000001")
MONEY_QUANTUM = Decimal("0.00000001")
ZERO = Decimal("0")


def _to_decimal(value: Number, *, field_name: str) -> Decimal:
    if isinstance(value, bool):
        raise InvalidTradeError(
            f"{field_name} must be a numeric value",
            details={field_name: value},
        )
    if isinstance(value, Decimal):
        converted = value
    elif isinstance(value, int):
        converted = Decimal(value)
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise InvalidTradeError(
                f"{field_name} must be a finite number",
                details={field_name: value},
            )
        converted = Decimal(str(value))
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise InvalidTradeError(f"{field_name} must not be empty")
        try:
            converted = Decimal(stripped)
        except InvalidOperation as exc:
            raise InvalidTradeError(
                f"{field_name} is not a valid number",
                details={field_name: value},
            ) from exc
    else:
        raise InvalidTradeError(
            f"{field_name} has an unsupported type",
            details={field_name: type(value).__name__},
        )

    if not converted.is_finite():
        raise InvalidTradeError(
            f"{field_name} must be a finite number",
            details={field_name: str(converted)},
        )
    return converted


def _quantize(value: Decimal, quantum: Decimal) -> Decimal:
    return value.quantize(quantum, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True)
class MarketLevels:
    """Session VWAP, ATR, and top-of-book pressure used for entry/exit prices."""

    symbol: str
    vwap: Decimal | None = None
    atr: Decimal | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    bid_size: Decimal | None = None
    ask_size: Decimal | None = None
    book_pressure: Decimal | None = None
    last_price: Decimal | None = None
    session_high: Decimal | None = None
    session_low: Decimal | None = None


@dataclass
class _TickerState:
    symbol: str
    inflow: Decimal = ZERO
    outflow: Decimal = ZERO
    buy_volume: Decimal = ZERO
    sell_volume: Decimal = ZERO
    last_price: Decimal | None = None
    last_different_price: Decimal | None = None
    last_side: TradeSide | None = None
    trade_count: int = 0
    classified_count: int = 0
    vwap_pv: Decimal = ZERO
    vwap_vol: Decimal = ZERO
    session_high: Decimal | None = None
    session_low: Decimal | None = None
    prev_close: Decimal | None = None
    true_ranges: deque[Decimal] = field(default_factory=lambda: deque(maxlen=14))
    bid: Decimal | None = None
    ask: Decimal | None = None
    bid_size: Decimal | None = None
    ask_size: Decimal | None = None

    @property
    def net_flow(self) -> Decimal:
        return _quantize(self.inflow - self.outflow, MONEY_QUANTUM)

    @property
    def vwap(self) -> Decimal | None:
        if self.vwap_vol <= ZERO:
            return None
        return _quantize(self.vwap_pv / self.vwap_vol, PRICE_QUANTUM)

    @property
    def book_pressure(self) -> Decimal | None:
        if self.bid_size is None or self.ask_size is None:
            return None
        total = self.bid_size + self.ask_size
        if total <= ZERO:
            return None
        return _quantize(self.bid_size / total, Decimal("0.0001"))

    @property
    def atr(self) -> Decimal | None:
        if self.true_ranges:
            total = sum(self.true_ranges, ZERO)
            return _quantize(total / len(self.true_ranges), PRICE_QUANTUM)
        if (
            self.session_high is not None
            and self.session_low is not None
            and self.session_high > self.session_low
        ):
            return _quantize(self.session_high - self.session_low, PRICE_QUANTUM)
        if self.last_price is not None and self.last_price > ZERO:
            return _quantize(self.last_price * Decimal("0.008"), PRICE_QUANTUM)
        return None

    def snapshot(self) -> SessionFlow:
        return SessionFlow(
            symbol=self.symbol,
            inflow=self.inflow,
            outflow=self.outflow,
            net_flow=self.net_flow,
            buy_volume=self.buy_volume,
            sell_volume=self.sell_volume,
            last_price=self.last_price,
            last_different_price=self.last_different_price,
            last_side=self.last_side,
            trade_count=self.trade_count,
            classified_count=self.classified_count,
        )


class LiquidityEngine:
    """Session-level trade classifier using the tick rule and net money flow.

    Tick rule:
    - Price up versus the previous trade → BUY (aggressive inflow)
    - Price down versus the previous trade → SELL (aggressive outflow)
    - Unchanged price → compare against the last *different* price (zero-tick)
    - No usable reference price → leave the trade unclassified
    """

    def __init__(
        self,
        *,
        price_quantum: Decimal = PRICE_QUANTUM,
        volume_quantum: Decimal = VOLUME_QUANTUM,
        money_quantum: Decimal = MONEY_QUANTUM,
    ) -> None:
        self._price_quantum = price_quantum
        self._volume_quantum = volume_quantum
        self._money_quantum = money_quantum
        self._sessions: dict[str, _TickerState] = {}
        self._lock = threading.RLock()

    @staticmethod
    def classify_tick(
        price: Decimal,
        previous_price: Decimal | None,
        last_different_price: Decimal | None = None,
    ) -> tuple[TradeSide | None, TickType]:
        """Return (side, tick type) for a single observation of the tick rule."""

        if previous_price is None:
            return None, TickType.UNCLASSIFIED

        if price > previous_price:
            return TradeSide.BUY, TickType.UPTICK
        if price < previous_price:
            return TradeSide.SELL, TickType.DOWNTICK

        if last_different_price is None:
            return None, TickType.UNCLASSIFIED
        if price > last_different_price:
            return TradeSide.BUY, TickType.ZERO_TICK
        if price < last_different_price:
            return TradeSide.SELL, TickType.ZERO_TICK
        return None, TickType.UNCLASSIFIED

    def process_trade(
        self,
        symbol: str,
        price: Number,
        volume: Number,
        *,
        timestamp: datetime | None = None,
    ) -> TradeResult:
        ticker = self._normalize_symbol(symbol)
        quantized_price = _quantize(
            _to_decimal(price, field_name="price"), self._price_quantum
        )
        quantized_volume = _quantize(
            _to_decimal(volume, field_name="volume"), self._volume_quantum
        )

        if quantized_price <= ZERO:
            raise InvalidTradeError(
                "price must be greater than zero",
                details={"price": str(quantized_price)},
            )
        if quantized_volume < ZERO:
            raise InvalidTradeError(
                "volume cannot be negative",
                details={"volume": str(quantized_volume)},
            )

        with self._lock:
            state = self._sessions.setdefault(ticker, _TickerState(symbol=ticker))
            side, tick = self.classify_tick(
                quantized_price,
                state.last_price,
                state.last_different_price,
            )
            money_flow = self._apply_money_flow(state, side, quantized_price, quantized_volume)
            self._update_vwap(state, quantized_price, quantized_volume)
            self._update_session_range(state, quantized_price)
            self._update_price_memory(state, quantized_price)
            state.trade_count += 1
            if side is not None:
                state.last_side = side
                state.classified_count += 1
            session = state.snapshot()

        return TradeResult(
            symbol=ticker,
            side=side,
            tick=tick,
            price=quantized_price,
            volume=quantized_volume,
            money_flow=money_flow,
            timestamp=timestamp,
            session=session,
        )

    def process_trades(self, trades: list[tuple[str, Number, Number]]) -> list[TradeResult]:
        return [
            self.process_trade(symbol, price, volume) for symbol, price, volume in trades
        ]

    def get_session(self, symbol: str) -> SessionFlow:
        ticker = self._normalize_symbol(symbol)
        with self._lock:
            state = self._sessions.get(ticker)
            if state is None:
                raise SymbolNotFoundError(ticker)
            return state.snapshot()

    def session_snapshot(self, symbol: str) -> SessionFlow:
        """Return session totals, or zeros if the ticker has no trades yet."""

        ticker = self._normalize_symbol(symbol)
        with self._lock:
            state = self._sessions.get(ticker)
            if state is None:
                return _TickerState(symbol=ticker).snapshot()
            return state.snapshot()

    def snapshot_all(self) -> dict[str, SessionFlow]:
        with self._lock:
            return {symbol: state.snapshot() for symbol, state in self._sessions.items()}

    def active_symbols(self) -> list[str]:
        with self._lock:
            return sorted(self._sessions)

    def reset(self, symbol: str | None = None) -> None:
        with self._lock:
            if symbol is None:
                self._sessions.clear()
                return
            self._sessions.pop(self._normalize_symbol(symbol), None)

    def levels_snapshot(self, symbol: str) -> MarketLevels:
        ticker = self._normalize_symbol(symbol)
        with self._lock:
            state = self._sessions.get(ticker) or _TickerState(symbol=ticker)
            return self._levels_from(state)

    def observe_market(self, symbol: str, payload: dict[str, Any] | None = None) -> MarketLevels:
        """Update VWAP/ATR/book from a quote payload (bid/ask, high/low, last)."""

        ticker = self._normalize_symbol(symbol)
        data = _flatten_market_payload(payload)
        with self._lock:
            state = self._sessions.setdefault(ticker, _TickerState(symbol=ticker))
            bid = _optional_decimal(data.get("bid") or data.get("best_bid"))
            ask = _optional_decimal(data.get("ask") or data.get("best_ask"))
            bid_size = _optional_decimal(
                data.get("bid_size") or data.get("bid_volume") or data.get("bid_qty")
            )
            ask_size = _optional_decimal(
                data.get("ask_size") or data.get("ask_volume") or data.get("ask_qty")
            )
            if bid is not None and bid > ZERO:
                state.bid = _quantize(bid, self._price_quantum)
            if ask is not None and ask > ZERO:
                state.ask = _quantize(ask, self._price_quantum)
            if bid_size is not None and bid_size >= ZERO:
                state.bid_size = _quantize(bid_size, self._volume_quantum)
            if ask_size is not None and ask_size >= ZERO:
                state.ask_size = _quantize(ask_size, self._volume_quantum)

            last = _optional_decimal(data.get("price") or data.get("last_price") or data.get("close"))
            high = _optional_decimal(data.get("high") or data.get("day_high"))
            low = _optional_decimal(data.get("low") or data.get("day_low"))
            prev = _optional_decimal(
                data.get("previous_close") or data.get("prev_close") or data.get("yesterday_close")
            )
            if prev is not None and prev > ZERO:
                state.prev_close = _quantize(prev, self._price_quantum)
            if last is not None and last > ZERO:
                quantized = _quantize(last, self._price_quantum)
                self._update_session_range(state, quantized)
                if state.last_price is None:
                    state.last_price = quantized
            if high is not None and high > ZERO:
                high_q = _quantize(high, self._price_quantum)
                state.session_high = high_q if state.session_high is None else max(state.session_high, high_q)
            if low is not None and low > ZERO:
                low_q = _quantize(low, self._price_quantum)
                state.session_low = low_q if state.session_low is None else min(state.session_low, low_q)
            self._record_true_range(state)
            volume = _optional_decimal(data.get("volume") or data.get("quantity"))
            if last is not None and volume is not None and volume > ZERO and state.vwap_vol <= ZERO:
                quantized = _quantize(last, self._price_quantum)
                qty = _quantize(volume, self._volume_quantum)
                self._update_vwap(state, quantized, qty)
            return self._levels_from(state)

    def _levels_from(self, state: _TickerState) -> MarketLevels:
        return MarketLevels(
            symbol=state.symbol,
            vwap=state.vwap,
            atr=state.atr,
            bid=state.bid,
            ask=state.ask,
            bid_size=state.bid_size,
            ask_size=state.ask_size,
            book_pressure=state.book_pressure,
            last_price=state.last_price,
            session_high=state.session_high,
            session_low=state.session_low,
        )

    def _update_vwap(self, state: _TickerState, price: Decimal, volume: Decimal) -> None:
        if volume <= ZERO:
            return
        state.vwap_pv = _quantize(state.vwap_pv + (price * volume), self._money_quantum)
        state.vwap_vol = _quantize(state.vwap_vol + volume, self._volume_quantum)

    def _update_session_range(self, state: _TickerState, price: Decimal) -> None:
        if state.session_high is None or price > state.session_high:
            state.session_high = price
        if state.session_low is None or price < state.session_low:
            state.session_low = price
        self._record_true_range(state)

    def _record_true_range(self, state: _TickerState) -> None:
        if state.session_high is None or state.session_low is None:
            return
        span = state.session_high - state.session_low
        close = state.last_price or state.session_high
        prev = state.prev_close or close
        true_range = max(span, abs(state.session_high - prev), abs(state.session_low - prev))
        if true_range <= ZERO:
            return
        quantized = _quantize(true_range, self._price_quantum)
        if state.true_ranges and state.true_ranges[-1] == quantized:
            return
        state.true_ranges.append(quantized)

    def _apply_money_flow(
        self,
        state: _TickerState,
        side: TradeSide | None,
        price: Decimal,
        volume: Decimal,
    ) -> Decimal:
        if side is None or volume == ZERO:
            return ZERO

        notional = _quantize(volume * price, self._money_quantum)
        if side is TradeSide.BUY:
            state.inflow = _quantize(state.inflow + notional, self._money_quantum)
            state.buy_volume = _quantize(state.buy_volume + volume, self._volume_quantum)
            return notional
        state.outflow = _quantize(state.outflow + notional, self._money_quantum)
        state.sell_volume = _quantize(state.sell_volume + volume, self._volume_quantum)
        return -notional

    def _update_price_memory(self, state: _TickerState, price: Decimal) -> None:
        if state.last_price is not None and price != state.last_price:
            state.last_different_price = state.last_price
        state.last_price = price

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        if not isinstance(symbol, str) or not symbol.strip():
            raise InvalidTradeError("symbol is required")
        return symbol.strip().upper()


def _flatten_market_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    merged = {**data, **{key: value for key, value in payload.items() if key != "data"}}
    book = merged.get("order_book") if isinstance(merged.get("order_book"), dict) else {}
    if book:
        merged.setdefault("bid", book.get("bid") or book.get("best_bid"))
        merged.setdefault("ask", book.get("ask") or book.get("best_ask"))
        merged.setdefault("bid_size", book.get("bid_size") or book.get("bid_volume"))
        merged.setdefault("ask_size", book.get("ask_size") or book.get("ask_volume"))
    return merged


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None
