"""TASI index correction states from measured daily bars and leader tapes.

Missing volume, EMA history, institutional flow, or block prints stay silent.
The index is never marked safe until twenty measured closes exist.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

STATE_SAFE = "safe"
STATE_APPROACH = "approach"
STATE_CONFIRMED = "confirmed"
STATE_ENDING = "ending"
STATE_REBOUND = "rebound"

LABELS = {
    STATE_SAFE: "آمن",
    STATE_APPROACH: "اقتراب تصحيحي ⚠️",
    STATE_CONFIRMED: "تصحيح جارٍ 🔴",
    STATE_ENDING: "اقتراب انتهاء التصحيح",
    STATE_REBOUND: "ارتداد ونهاية تصحيح ✅",
}

REASON_PEAKS = "قمم صاعدة بأحجام متناقصة"
REASON_EMA = "كسر متوسط 20"
REASON_VWAP = "كسر متوسط الجلسة"
REASON_SUPPORT = "كسر دعم الإغلاقات الأخيرة"
REASON_TWO_DOWN = "إغلاق جلستين متتاليتين بسالب"
REASON_OUTFLOW = "تدفق خارج من الأسهم القيادية"
REASON_NEAR = "اقتراب من دعم أو متوسط 50"
REASON_DRY = "جفاف في حجوم البيع"
REASON_CANDLE = "شمعة ارتداد إيجابية بحجم أعلى من المتوسط"
REASON_FLOW_IN = "سيولة مؤسسية داخلة في القياديات"
REASON_BLOCKS = "كتل شرائية عند القاع"

LEADERS = ("2222", "1120", "1180", "7010", "2010", "1150")
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETASI.SR"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
_TOUCH = 0.015
_SURGE = 1.5
_STRONG = 0.004
_CACHE_SECONDS = 60.0
_RIYADH = timezone(timedelta(hours=3))
_bars_cache: tuple[float, list[tuple[str, float, float]]] | None = None


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _positive(value: Any) -> float | None:
    number = _num(value)
    if number is None or number <= 0:
        return None
    return number


def _ema(values: list[float], period: int) -> float | None:
    if len(values) < period or period < 1:
        return None
    seed = sum(values[:period]) / period
    weight = 2.0 / (period + 1)
    current = seed
    for price in values[period:]:
        current = price * weight + current * (1.0 - weight)
    return current


def _near(price: float, level: float | None) -> bool:
    if level is None or price <= 0 or level <= 0:
        return False
    return abs(price - level) / level <= _TOUCH


def _bars(history: Any) -> list[tuple[str, float, float]]:
    rows: list[tuple[str, float, float]] = []
    if not isinstance(history, list):
        return []
    for item in history:
        if not isinstance(item, dict):
            continue
        close = _positive(item.get("close") or item.get("last_price"))
        volume = _positive(item.get("volume"))
        if close is None or volume is None:
            continue
        day = str(item.get("date") or "")[:10]
        rows.append((day, close, volume))
    rows.sort(key=lambda row: row[0])
    return rows


def _leader_stats(leaders: Any, index_near_low: bool) -> dict[str, int]:
    measured = negative = positive = blocks = 0
    if not isinstance(leaders, list):
        return {"measured": 0, "negative": 0, "positive": 0, "blocks": 0}
    for item in leaders:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").strip().upper()
        if symbol not in LEADERS:
            continue
        inflow = _num(item.get("institutional_inflow")) if "institutional_inflow" in item else None
        outflow = _num(item.get("institutional_outflow")) if "institutional_outflow" in item else None
        if inflow is not None and outflow is not None and inflow >= 0 and outflow >= 0 and inflow + outflow > 0:
            measured += 1
            net = inflow - outflow
            if net < 0:
                negative += 1
            elif net > 0:
                positive += 1
        trades = int(_num(item.get("block_trades")) or 0)
        block_volume = _positive(item.get("block_volume") or item.get("last_block_value"))
        if index_near_low and trades >= 1 and block_volume is not None and item.get("block_side") == "buy":
            blocks += 1
    return {"measured": measured, "negative": negative, "positive": positive, "blocks": blocks}


def classify_tasi_index(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Return one index state, or None when the daily series is too short to judge."""

    if not isinstance(snapshot, dict):
        return None
    series = _bars(snapshot.get("history"))
    closes = [row[1] for row in series]
    volumes = [row[2] for row in series]
    if len(closes) < 4:
        return None
    last = closes[-1]
    previous = closes[-2]
    change = ((last - previous) / previous) * 100.0 if previous else None
    reasons: list[str] = []

    peaks = (
        closes[-1] > closes[-2] > closes[-3]
        and volumes[-1] < volumes[-2] < volumes[-3]
    )
    ema_now = _ema(closes, 20)
    ema_prev = _ema(closes[:-1], 20)
    ema_break = (
        ema_now is not None
        and ema_prev is not None
        and closes[-2] >= ema_prev
        and last < ema_now
    )
    vwap = _positive(snapshot.get("session_vwap"))
    vwap_break = vwap is not None and closes[-2] >= vwap and last < vwap

    prior = closes[:-2]
    support = min(prior[-20:]) if len(prior) >= 15 else None
    support_break = support is not None and last < support
    two_down = closes[-1] < closes[-2] < closes[-3]

    ema50 = _ema(closes, 50)
    weekly = min(closes[-6:-1]) if len(closes) >= 6 else None
    monthly = min(closes[-21:-1]) if len(closes) >= 21 else None
    near_support = _near(last, ema50) or _near(last, weekly) or _near(last, monthly)
    drying = volumes[-1] < volumes[-2] < volumes[-3] and last < closes[-4]
    below_fast = ema_now is not None and last < ema_now

    prior_volumes = volumes[-11:-1]
    average = sum(prior_volumes) / len(prior_volumes) if len(prior_volumes) == 10 else None
    strong = (
        last > previous
        and previous > 0
        and (last - previous) / previous >= _STRONG
        and average is not None
        and volumes[-1] >= average * _SURGE
    )

    leaders = _leader_stats(snapshot.get("leaders"), near_support)
    heavy_out = leaders["measured"] >= 2 and leaders["negative"] >= 2 and leaders["negative"] * 2 >= leaders["measured"]
    heavy_in = leaders["measured"] >= 2 and leaders["positive"] >= 2 and leaders["positive"] * 2 >= leaders["measured"]

    state: str | None = None
    if strong and near_support and (heavy_in or leaders["blocks"] >= 1):
        state = STATE_REBOUND
        reasons.append(REASON_CANDLE)
        if heavy_in:
            reasons.append(REASON_FLOW_IN)
        if leaders["blocks"] >= 1:
            reasons.append(REASON_BLOCKS)
    elif support_break and two_down and heavy_out:
        state = STATE_CONFIRMED
        reasons.extend([REASON_SUPPORT, REASON_TWO_DOWN, REASON_OUTFLOW])
    elif near_support and drying and below_fast:
        state = STATE_ENDING
        reasons.extend([REASON_NEAR, REASON_DRY])
    elif peaks or ema_break or vwap_break:
        state = STATE_APPROACH
        if peaks:
            reasons.append(REASON_PEAKS)
        if ema_break:
            reasons.append(REASON_EMA)
        if vwap_break:
            reasons.append(REASON_VWAP)
    elif len(closes) >= 20:
        state = STATE_SAFE
    else:
        return None

    return {
        "symbol": "TASI",
        "state": state,
        "label": LABELS[state],
        "alert": state in {STATE_APPROACH, STATE_CONFIRMED},
        "value": round(last, 2),
        "change_percent": None if change is None else round(change, 4),
        "reasons": reasons,
        "ema20": None if ema_now is None else round(ema_now, 2),
        "ema50": None if ema50 is None else round(ema50, 2),
    }


def parse_tasi_chart(payload: dict[str, Any]) -> list[tuple[str, float, float]]:
    """Collapse Yahoo candles into one Riyadh session: last close and summed volume.

    The daily chart for this index returns a single bar, so the caller asks for hourly
    candles and this function folds them into sessions.
    """

    result = ((payload.get("chart") or {}).get("result") or [None])[0] or {}
    stamps = result.get("timestamp") if isinstance(result, dict) else None
    quote = ((result.get("indicators") or {}).get("quote") or [None])[0] if isinstance(result, dict) else None
    closes = quote.get("close") if isinstance(quote, dict) else None
    volumes = quote.get("volume") if isinstance(quote, dict) else None
    if not isinstance(stamps, list) or not isinstance(closes, list):
        return []
    folded: dict[str, tuple[float, float]] = {}
    for index, stamp in enumerate(stamps):
        close = _positive(closes[index] if index < len(closes) else None)
        if close is None:
            continue
        raw_volume = volumes[index] if isinstance(volumes, list) and index < len(volumes) else None
        volume = _num(raw_volume)
        if volume is None or volume < 0:
            volume = 0.0
        try:
            day = datetime.fromtimestamp(float(stamp), tz=_RIYADH).date().isoformat()
        except (TypeError, ValueError, OSError):
            continue
        previous = folded.get(day)
        if previous is None:
            folded[day] = (close, volume)
        else:
            folded[day] = (close, previous[1] + volume)
    rows = [(day, close, volume) for day, (close, volume) in folded.items() if volume > 0]
    rows.sort(key=lambda row: row[0])
    return rows


def completed_sessions(
    bars: list[tuple[str, float, float]],
    now: datetime | None = None,
) -> list[tuple[str, float, float]]:
    """Drop today's candle before 16:00 Riyadh so a partial session cannot fake fading volume."""

    if not bars:
        return []
    clock = now.astimezone(_RIYADH) if now is not None else datetime.now(_RIYADH)
    if bars[-1][0] != clock.date().isoformat():
        return list(bars)
    if clock.weekday() in (4, 5):
        return list(bars)
    if clock.hour >= 16:
        return list(bars)
    return list(bars[:-1])


def cached_tasi_bars(*, fetcher: Any = None) -> list[tuple[str, float, float]]:
    global _bars_cache
    now = time.monotonic()
    if fetcher is None and _bars_cache and now - _bars_cache[0] < _CACHE_SECONDS:
        return list(_bars_cache[1])
    load = fetcher or _download_tasi_bars
    try:
        bars = list(load() or [])
    except Exception:
        logger.warning("TASI correction history unavailable", exc_info=True)
        return list(_bars_cache[1]) if _bars_cache else []
    if bars and fetcher is None:
        _bars_cache = (now, bars)
    return bars


def _download_tasi_bars() -> list[tuple[str, float, float]]:
    with httpx.Client(timeout=httpx.Timeout(8.0, connect=3.0), headers={"User-Agent": _UA}) as http:
        response = http.get(YAHOO_CHART, params={"interval": "1h", "range": "1y"})
        response.raise_for_status()
        return parse_tasi_chart(response.json())


def _leader_rows(feed: Any) -> list[dict[str, Any]]:
    if feed is None:
        return []
    quotes = getattr(feed, "_quotes", None)
    tapes = getattr(feed, "_tapes", None)
    tapes = tapes if isinstance(tapes, dict) else {}
    rows: list[dict[str, Any]] = []
    for symbol in LEADERS:
        tape = tapes.get(symbol)
        snap = getattr(tape, "snapshot", None)
        live: dict[str, Any] = {}
        if callable(snap):
            try:
                payload = snap()
                if isinstance(payload, dict):
                    live = payload
            except Exception:
                live = {}
        history = []
        if quotes is not None and callable(getattr(quotes, "close_history", None)):
            try:
                history = quotes.close_history(symbol)
            except Exception:
                history = []
        rows.append(
            {
                "symbol": symbol,
                "history": history,
                "institutional_inflow": live.get("institutional_inflow"),
                "institutional_outflow": live.get("institutional_outflow"),
                "block_trades": live.get("block_trades") or 0,
                "block_volume": live.get("block_volume"),
                "block_side": live.get("block_side"),
            }
        )
    return rows


def build_tasi_correction(feed: Any = None, *, bars: list[tuple[str, float, float]] | None = None) -> dict[str, Any]:
    series = completed_sessions(bars if bars is not None else cached_tasi_bars())
    history = [{"date": day, "close": close, "volume": volume} for day, close, volume in series]
    classified = classify_tasi_index({"history": history, "leaders": _leader_rows(feed)})
    if classified is None:
        return {
            "success": True,
            "symbol": "TASI",
            "state": None,
            "label": "",
            "alert": False,
            "value": None,
            "change_percent": None,
            "reasons": [],
            "ema20": None,
            "ema50": None,
        }
    return {"success": True, **classified}
