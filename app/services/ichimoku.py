"""Ichimoku cloud and candlestick reading from measured daily bars.

A reading is returned only when 78 sessions have open, high, low, and close.
Missing bars stay silent. Nothing here is filled from the close alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

TENKAN = 9
KIJUN = 26
SENKOU_B = 52
SHIFT = 26
_MIN_BARS = SENKOU_B + SHIFT


@dataclass(frozen=True)
class _Bar:
    day: str
    open: float
    high: float
    low: float
    close: float


def history_has_cloud(bars: list[dict[str, Any]]) -> bool:
    """True when stored sessions already contain a full displaced cloud."""

    return len(_series(bars, None)) >= _MIN_BARS


def ichimoku_reading(bars: list[dict[str, Any]], today: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Trend and entry/exit from the latest session that has a full cloud."""

    series = _series(bars, today)
    if len(series) < _MIN_BARS:
        return None
    tenkan, kijun, span_a, span_b = _lines(series)
    last = len(series) - 1
    source = last - SHIFT
    previous = last - 1
    previous_source = previous - SHIFT
    if not _ready(tenkan, kijun, span_a, span_b, last, source, previous, previous_source):
        return None
    cloud_top, cloud_bottom = _band(span_a[source], span_b[source])
    prior_top, prior_bottom = _band(span_a[previous_source], span_b[previous_source])
    close = series[last].close
    prior_close = series[previous].close
    future_a = span_a[last]
    future_b = span_b[last]
    if future_a is None or future_b is None:
        return None
    pattern = _pattern(series[previous], series[last])
    bullish_cross = tenkan[last] > kijun[last] and tenkan[previous] <= kijun[previous]
    bearish_cross = tenkan[last] < kijun[last] and tenkan[previous] >= kijun[previous]
    breakout = close > cloud_top and prior_close <= prior_top
    breakdown = close < cloud_bottom and prior_close >= prior_bottom
    signal = "watch"
    if breakout and bullish_cross and pattern in {"hammer", "bullish_engulfing"}:
        signal = "entry"
    elif (breakdown or bearish_cross) and pattern in {"shooting_star", "bearish_engulfing"}:
        signal = "exit"
    trend = _trend(close, cloud_top, cloud_bottom, future_a, future_b)
    return {
        "trend": trend,
        "position": _position(close, cloud_top, cloud_bottom),
        "signal": signal,
        "pattern": pattern,
        "tenkan": round(float(tenkan[last]), 4),
        "kijun": round(float(kijun[last]), 4),
        "span_a": round(float(span_a[source]), 4),
        "span_b": round(float(span_b[source]), 4),
        "future_span_a": round(float(future_a), 4),
        "future_span_b": round(float(future_b), 4),
        "chikou": round(close, 4),
    }


def _position(close: float, top: float, bottom: float) -> str:
    if bottom <= close <= top:
        return "inside"
    if close > top:
        return "above"
    return "below"


def _trend(close: float, top: float, bottom: float, future_a: float, future_b: float) -> str | None:
    if bottom <= close <= top:
        return "range"
    if close > top and future_a > future_b:
        return "up"
    if close < bottom and future_a < future_b:
        return "down"
    return None


def _ready(*args: Any) -> bool:
    tenkan, kijun, span_a, span_b, last, source, previous, previous_source = args
    needed = (
        tenkan[last],
        kijun[last],
        tenkan[previous],
        kijun[previous],
        span_a[source],
        span_b[source],
        span_a[previous_source],
        span_b[previous_source],
    )
    return all(value is not None for value in needed)


def _lines(
    series: list[_Bar],
) -> tuple[list[float | None], list[float | None], list[float | None], list[float | None]]:
    count = len(series)
    tenkan: list[float | None] = [None] * count
    kijun: list[float | None] = [None] * count
    span_a: list[float | None] = [None] * count
    span_b: list[float | None] = [None] * count
    highs = [bar.high for bar in series]
    lows = [bar.low for bar in series]
    for index in range(count):
        if index + 1 >= TENKAN:
            tenkan[index] = _mid(highs[index + 1 - TENKAN : index + 1], lows[index + 1 - TENKAN : index + 1])
        if index + 1 >= KIJUN:
            kijun[index] = _mid(highs[index + 1 - KIJUN : index + 1], lows[index + 1 - KIJUN : index + 1])
        if index + 1 >= SENKOU_B:
            span_b[index] = _mid(highs[index + 1 - SENKOU_B : index + 1], lows[index + 1 - SENKOU_B : index + 1])
        if tenkan[index] is not None and kijun[index] is not None:
            span_a[index] = (float(tenkan[index]) + float(kijun[index])) / 2
    return tenkan, kijun, span_a, span_b


def _mid(highs: list[float], lows: list[float]) -> float:
    return (max(highs) + min(lows)) / 2


def _band(span_a: float | None, span_b: float | None) -> tuple[float, float]:
    left = float(span_a or 0)
    right = float(span_b or 0)
    return max(left, right), min(left, right)


def _pattern(previous: _Bar, current: _Bar) -> str | None:
    if _bearish(previous) and _bullish(current) and current.open <= previous.close and current.close >= previous.open:
        return "bullish_engulfing"
    if _bullish(previous) and _bearish(current) and current.open >= previous.close and current.close <= previous.open:
        return "bearish_engulfing"
    if _hammer(current):
        return "hammer"
    if _shooting_star(current):
        return "shooting_star"
    return None


def _bullish(bar: _Bar) -> bool:
    return bar.close > bar.open


def _bearish(bar: _Bar) -> bool:
    return bar.close < bar.open


def _hammer(bar: _Bar) -> bool:
    body = abs(bar.close - bar.open)
    if body <= 0:
        return False
    lower = min(bar.open, bar.close) - bar.low
    upper = bar.high - max(bar.open, bar.close)
    return lower >= body * 2 and upper <= body


def _shooting_star(bar: _Bar) -> bool:
    body = abs(bar.close - bar.open)
    if body <= 0:
        return False
    upper = bar.high - max(bar.open, bar.close)
    lower = min(bar.open, bar.close) - bar.low
    return upper >= body * 2 and lower <= body


def _series(bars: list[dict[str, Any]], today: dict[str, Any] | None) -> list[_Bar]:
    parsed: dict[str, _Bar] = {}
    for item in bars:
        if not isinstance(item, dict):
            continue
        bar = _bar(item)
        if bar is not None:
            parsed[bar.day] = bar
    if isinstance(today, dict):
        bar = _bar(today)
        if bar is not None:
            parsed[bar.day] = bar
    return [parsed[day] for day in sorted(parsed)]


def _bar(item: dict[str, Any]) -> _Bar | None:
    day_raw = item.get("date") or item.get("session_date")
    day = day_raw.isoformat() if isinstance(day_raw, date) else str(day_raw or "").strip()[:10]
    if len(day) < 10:
        return None
    open_ = _number(item.get("open"))
    high = _number(item.get("high"))
    low = _number(item.get("low"))
    close = _number(item.get("close") if item.get("close") is not None else item.get("last_price"))
    if open_ is None or high is None or low is None or close is None:
        return None
    if high < low or high < max(open_, close) or low > min(open_, close):
        return None
    return _Bar(day, open_, high, low, close)


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number <= 0 or abs(number) == float("inf"):
        return None
    return number
