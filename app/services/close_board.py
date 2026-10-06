"""Close-session cards from prices already stored for the main market.

The strict end-of-day scan can be empty. These rows still show where the
session accumulated and where the value traded, using the stored print only.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.models.screener import is_tasi_main_symbol
from app.services.shariah import company_name_for, is_prohibited, sector_for
from app.services.signals import is_valid_long_plan, long_trade_levels

ACCUMULATION = "الأكثر تجميعاً"
LIQUIDITY = "الأكثر سيولة عند الإغلاق"
_LIMIT = 4


def close_session_board(quotes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priced: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in quotes:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").strip().upper()
        if symbol in seen or not is_tasi_main_symbol(symbol) or is_prohibited(symbol):
            continue
        price = _positive(item.get("last_price") or item.get("price") or item.get("close"))
        if price is None:
            continue
        flow = _number(item.get("net_flow")) or 0.0
        volume = _number(item.get("volume") or item.get("session_volume")) or 0.0
        value = _number(item.get("value_traded") or item.get("session_value")) or 0.0
        if value <= 0 and volume > 0:
            value = price * volume
        if value <= 0 and flow == 0:
            continue
        seen.add(symbol)
        priced.append(
            {
                "symbol": symbol,
                "name": _name(symbol, item.get("name")),
                "sector": str(item.get("sector") or sector_for(symbol) or ""),
                "price": price,
                "flow": flow,
                "value": value,
                "change": _number(item.get("change_percent") or item.get("price_change_pct")),
                "vwap": _positive(item.get("session_vwap") or item.get("vwap")),
            }
        )
    accumulated = [row for row in priced if row["flow"] > 0]
    accumulated.sort(key=lambda row: (row["flow"], row["value"]), reverse=True)
    liquid = sorted(priced, key=lambda row: (row["value"], row["flow"]), reverse=True)
    chosen: list[dict[str, Any]] = []
    used: set[str] = set()
    for row in accumulated[:_LIMIT]:
        published = _publish(row, ACCUMULATION, "bounce")
        if published is None:
            continue
        used.add(row["symbol"])
        chosen.append(published)
    for row in liquid:
        if row["symbol"] in used:
            continue
        published = _publish(row, LIQUIDITY, "momentum")
        if published is None:
            continue
        chosen.append(published)
        if sum(1 for item in chosen if item["signal_type"] == LIQUIDITY) >= _LIMIT:
            break
    return chosen


def _publish(row: dict[str, Any], label: str, kind: str) -> dict[str, Any] | None:
    price = float(row["price"])
    plan = _plan(price)
    if plan is None:
        return None
    entry, target, stop = plan
    change = row["change"]
    return {
        "symbol": row["symbol"],
        "name": row["name"],
        "close_price": round(price, 2),
        "last_price": round(price, 2),
        "signal_type": label,
        "signal_kind": kind,
        "confidence": "60%" if row["flow"] > 0 else "52%",
        "confidence_score": 60 if row["flow"] > 0 else 52,
        "entry_price": f"{entry:.2f}",
        "target_price": f"{target:.2f}",
        "stop_loss": f"{stop:.2f}",
        "reason": label,
        "volume_ratio": None,
        "mfi": None,
        "scan_mode": "end_of_day",
        "horizon": "close",
        "entry": False,
        "entry_rule": "close_session",
        "change_percent": None if change is None else round(float(change), 2),
        "session_vwap": row["vwap"],
        "net_flow": row["flow"],
    }


def _plan(price: float) -> tuple[float, float, float] | None:
    try:
        target, stop = long_trade_levels(price, min_reward=Decimal("1.5"))
    except (TypeError, ValueError):
        return None
    if not is_valid_long_plan(price, target, stop):
        return None
    return float(price), float(target), float(stop)


def _name(symbol: str, given: Any) -> str:
    listed = company_name_for(symbol)
    if listed and listed != symbol:
        return listed
    text = str(given or "").strip()
    if text and text != symbol and not text.isdigit():
        return text
    return listed or symbol


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
