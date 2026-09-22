from __future__ import annotations

import math
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any

from app.core.exceptions import InvalidTradeError, SymbolNotFoundError
from app.models.trade import (
    LiquidityStreamMessage,
    SessionFlow,
    TickType,
    TradeResult,
    TradeSide,
    recommendation_label,
)

Number = Decimal | float | int | str

PRICE_QUANTUM = Decimal("0.00000001")
VOLUME_QUANTUM = Decimal("0.00000001")
MONEY_QUANTUM = Decimal("0.00000001")
ZERO = Decimal("0")


_LIVE_SIGNAL_ENGINE = None


def _live_signal_engine():
    from app.core.config import get_settings
    from app.services.signals import signal_engine_from_settings

    global _LIVE_SIGNAL_ENGINE
    if _LIVE_SIGNAL_ENGINE is None:
        _LIVE_SIGNAL_ENGINE = signal_engine_from_settings(get_settings())
    return _LIVE_SIGNAL_ENGINE


def reset_live_signal_engine(engine=None) -> None:
    """Replace or drop the process-wide live signal latch (tests)."""

    global _LIVE_SIGNAL_ENGINE
    _LIVE_SIGNAL_ENGINE = engine


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
            reference = state.last_price if state.last_price is not None else state.prev_close
            side, tick = self.classify_tick(
                quantized_price,
                reference,
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

    def ingest_candles(self, candles: Any) -> list[TradeResult]:
        """Ingest a Sahm OHLCV DataFrame (or list of row mappings) in timestamp order."""

        rows = _candle_rows(candles)
        results: list[TradeResult] = []
        for row in rows:
            symbol = str(row.get("symbol") or "").strip()
            close = _optional_decimal(row.get("close") or row.get("price"))
            volume = _optional_decimal(row.get("volume"))
            if not symbol or close is None or volume is None or close <= ZERO or volume < ZERO:
                continue
            payload = {
                "price": close,
                "close": close,
                "high": row.get("high"),
                "low": row.get("low"),
                "open": row.get("open"),
                "volume": volume,
                "previous_close": row.get("previous_close"),
            }
            timestamp = _optional_datetime(row.get("timestamp") or row.get("date"))
            try:
                self.observe_market(symbol, payload)
                results.append(
                    self.process_trade(symbol, close, volume, timestamp=timestamp)
                )
            except InvalidTradeError:
                continue
        return results

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

    def recommendation_flag(self, symbol: str) -> str | None:
        """دخول/خروج from the live SignalEngine, or None when the tape is quiet."""

        from app.services.signals import SignalInputs, apply_levels

        ticker = (symbol or "").strip().upper()
        if not ticker:
            return None
        session = self.session_snapshot(ticker)
        levels = self.levels_snapshot(ticker)
        inputs = apply_levels(
            SignalInputs(
                inflow=session.inflow,
                outflow=session.outflow,
                net_flow=session.net_flow,
                buy_volume=session.buy_volume,
                sell_volume=session.sell_volume,
                price=session.last_price or levels.last_price,
                tracked=True,
                symbol=ticker,
            ),
            levels,
        )
        decision = _live_signal_engine().evaluate(inputs, peer_nets=self._peer_nets())
        return recommendation_label(entry=decision.entry, exit_signal=decision.exit)

    def _peer_nets(self) -> list[Decimal]:
        with self._lock:
            return [state.net_flow for state in self._sessions.values()]

    def stream_message(self, result: TradeResult) -> LiquidityStreamMessage:
        return LiquidityStreamMessage.from_trade(
            result,
            recommendation=self.recommendation_flag(result.symbol),
        )

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


def _optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    to_pydatetime = getattr(value, "to_pydatetime", None)
    if callable(to_pydatetime):
        return _optional_datetime(to_pydatetime())
    return None


def _candle_rows(candles: Any) -> list[dict[str, Any]]:
    if candles is None:
        return []
    if getattr(candles, "empty", None) is True:
        return []
    frame = candles
    if hasattr(frame, "sort_values") and "timestamp" in getattr(frame, "columns", []):
        columns = ["timestamp"]
        if "symbol" in getattr(frame, "columns", []):
            columns = ["symbol", "timestamp"]
        frame = frame.sort_values(columns, kind="mergesort")
    if hasattr(frame, "to_dict"):
        records = frame.to_dict("records")
        return [row for row in records if isinstance(row, dict)]
    if isinstance(candles, list):
        rows = [row for row in candles if isinstance(row, dict)]
        return sorted(
            rows,
            key=lambda row: (str(row.get("symbol") or ""), str(row.get("timestamp") or "")),
        )
    return []


def _json_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _candle_frame(candles: Any, symbol: str) -> Any:
    if candles is None or getattr(candles, "empty", False):
        return None
    if not hasattr(candles, "iloc"):
        return None
    frame = candles
    if "symbol" in getattr(frame, "columns", []):
        filtered = frame[frame["symbol"].astype(str).str.upper() == symbol]
        if not filtered.empty:
            frame = filtered
    return frame


def _candle_context(candles: Any, symbol: str) -> tuple[Decimal, Decimal, Decimal | None]:
    frame = _candle_frame(candles, symbol)
    if frame is None or len(frame) == 0:
        return Decimal("0"), Decimal("0"), None
    last = frame.iloc[-1]
    volume = _optional_decimal(last.get("volume")) or Decimal("0")
    prev_volume = None
    change = Decimal("0")
    if len(frame) >= 2:
        prev = frame.iloc[-2]
        prev_volume = _optional_decimal(prev.get("volume"))
        first_close = _optional_decimal(frame.iloc[0].get("close"))
        last_close = _optional_decimal(last.get("close"))
        if first_close and last_close and first_close > 0:
            change = ((last_close - first_close) / first_close) * Decimal("100")
    return change, volume, prev_volume


def _volume_profile(candles: Any, symbol: str) -> tuple[Decimal | None, Decimal | None]:
    frame = _candle_frame(candles, symbol)
    if frame is None or len(frame) < 3:
        return None, None
    avg_volume = None
    swing_low = None
    if "volume" in frame.columns:
        prior = [_optional_decimal(value) for value in frame["volume"].iloc[:-1].tolist()]
        sample = [value for value in prior[-10:] if value is not None and value > 0]
        if sample:
            avg_volume = sum(sample, Decimal("0")) / Decimal(len(sample))
    if "low" in frame.columns:
        lows = [_optional_decimal(value) for value in frame["low"].iloc[-10:].tolist()]
        valid = [value for value in lows if value is not None and value > 0]
        if valid:
            swing_low = min(valid)
    return avg_volume, swing_low


def _detect_liquidity_trap(candles: Any, symbol: str) -> dict[str, str] | None:
    frame = _candle_frame(candles, symbol)
    if frame is None or len(frame) < 3:
        return None
    last = frame.iloc[-1]
    prev = frame.iloc[-2]
    high = _optional_decimal(last.get("high"))
    low = _optional_decimal(last.get("low"))
    close = _optional_decimal(last.get("close"))
    opened = _optional_decimal(last.get("open"))
    if high is None or low is None or close is None or opened is None:
        return None
    span = high - low
    if span <= 0:
        return None
    upper = high - max(opened, close)
    lower = min(opened, close) - low
    lookback = frame.iloc[0] if len(frame) < 4 else frame.iloc[-4]
    prior_close = _optional_decimal(lookback.get("close"))
    trend_up = prior_close is not None and close > prior_close
    if upper / span >= Decimal("0.55") and close < opened:
        return {
            "kind": "bull_trap",
            "label": "فخ صعود: رفض أعلى النطاق مع إغلاق ضعيف",
        }
    if lower / span >= Decimal("0.55") and close > opened:
        return {
            "kind": "bear_trap",
            "label": "فخ هبوط: كنس السيولة السفلية ثم إغلاق قوي",
        }
    volumes = frame["volume"] if "volume" in frame.columns else None
    if volumes is not None and len(frame) >= 5:
        window = [_optional_decimal(value) or Decimal("0") for value in volumes.iloc[-6:-1].tolist()]
        avg = (sum(window, Decimal("0")) / len(window)) if window else Decimal("0")
        last_volume = _optional_decimal(last.get("volume")) or Decimal("0")
        prev_close = _optional_decimal(prev.get("close"))
        if avg > 0 and last_volume >= avg * Decimal("1.8") and prev_close is not None:
            if close < prev_close and trend_up:
                return {
                    "kind": "bull_trap",
                    "label": "فخ صعود: تصريف بكمية مرتفعة بعد الصعود",
                }
            if close > prev_close and not trend_up:
                return {
                    "kind": "bear_trap",
                    "label": "فخ هبوط: امتصاص بكمية مرتفعة بعد الهبوط",
                }
    return None


class LiquidityRadarEngine(LiquidityEngine):
    """Candle-aware radar: ingest a Sahm DataFrame and emit the latest signal report."""

    def __init__(self, candles: Any = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._candles: Any = None
        self._primary_symbol: str | None = None
        if candles is not None:
            self.ingest(candles)

    def ingest(self, candles: Any) -> list[TradeResult]:
        self._candles = candles
        results = self.ingest_candles(candles)
        if results:
            self._primary_symbol = results[-1].symbol
        elif hasattr(candles, "empty") and not candles.empty and "symbol" in candles.columns:
            self._primary_symbol = str(candles["symbol"].iloc[-1])
        return results

    def get_latest_signal_report(self, symbol: str | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """Latest liquidity-flow / trap report after ingesting Sahm candles."""

        from app.services.signals import SignalInputs, apply_levels

        ticker = (symbol or self._primary_symbol or "").strip().upper()
        if not ticker:
            symbols = self.active_symbols()
            ticker = symbols[0] if symbols else ""
        if not ticker:
            return {
                "symbol": None,
                "signal": "neutral",
                "entry": False,
                "exit": False,
                "trap": None,
                "flow_verified": False,
                "reasons": ["لا توجد شموع محملة في محرك الرادار"],
            }

        session = self.session_snapshot(ticker)
        levels = self.levels_snapshot(ticker)
        change_percent, volume, prev_volume = _candle_context(self._candles, ticker)
        trap = _detect_liquidity_trap(self._candles, ticker)
        extra = extra or {}
        overlay_net = _optional_decimal(extra.get("net_flow")) if "net_flow" in extra else None
        overlay_inflow = _optional_decimal(extra.get("inflow"))
        overlay_outflow = _optional_decimal(extra.get("outflow"))
        session_net = overlay_net if overlay_net is not None else session.net_flow
        if session.net_flow and overlay_net is not None and abs(session.net_flow) > abs(overlay_net):
            session_net = session.net_flow
        session_inflow = session.inflow if session.inflow else overlay_inflow
        session_outflow = session.outflow if session.outflow else overlay_outflow
        extra_change = _optional_decimal(extra.get("change_percent"))
        extra_volume = _optional_decimal(extra.get("volume"))
        extra_value = _optional_decimal(extra.get("session_value"))
        extra_avg = _optional_decimal(extra.get("avg_volume"))
        extra_swing = _optional_decimal(extra.get("swing_low"))
        peer_nets = extra.get("peer_nets")
        if peer_nets is None:
            peer_nets = list(self._peer_nets())
            if overlay_net:
                peer_nets.append(overlay_net)
        avg_volume, swing_low = _volume_profile(self._candles, ticker)
        inputs = apply_levels(
            SignalInputs(
                volume=extra_volume if extra_volume is not None else volume,
                prev_volume=prev_volume,
                inflow=session_inflow,
                outflow=session_outflow,
                net_flow=session_net,
                buy_volume=session.buy_volume,
                sell_volume=session.sell_volume,
                change_percent=extra_change if extra_change is not None else change_percent,
                price=session.last_price or levels.last_price,
                session_value=extra_value,
                avg_volume=extra_avg if extra_avg is not None else avg_volume,
                swing_low=extra_swing if extra_swing is not None else swing_low or levels.session_low,
                tracked=True,
                symbol=ticker,
            ),
            levels,
        )
        decision = _live_signal_engine().evaluate(inputs, peer_nets=peer_nets)
        signal = "entry" if decision.entry else "exit" if decision.exit else "trap" if trap else "neutral"
        reasons = list(decision.reasons)
        if trap and trap["label"] not in reasons:
            reasons.insert(0, trap["label"])
        return {
            "symbol": ticker,
            "signal": signal,
            "entry": decision.entry,
            "exit": decision.exit,
            "trap": trap,
            "flow_verified": decision.flow_verified,
            "score": _json_number(decision.score),
            "net_flow": _json_number(session_net if session_net is not None else session.net_flow),
            "inflow": _json_number(session_inflow if session_inflow is not None else session.inflow),
            "outflow": _json_number(session_outflow if session_outflow is not None else session.outflow),
            "buy_volume": _json_number(session.buy_volume),
            "sell_volume": _json_number(session.sell_volume),
            "buy_ratio": _json_number(decision.buy_ratio),
            "sell_ratio": _json_number(decision.sell_ratio),
            "last_price": _json_number(session.last_price or levels.last_price),
            "vwap": _json_number(decision.vwap or levels.vwap),
            "atr": _json_number(decision.atr or levels.atr),
            "suggested_entry": _json_number(decision.suggested_entry),
            "suggested_exit": _json_number(decision.suggested_exit),
            "target_price": _json_number(decision.target_price),
            "stop_loss": _json_number(decision.stop_loss),
            "change_percent": _json_number(extra_change if extra_change is not None else change_percent),
            "trade_count": session.trade_count,
            "reasons": reasons,
        }
