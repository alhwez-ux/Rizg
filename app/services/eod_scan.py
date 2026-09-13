"""End-of-day close/volume scan for next-session bounce and momentum watches."""

from __future__ import annotations

from statistics import median
from typing import Any, Mapping

from app.services.shariah import company_name_for, is_prohibited

SIGNAL_EOD_MOMENTUM = "زخم إغلاق تاريخي — ارتقاب الغد 🚀"
SIGNAL_EOD_BOUNCE = "ارتداد إغلاق إيجابي — ارتقاب الغد 📈"
KIND_MOMENTUM = "momentum"
KIND_BOUNCE = "bounce"
MIN_SCORE = 56
SCAN_LIMIT = 12


def scan_end_of_day(snapshots: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Score last close + closing volume. Does not require a live tick stream."""

    rows: list[dict[str, Any]] = []
    volumes = [_positive(_number(item.get("session_volume") or item.get("volume"))) for item in snapshots]
    typical_volume = median([value for value in volumes if value]) if any(volumes) else 0.0
    for item in snapshots:
        row = evaluate_close_setup(item, typical_volume=typical_volume)
        if row is not None:
            rows.append(row)
    rows.sort(key=lambda item: int(item.get("confidence_score") or 0), reverse=True)
    return rows[:SCAN_LIMIT]


def evaluate_close_setup(snapshot: Mapping[str, Any], *, typical_volume: float = 0.0) -> dict[str, Any] | None:
    symbol = str(snapshot.get("symbol") or "").strip().upper()
    if not symbol or is_prohibited(symbol):
        return None
    close = _positive(_number(snapshot.get("last_price") or snapshot.get("close_price") or snapshot.get("close")))
    if close is None:
        return None
    volume = _positive(_number(snapshot.get("session_volume") or snapshot.get("volume"))) or 0.0
    vol_ratio = _positive(_number(snapshot.get("volume_ratio")))
    if vol_ratio is None:
        vol_ratio = (volume / typical_volume) if typical_volume > 0 else 1.0
    change = _number(snapshot.get("change_percent")) or 0.0
    mfi = _number(snapshot.get("institutional_mfi") or snapshot.get("mfi")) or 50.0
    net_flow = _number(snapshot.get("net_flow")) or 0.0
    high = _positive(_number(snapshot.get("session_high"))) or close
    low = _positive(_number(snapshot.get("session_low"))) or close
    atr = _positive(_number(snapshot.get("atr"))) or max(close * 0.012, 0.05)
    trap = snapshot.get("trap") if isinstance(snapshot.get("trap"), Mapping) else {}
    trap_kind = str(trap.get("kind") or "")
    name = str(snapshot.get("name") or company_name_for(symbol) or symbol)

    bounce = _bounce_close_score(
        close=close,
        high=high,
        low=low,
        change=change,
        vol_ratio=vol_ratio,
        mfi=mfi,
        net_flow=net_flow,
        trap_kind=trap_kind,
    )
    momentum = _momentum_close_score(
        close=close,
        high=high,
        change=change,
        vol_ratio=vol_ratio,
        mfi=mfi,
        net_flow=net_flow,
        trap_kind=trap_kind,
    )
    if bounce >= momentum and bounce >= MIN_SCORE:
        kind = KIND_BOUNCE
        signal = SIGNAL_EOD_BOUNCE
        score = bounce
        reason = (
            f"إغلاق نهائي {close:.2f} بعد اختبار {low:.2f}، "
            f"وحجم ختامي {vol_ratio:.1f}× المتوسط — ارتقاب ارتداد جلسة الغد."
        )
        target = close + max(atr * 1.4, close * 0.025)
        stop = min(close - atr, low * 0.995)
    elif momentum >= MIN_SCORE:
        kind = KIND_MOMENTUM
        signal = SIGNAL_EOD_MOMENTUM
        score = momentum
        reason = (
            f"إغلاق نهائي {close:.2f} بزخم وحجم ختامي {vol_ratio:.1f}× المتوسط "
            f"(MFI {mfi:.0f}) — ارتقاب استمرار الاتجاه غداً."
        )
        target = close + max(atr * 1.6, close * 0.03)
        stop = close - max(atr, close * 0.015)
    else:
        return None
    if stop >= close or target <= close:
        return None
    return {
        "symbol": symbol,
        "name": name,
        "close_price": round(close, 2),
        "signal_type": signal,
        "signal_kind": kind,
        "confidence": f"{int(score)}%",
        "confidence_score": int(score),
        "entry_price": f"{close:.2f}",
        "target_price": f"{target:.2f}",
        "stop_loss": f"{stop:.2f}",
        "reason": reason,
        "volume_ratio": round(vol_ratio, 2),
        "mfi": round(mfi, 1),
        "scan_mode": "end_of_day",
        "horizon": "next_session",
    }


def _bounce_close_score(
    *,
    close: float,
    high: float,
    low: float,
    change: float,
    vol_ratio: float,
    mfi: float,
    net_flow: float,
    trap_kind: str,
) -> int:
    score = 16
    if low < close * 0.992:
        score += 18
    if change >= 0:
        score += 12
    elif change > -1.2:
        score += 6
    if trap_kind == "silent_accumulation" or mfi <= 42:
        score += 16
    elif mfi <= 50:
        score += 8
    if vol_ratio >= 1.4:
        score += 14
    elif vol_ratio >= 1.1:
        score += 8
    if net_flow > 0:
        score += 8
    if close >= high * 0.997 and low < close * 0.99:
        score += 8
    return min(score, 96)


def _momentum_close_score(
    *,
    close: float,
    high: float,
    change: float,
    vol_ratio: float,
    mfi: float,
    net_flow: float,
    trap_kind: str,
) -> int:
    score = 16
    if change >= 0.6:
        score += 20
    elif change > 0:
        score += 12
    if close >= high * 0.997:
        score += 12
    if vol_ratio >= 1.8:
        score += 22
    elif vol_ratio >= 1.35:
        score += 16
    elif vol_ratio >= 1.15:
        score += 8
    if mfi >= 55 or net_flow > 0:
        score += 14
    if vol_ratio >= 1.6 and change >= 0:
        score += 12
    if trap_kind in {"bull_trap", "silent_distribution"}:
        score -= 20
    return min(max(score, 0), 96)


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
