"""Liquidity fallback when a strict entry plan is absent.

The rows use the tape's own last price. They are labeled as watch names,
not as a confirmed entry.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.models.screener import is_tasi_main_symbol
from app.services.shariah import company_name_for, is_prohibited, is_pure, sector_for
from app.services.signals import is_valid_long_plan, long_trade_levels

MIN_REWARD = Decimal("1.5")
WATCH_LIMIT = 5
WATCH_REASON = "فرص قيد المراقبة - السيولة تتجمع فيها"
CLOSE_SETUP = "أبرز فرص إغلاق الجلسة"
LIVE_SETUP = "فرص قيد المراقبة"


def liquidity_leaders(feed: Any, *, limit: int = WATCH_LIMIT) -> list[dict[str, Any]]:
    """Highest traded value, with positive flow and a price at or above VWAP first."""

    ranked: list[tuple[tuple[int, int, float, float], dict[str, Any]]] = []
    seen: set[str] = set()
    for item in _tape(feed):
        symbol = str(item.get("symbol") or "").strip().upper()
        if symbol in seen or not is_tasi_main_symbol(symbol) or is_prohibited(symbol):
            continue
        price = _positive(item.get("last_price") or item.get("price") or item.get("close_price"))
        if price is None:
            continue
        flow = _number(item.get("net_flow")) or 0.0
        value = _number(item.get("value_traded") or item.get("session_value")) or 0.0
        volume = _number(item.get("volume") or item.get("session_volume")) or 0.0
        if value <= 0 and volume > 0:
            value = price * volume
        if value <= 0 and flow <= 0:
            continue
        vwap = _positive(item.get("session_vwap") or item.get("vwap"))
        above = vwap is None or price >= vwap
        if flow <= 0 and vwap is not None and not above:
            continue
        seen.add(symbol)
        ranked.append(
            (
                (1 if flow > 0 else 0, 1 if above else 0, value, flow),
                {
                    "symbol": symbol,
                    "name": company_name_for(symbol) or str(item.get("name") or symbol),
                    "sector": str(item.get("sector") or sector_for(symbol) or ""),
                    "last_price": price,
                    "net_flow": flow,
                    "value_traded": value,
                },
            )
        )
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [row for _key, row in ranked[: max(1, limit)]]


def watch_recommendation(row: dict[str, Any], *, closed: bool) -> dict[str, Any] | None:
    price = _positive(row.get("last_price"))
    if price is None:
        return None
    plan = _plan(price)
    if plan is None:
        return None
    _entry, target, stop, ratio = plan
    symbol = str(row["symbol"])
    setup = CLOSE_SETUP if closed else LIVE_SETUP
    score = 60 if (row.get("net_flow") or 0) > 0 else 52
    return {
        "symbol": symbol,
        "name": row.get("name") or company_name_for(symbol) or symbol,
        "close_price": price,
        "last_price": price,
        "signal_type": setup,
        "signal_kind": "momentum",
        "confidence": f"{score}%",
        "confidence_score": score,
        "entry_price": f"{price:.2f}",
        "target_price": f"{target:.2f}",
        "stop_loss": f"{stop:.2f}",
        "reason": WATCH_REASON,
        "volume_ratio": None,
        "mfi": None,
        "scan_mode": "end_of_day" if closed else "live",
        "horizon": "close" if closed else "intraday",
        "entry": False,
        "entry_rule": "liquidity_watch",
        "reward_ratio": round(ratio, 2),
    }


def watch_daily_row(row: dict[str, Any], *, closed: bool, pure_only: bool) -> dict[str, Any] | None:
    symbol = str(row.get("symbol") or "").strip().upper()
    if pure_only and not is_pure(symbol):
        return None
    price = _positive(row.get("last_price"))
    if price is None:
        return None
    plan = _plan(price)
    if plan is None:
        return None
    _entry, target, stop, ratio = plan
    from app.services.shariah import classified_status, shariah_label

    return {
        "symbol": symbol,
        "name": str(row.get("name") or company_name_for(symbol) or symbol),
        "sector": str(row.get("sector") or sector_for(symbol) or ""),
        "last_price": price,
        "entry_price": f"{price:.2f}",
        "target_price": f"{target:.2f}",
        "stop_loss": f"{stop:.2f}",
        "reward_ratio": round(ratio, 2),
        "timeframe": "جلسة اليوم",
        "setup": CLOSE_SETUP if closed else LIVE_SETUP,
        "reason": WATCH_REASON,
        "score": 60.0 if (row.get("net_flow") or 0) > 0 else 52.0,
        "entry_locked_at": None,
        "shariah_status": classified_status(symbol),
        "shariah_label": shariah_label(symbol),
    }


def _plan(price: float) -> tuple[float, float, float, float] | None:
    try:
        target, stop = long_trade_levels(price, min_reward=MIN_REWARD)
    except (TypeError, ValueError):
        target, stop = None, None
    if target is not None and stop is not None and is_valid_long_plan(price, target, stop):
        risk = price - float(stop)
        if risk > 0:
            ratio = (float(target) - price) / risk
            if ratio >= float(MIN_REWARD):
                return price, float(target), float(stop), ratio
    stop_price = round(price * 0.99, 2)
    if stop_price >= price:
        stop_price = round(price - 0.01, 2)
    risk = price - stop_price
    if risk <= 0:
        return None
    target_price = round(price + float(MIN_REWARD) * risk, 2)
    if not is_valid_long_plan(price, target_price, stop_price):
        return None
    return price, target_price, stop_price, (target_price - price) / risk


def _tape(feed: Any) -> list[dict[str, Any]]:
    if feed is None:
        return []
    for name in ("market_rows", "quote_tape"):
        loader = getattr(feed, name, None)
        if not callable(loader):
            continue
        try:
            rows = loader()
        except Exception:
            continue
        if isinstance(rows, list) and rows:
            return [row for row in rows if isinstance(row, dict)]
    return []


def _positive(value: Any) -> float | None:
    number = _number(value)
    return number if number is not None and number > 0 else None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number
