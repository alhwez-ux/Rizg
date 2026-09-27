"""Intraday Rizg setups: locked entry, long geometry, and at least 1:2 reward."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from app.models.screener import is_tasi_main_symbol
from app.services.entry_snapshot_store import EntrySnapshotStore, apply_locked_entries
from app.services.analyst_consensus import scale_long_plan
from app.services.shariah import classified_status, company_name_for, is_prohibited, is_pure, sector_for, shariah_label
from app.services.signals import is_valid_long_plan, keep_long_recommendations, long_trade_levels
from app.services.smart_money import KIND_ACCUMULATION, scan_smart_money
from app.services.tasi_clock import now_riyadh, phase_label, session_phase

SCAN_MODE = "intraday"
MIN_REWARD = Decimal("2")
TIMEFRAME = "جلسة اليوم"
_DEFAULT_STORE = EntrySnapshotStore(Path("data/intraday_entry_snapshots.json"))

HINT = (
    "فرص يومية بشرط الهدف فوق الدخول فوق الوقف، ومكافأة لا تقل عن 1:2. "
    "يُقفل الدخول على آخر سعر لحظة الإشارة، ثم يُحسب الهدف والوقف من ذلك الدخول."
)


def scan_daily_opportunities(
    feed: Any = None,
    *,
    snapshots: list[dict[str, Any]] | None = None,
    recommendations: list[dict[str, Any]] | None = None,
    store: EntrySnapshotStore | None = None,
    moment: Any = None,
    pure_only: bool = False,
    source: str = "TickChart",
) -> dict[str, Any]:
    current = now_riyadh(moment)
    phase = session_phase(current)
    book = store or _DEFAULT_STORE
    day = current.date().isoformat() if isinstance(current, datetime) else now_riyadh().date().isoformat()
    candidates = _candidates(feed, snapshots=snapshots, recommendations=recommendations)
    locked = apply_locked_entries(
        candidates,
        store=book,
        scan_mode=SCAN_MODE,
        session_date=day,
    )
    rows: list[dict[str, Any]] = []
    for raw in locked:
        published = _publish(raw, pure_only=pure_only)
        if published is not None:
            rows.append(published)
    rows.sort(key=lambda row: (-float(row["reward_ratio"]), -float(row["score"]), row["symbol"]))
    scanned = current if isinstance(current, datetime) else now_riyadh()
    return {
        "success": True,
        "session_phase": phase,
        "session_label": phase_label(phase),
        "source": source,
        "count": len(rows),
        "min_reward_ratio": float(MIN_REWARD),
        "hint": HINT,
        "scanned_at": scanned.isoformat(),
        "data": rows,
    }


def _candidates(
    feed: Any,
    *,
    snapshots: list[dict[str, Any]] | None,
    recommendations: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    money = scan_smart_money(feed, snapshots=snapshots)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in money.get("data") or []:
        if item.get("signal_kind") != KIND_ACCUMULATION or not item.get("plan_ok"):
            continue
        shaped = _from_smart_money(item)
        if shaped is None or shaped["symbol"] in seen:
            continue
        seen.add(shaped["symbol"])
        rows.append(shaped)
    for item in keep_long_recommendations(recommendations):
        shaped = _from_recommendation(item)
        if shaped is None or shaped["symbol"] in seen:
            continue
        seen.add(shaped["symbol"])
        rows.append(shaped)
    return rows


def _from_smart_money(item: dict[str, Any]) -> dict[str, Any] | None:
    symbol = str(item.get("symbol") or "").strip().upper()
    if not _tradable(symbol):
        return None
    bound = _bind_live_levels(item.get("last_price"), item.get("entry"), item.get("target"), item.get("stop"))
    if bound is None:
        return None
    entry, target, stop = bound
    return {
        "symbol": symbol,
        "name": item.get("name") or company_name_for(symbol) or symbol,
        "sector": item.get("sector") or sector_for(symbol) or "",
        "last_price": entry,
        "entry_price": entry,
        "target_price": target,
        "stop_loss": stop,
        "signal_kind": "intraday",
        "setup": "تجميع مؤسسي يومي",
        "reason": item.get("reason") or "",
        "score": item.get("score") or item.get("institutional_flow_score") or 0,
    }


def _from_recommendation(item: dict[str, Any]) -> dict[str, Any] | None:
    symbol = str(item.get("symbol") or "").strip().upper()
    if not _tradable(symbol):
        return None
    live = item.get("last_price") or item.get("close_price") or item.get("entry_price")
    bound = _bind_live_levels(live, item.get("entry_price"), item.get("target_price"), item.get("stop_loss"))
    if bound is None:
        return None
    entry, target, stop = bound
    return {
        "symbol": symbol,
        "name": item.get("name") or company_name_for(symbol) or symbol,
        "sector": item.get("sector") or sector_for(symbol) or "",
        "last_price": entry,
        "entry_price": entry,
        "target_price": target,
        "stop_loss": stop,
        "signal_kind": str(item.get("signal_kind") or "momentum"),
        "setup": str(item.get("signal_type") or "فرصة يومية"),
        "reason": item.get("reason") or "",
        "score": item.get("confidence_score") or 0,
    }


def _publish(raw: dict[str, Any], *, pure_only: bool) -> dict[str, Any] | None:
    symbol = str(raw.get("symbol") or "").strip().upper()
    if not _tradable(symbol):
        return None
    status = classified_status(symbol)
    if pure_only and not is_pure(symbol):
        return None
    geometry = _ensure_two_r(raw.get("entry_price"), raw.get("target_price"), raw.get("stop_loss"))
    if geometry is None:
        return None
    entry, target, stop, ratio = geometry
    last = _positive(raw.get("last_price"))
    return {
        "symbol": symbol,
        "name": str(raw.get("name") or company_name_for(symbol) or symbol),
        "sector": str(raw.get("sector") or sector_for(symbol) or ""),
        "last_price": last,
        "entry_price": f"{entry:.2f}",
        "target_price": f"{target:.2f}",
        "stop_loss": f"{stop:.2f}",
        "reward_ratio": round(ratio, 2),
        "timeframe": TIMEFRAME,
        "setup": str(raw.get("setup") or "فرصة يومية"),
        "reason": str(raw.get("reason") or ""),
        "score": float(raw.get("score") or 0),
        "entry_locked_at": raw.get("entry_locked_at"),
        "shariah_status": status,
        "shariah_label": shariah_label(symbol),
    }


def _bind_live_levels(last: Any, template_entry: Any, template_target: Any, template_stop: Any) -> tuple[float, float, float] | None:
    """Anchor a long plan on the live print. Later locks must not replace this entry."""

    live = _positive(last)
    if live is None:
        return None
    scaled = scale_long_plan(template_entry, template_target, template_stop, live)
    if scaled is not None:
        entry, target, stop = scaled
        return float(entry), float(target), float(stop)
    try:
        target, stop = long_trade_levels(live, min_reward=MIN_REWARD)
    except ValueError:
        return None
    if not is_valid_long_plan(live, target, stop):
        return None
    return float(live), float(target), float(stop)


def _ensure_two_r(entry: Any, target: Any, stop: Any) -> tuple[float, float, float, float] | None:
    """Keep the locked entry and stop. Extend the target until reward is at least 1:2.

    Prices are rounded in Decimal space so a float like 1.999999 does not fail the 2R gate.
    """

    if not is_valid_long_plan(entry, target, stop):
        return None
    price = _money(entry, ROUND_HALF_UP)
    stop_price = _money(stop, ROUND_HALF_UP)
    target_price = _money(target, ROUND_HALF_UP)
    if price is None or stop_price is None or target_price is None:
        return None
    if not (target_price > price > stop_price > 0):
        return None
    risk = price - stop_price
    if risk <= 0:
        return None
    ratio = (target_price - price) / risk
    if ratio < MIN_REWARD:
        target_price = (price + MIN_REWARD * risk).quantize(Decimal("0.01"), rounding=ROUND_CEILING)
        ratio = (target_price - price) / risk
    if ratio < MIN_REWARD or not (target_price > price > stop_price > 0):
        return None
    if not is_valid_long_plan(price, target_price, stop_price):
        return None
    return float(price), float(target_price), float(stop_price), float(ratio)


def _money(value: Any, rounding) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except (ArithmeticError, TypeError, ValueError):
        return None
    if not number.is_finite() or number <= 0:
        return None
    return number.quantize(Decimal("0.01"), rounding=rounding)


def _tradable(symbol: str) -> bool:
    return bool(symbol) and is_tasi_main_symbol(symbol) and not is_prohibited(symbol)


def _positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number <= 0:
        return None
    return number
