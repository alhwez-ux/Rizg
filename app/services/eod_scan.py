"""End-of-day close recommendations with strict entry and false-breakout guards."""

from __future__ import annotations

from typing import Any, Mapping

from app.models.screener import is_tasi_main_symbol
from app.services.shariah import company_name_for, is_prohibited

SIGNAL_EOD_MOMENTUM = "توصية إغلاق — اختراق 🚀"
SIGNAL_EOD_BOUNCE = "توصية إغلاق — اختراق بعد اختبار 📈"
KIND_MOMENTUM = "momentum"
KIND_BOUNCE = "bounce"
LOOKBACK = 10
MIN_VOLUME_MULTIPLE = 1.5
MIN_BREAKOUT_PCT = 0.25
MAX_EXTENSION_PCT = 8.0
MAX_DAILY_CHANGE = 9.5
MAX_UPPER_WICK = 0.42
MIN_CLOSE_IN_RANGE = 0.62
MIN_REWARD_RATIO = 1.3
MFI_EXHAUSTION = 82
SCAN_LIMIT = 12


def scan_end_of_day(snapshots: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """List names that clear close-breakout entry and anti-trap filters."""

    rows: list[dict[str, Any]] = []
    for item in snapshots:
        row = evaluate_close_setup(item)
        if row is not None:
            rows.append(row)
    rows.sort(key=lambda item: int(item.get("confidence_score") or 0), reverse=True)
    return rows[:SCAN_LIMIT]


def evaluate_close_setup(snapshot: Mapping[str, Any], *, typical_volume: float = 0.0) -> dict[str, Any] | None:
    del typical_volume
    symbol = str(snapshot.get("symbol") or "").strip().upper()
    if not symbol or not is_tasi_main_symbol(symbol) or is_prohibited(symbol):
        return None
    closes, volumes = _close_volume_series(snapshot)
    if len(closes) < LOOKBACK + 1:
        return _evaluate_session_close(snapshot)
    close = closes[-1]
    volume = volumes[-1]
    prior_closes = closes[-(LOOKBACK + 1) : -1]
    prior_volumes = volumes[-(LOOKBACK + 1) : -1]
    resistance = max(prior_closes)
    avg_volume = sum(prior_volumes) / len(prior_volumes) if prior_volumes else 0.0
    vol_ratio = (volume / avg_volume) if avg_volume > 0 else 0.0
    sma = sum(closes[-LOOKBACK:]) / LOOKBACK
    atr = _atr(snapshot, closes, close)
    high = _positive(_number(snapshot.get("session_high"))) or close
    low = _positive(_number(snapshot.get("session_low"))) or min(close, prior_closes[-1])
    change = _number(snapshot.get("change_percent"))
    if change is None and len(closes) >= 2 and closes[-2] > 0:
        change = ((close - closes[-2]) / closes[-2]) * 100
    change = change or 0.0
    mfi = _number(snapshot.get("institutional_mfi") or snapshot.get("mfi")) or 50.0
    net_flow = _number(snapshot.get("net_flow")) or 0.0
    trap = snapshot.get("trap") if isinstance(snapshot.get("trap"), Mapping) else {}
    trap_kind = str(trap.get("kind") or "")
    name = str(snapshot.get("name") or company_name_for(symbol) or symbol)

    if not _breakout_ok(close, resistance, atr):
        return None
    if not _volume_ok(volume, avg_volume, vol_ratio):
        return None
    if not _liquidity_ok(snapshot, net_flow=net_flow, mfi=mfi, trap_kind=trap_kind):
        return None
    if not _momentum_ok(closes, close, sma):
        return None
    blocked = _false_entry_reason(
        snapshot,
        close=close,
        high=high,
        low=low,
        change=change,
        sma=sma,
        atr=atr,
        resistance=resistance,
        vol_ratio=vol_ratio,
        mfi=mfi,
        trap_kind=trap_kind,
    )
    if blocked:
        return None

    shakeout = low < close * 0.985 and low < resistance
    kind = KIND_BOUNCE if shakeout else KIND_MOMENTUM
    signal = SIGNAL_EOD_BOUNCE if shakeout else SIGNAL_EOD_MOMENTUM
    target = close + max(atr * 1.6, close * 0.03)
    stop = min(close - atr, resistance * 0.997, low * 0.995)
    if stop >= close or target <= close:
        return None
    reward = (target - close) / max(close - stop, 1e-9)
    if reward < MIN_REWARD_RATIO:
        return None
    score = _confidence(
        close=close,
        resistance=resistance,
        vol_ratio=vol_ratio,
        net_flow=net_flow,
        mfi=mfi,
        sma=sma,
        macd=_macd_bullish(closes),
        shakeout=shakeout,
    )
    rule = (
        f"إغلاق فوق أعلى إغلاق لـ{LOOKBACK} جلسات "
        f"وحجم ≥ {MIN_VOLUME_MULTIPLE:.0%} من المتوسط مع تدفق إيجابي وزخم فوق المتوسط"
    )
    reason = (
        f"تحقق شرط الدخول على إغلاق {close:.2f} فوق مقاومة {resistance:.2f} "
        f"(آخر {LOOKBACK} جلسات) بحجم ختامي {vol_ratio:.1f}× المتوسط، "
        f"وسيولة غير تصريفية، واستقرار فوق المتوسط {sma:.2f} — ارتقاب جلسة الغد."
    )
    return {
        "symbol": symbol,
        "name": name,
        "close_price": round(close, 2),
        "signal_type": signal,
        "signal_kind": kind,
        "confidence": f"{score}%",
        "confidence_score": score,
        "entry": True,
        "entry_price": f"{close:.2f}",
        "target_price": f"{target:.2f}",
        "stop_loss": f"{stop:.2f}",
        "reason": reason,
        "entry_rule": rule,
        "volume_ratio": round(vol_ratio, 2),
        "mfi": round(mfi, 1),
        "scan_mode": "end_of_day",
        "horizon": "next_session",
    }


def _evaluate_session_close(snapshot: Mapping[str, Any]) -> dict[str, Any] | None:
    """Close pick from today's UniTicker session when 10-day history is not stored yet."""

    symbol = str(snapshot.get("symbol") or "").strip().upper()
    close = _positive(_number(snapshot.get("last_price") or snapshot.get("close_price")))
    prev = _positive(_number(snapshot.get("prev_close")))
    volume = _positive(_number(snapshot.get("session_volume") or snapshot.get("volume"))) or 0.0
    if not symbol or close is None or prev is None or volume <= 0:
        return None
    if close <= prev:
        return None
    change = _number(snapshot.get("change_percent"))
    if change is None and prev > 0:
        change = ((close - prev) / prev) * 100
    change = change or 0.0
    if change <= MIN_BREAKOUT_PCT:
        return None
    high = _positive(_number(snapshot.get("session_high"))) or close
    low = _positive(_number(snapshot.get("session_low"))) or min(close, prev)
    opened = _positive(_number(snapshot.get("session_open") or snapshot.get("open"))) or prev
    mfi = _number(snapshot.get("institutional_mfi") or snapshot.get("mfi")) or 50.0
    net_flow = _number(snapshot.get("net_flow")) or 0.0
    trap = snapshot.get("trap") if isinstance(snapshot.get("trap"), Mapping) else {}
    trap_kind = str(trap.get("kind") or "")
    atr = max(close * 0.012, abs(high - low), 0.05)
    sma = (prev + close) / 2
    if close < opened:
        return None
    if not _liquidity_ok(snapshot, net_flow=net_flow, mfi=mfi, trap_kind=trap_kind):
        return None
    blocked = _false_entry_reason(
        snapshot,
        close=close,
        high=high,
        low=low,
        change=change,
        sma=sma,
        atr=atr,
        resistance=prev,
        vol_ratio=max(_number(snapshot.get("liquidity_flow")) or 1.0, 1.0),
        mfi=mfi,
        trap_kind=trap_kind,
        max_range_pct=0.095,
    )
    if blocked:
        return None
    shakeout = low < close * 0.985 and low < prev
    kind = KIND_BOUNCE if shakeout else KIND_MOMENTUM
    signal = SIGNAL_EOD_BOUNCE if shakeout else SIGNAL_EOD_MOMENTUM
    target = close + max(atr * 1.6, close * 0.03)
    stop = min(close - atr, prev * 0.997, low * 0.995)
    if stop >= close or target <= close:
        return None
    reward = (target - close) / max(close - stop, 1e-9)
    if reward < MIN_REWARD_RATIO:
        return None
    score = _confidence(
        close=close,
        resistance=prev,
        vol_ratio=1.6,
        net_flow=net_flow,
        mfi=mfi,
        sma=sma,
        macd=close > prev,
        shakeout=shakeout,
    )
    name = str(snapshot.get("name") or company_name_for(symbol) or symbol)
    return {
        "symbol": symbol,
        "name": name,
        "close_price": round(close, 2),
        "signal_type": signal,
        "signal_kind": kind,
        "confidence": f"{score}%",
        "confidence_score": score,
        "entry": True,
        "entry_price": f"{close:.2f}",
        "target_price": f"{target:.2f}",
        "stop_loss": f"{stop:.2f}",
        "reason": (
            f"إغلاق جلسة اليوم {close:.2f} فوق إغلاق أمس {prev:.2f} "
            f"({change:.2f}%) مع سيولة غير تصريفية — ارتقاب جلسة الغد."
        ),
        "entry_rule": "إغلاق اليوم أعلى من الإغلاق السابق مع تدفق غير سلبي واستقرار قرب أعلى الجلسة",
        "volume_ratio": round(float(_number(snapshot.get("liquidity_flow")) or 1.0), 2),
        "mfi": round(mfi, 1),
        "scan_mode": "end_of_day",
        "horizon": "next_session",
    }


def _breakout_ok(close: float, resistance: float, atr: float) -> bool:
    if close <= resistance:
        return False
    margin = max(resistance * (MIN_BREAKOUT_PCT / 100), atr * 0.15)
    return close >= resistance + margin


def _volume_ok(volume: float, avg_volume: float, vol_ratio: float) -> bool:
    if volume <= 0 or avg_volume <= 0:
        return volume <= 0 and avg_volume <= 0
    return vol_ratio >= MIN_VOLUME_MULTIPLE


def _liquidity_ok(snapshot: Mapping[str, Any], *, net_flow: float, mfi: float, trap_kind: str) -> bool:
    if trap_kind in {"bull_trap", "silent_distribution"}:
        return False
    if net_flow < 0:
        return False
    ask_wall = snapshot.get("ask_wall") if isinstance(snapshot.get("ask_wall"), Mapping) else {}
    bid_wall = snapshot.get("bid_wall") if isinstance(snapshot.get("bid_wall"), Mapping) else {}
    ask_qty = _positive(_number(ask_wall.get("quantity"))) or 0.0
    bid_qty = _positive(_number(bid_wall.get("quantity"))) or 0.0
    if ask_qty > 0 and bid_qty > 0 and ask_qty >= bid_qty * 3:
        return False
    book = _number(snapshot.get("book_pressure"))
    bid_size = _positive(_number(snapshot.get("bid_size")))
    ask_size = _positive(_number(snapshot.get("ask_size")))
    accumulation = trap_kind == "silent_accumulation" or mfi >= 55
    balanced = book is not None and book >= 0
    if bid_size and ask_size and bid_size >= ask_size * 0.95:
        balanced = True
    if net_flow == 0 and book is None and not bid_size and not ask_size:
        return True
    return net_flow > 0 or accumulation or balanced


def _momentum_ok(closes: list[float], close: float, sma: float) -> bool:
    if close < sma:
        return False
    return _macd_bullish(closes) or close >= sma


def _false_entry_reason(
    snapshot: Mapping[str, Any],
    *,
    close: float,
    high: float,
    low: float,
    change: float,
    sma: float,
    atr: float,
    resistance: float,
    vol_ratio: float,
    mfi: float,
    trap_kind: str,
    max_range_pct: float = 0.06,
) -> str | None:
    if trap_kind in {"bull_trap", "silent_distribution"}:
        return "trap"
    if change >= MAX_DAILY_CHANGE:
        return "limit_chase"
    candle_range = max(high - low, 1e-9)
    if candle_range / close > max_range_pct:
        return "wide_range"
    if (high - close) / candle_range >= MAX_UPPER_WICK:
        return "upper_wick"
    if (close - low) / candle_range < MIN_CLOSE_IN_RANGE:
        return "weak_close"
    if sma > 0 and (close - sma) / sma * 100 > MAX_EXTENSION_PCT:
        return "overextended"
    if atr > 0 and close - resistance > atr * 8:
        return "runaway_break"
    if mfi >= MFI_EXHAUSTION and vol_ratio < 1.8:
        return "exhaustion"
    spread = _number(snapshot.get("spread"))
    if spread is not None and close > 0 and spread / close > 0.02:
        return "wide_spread"
    return None


def _confidence(
    *,
    close: float,
    resistance: float,
    vol_ratio: float,
    net_flow: float,
    mfi: float,
    sma: float,
    macd: bool,
    shakeout: bool,
) -> int:
    score = 58
    if resistance > 0:
        score += min(12, int(((close - resistance) / resistance) * 400))
    if vol_ratio >= 2.0:
        score += 12
    elif vol_ratio >= 1.5:
        score += 8
    if net_flow > 0:
        score += 8
    if mfi >= 55:
        score += 6
    if sma > 0 and close >= sma:
        score += 6
    if macd:
        score += 6
    if shakeout:
        score += 4
    return min(score, 94)


def _close_volume_series(snapshot: Mapping[str, Any]) -> tuple[list[float], list[float]]:
    closes = _float_list(snapshot.get("closes") or snapshot.get("close_series"))
    volumes = _float_list(snapshot.get("volumes") or snapshot.get("volume_series"))
    last = _positive(_number(snapshot.get("last_price") or snapshot.get("close_price") or snapshot.get("close")))
    volume = _positive(_number(snapshot.get("session_volume") or snapshot.get("volume"))) or 0.0
    if last is None:
        return [], []
    if not closes:
        return [], []
    if abs(closes[-1] - last) > max(last * 0.0001, 1e-6):
        closes = [*closes, last]
        volumes = [*volumes, volume] if volumes else [0.0] * (len(closes) - 1) + [volume]
    elif len(volumes) < len(closes):
        volumes = [*volumes, *[0.0] * (len(closes) - len(volumes) - 1), volume or (volumes[-1] if volumes else 0.0)]
    elif volume > 0:
        volumes[-1] = volume
    if len(volumes) != len(closes):
        volumes = (volumes + [0.0] * len(closes))[: len(closes)]
    return closes, volumes


def _atr(snapshot: Mapping[str, Any], closes: list[float], close: float) -> float:
    stored = _positive(_number(snapshot.get("atr")))
    if stored:
        return stored
    sample = closes[:-1] if len(closes) > LOOKBACK else closes
    if len(sample) >= 6:
        moves = [abs(sample[index] - sample[index - 1]) for index in range(1, len(sample))]
        return max(sum(moves[-5:]) / 5, close * 0.008)
    return max(close * 0.012, 0.05)


def _macd_bullish(closes: list[float]) -> bool:
    if len(closes) < 35:
        return False
    fast = _ema(closes, 12)
    slow = _ema(closes, 26)
    macd = [fast[index] - slow[index] for index in range(min(len(fast), len(slow)))]
    signal = _ema(macd, 9)
    if len(macd) < 2 or len(signal) < 2:
        return False
    crossed = macd[-1] > signal[-1] and macd[-2] <= signal[-2]
    holding = macd[-1] > signal[-1] and macd[-1] >= macd[-2]
    return crossed or holding


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    k = 2 / (period + 1)
    out = [values[0]]
    for value in values[1:]:
        out.append(value * k + out[-1] * (1 - k))
    return out


def _float_list(raw: Any) -> list[float]:
    if not isinstance(raw, (list, tuple)):
        return []
    values: list[float] = []
    for item in raw:
        number = _positive(_number(item))
        if number is not None:
            values.append(number)
    return values


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or abs(number) == float("inf"):
        return None
    return number


def _positive(value: float | None) -> float | None:
    if value is None or value <= 0:
        return None
    return value
