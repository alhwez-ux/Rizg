"""Intraday Rizg setups: locked entry, long geometry, and at least 1:1.5 reward."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from app.models.screener import is_tasi_main_symbol
from app.services.entry_snapshot_store import EntrySnapshotStore, apply_locked_entries
from app.services.analyst_consensus import scale_long_plan
from app.services.shariah import classified_status, company_name_for, is_prohibited, is_pure, sector_for, shariah_label
from app.services.signals import is_valid_long_plan, long_trade_levels
from app.services.tasi_clock import now_riyadh, phase_label, session_phase

SCAN_MODE = "intraday"
MIN_REWARD = Decimal("1.5")
TIMEFRAME = "جلسة اليوم"
_DEFAULT_STORE = EntrySnapshotStore(Path("data/intraday_entry_snapshots.json"))

HINT = (
    "أسهم اقتربت من دعم رئيسي، أو ارتدت من متوسط السيولة، أو اخترقت مقاومة اليوم. "
    "هذه ليست قائمة أعلى سيولة."
)
CLOSE_HINT = "فرص الإغلاق التي بقيت قرب الدعم أو أكملت ارتداد الجلسة."
SETUP_SUPPORT = "ارتداد من دعم رئيسي"
SETUP_VWAP = "ارتداد من متوسط السيولة"
SETUP_BREAK = "اختراق مقاومة يومية"
_NEAR_SUPPORT = 0.015


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
    rows.sort(key=lambda row: (-float(row["score"]), -float(row["reward_ratio"]), row["symbol"]))
    scanned = current if isinstance(current, datetime) else now_riyadh()
    closed = phase in {"closed", "weekend", "auction"}
    return {
        "success": True,
        "session_phase": phase,
        "session_label": phase_label(phase),
        "source": source,
        "count": len(rows),
        "min_reward_ratio": float(MIN_REWARD),
        "hint": CLOSE_HINT if closed and rows else HINT,
        "scanned_at": scanned.isoformat(),
        "data": rows,
    }


def _candidates(
    feed: Any,
    *,
    snapshots: list[dict[str, Any]] | None,
    recommendations: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    del recommendations
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in list(snapshots or []) + _tape(feed):
        if not isinstance(item, dict):
            continue
        shaped = _from_rebound(feed, item)
        if shaped is None or shaped["symbol"] in seen:
            continue
        seen.add(shaped["symbol"])
        rows.append(shaped)
    return rows


def _from_rebound(feed: Any, item: dict[str, Any]) -> dict[str, Any] | None:
    symbol = str(item.get("symbol") or "").strip().upper()
    if not _tradable(symbol):
        return None
    noted = _with_prior_closes(feed, item)
    setup = rebound_setup(noted)
    if setup is None:
        return None
    price = _positive(noted.get("last_price") or noted.get("price") or noted.get("close"))
    if price is None:
        return None
    bound = _bind_live_levels(price, price, None, None)
    if bound is None:
        return None
    entry, target, stop = bound
    return {
        "symbol": symbol,
        "name": _listed_name(symbol, noted.get("name")),
        "sector": noted.get("sector") or sector_for(symbol) or "",
        "last_price": price,
        "entry_price": entry,
        "target_price": target,
        "stop_loss": stop,
        "signal_kind": "bounce" if setup != SETUP_BREAK else "momentum",
        "setup": setup,
        "reason": setup,
        "score": _rebound_score(noted, setup),
    }


def rebound_setup(row: dict[str, Any]) -> str | None:
    """Support, a real VWAP reclaim, or a break of the prior close ceiling."""

    price = _positive(row.get("last_price") or row.get("price") or row.get("close"))
    if price is None:
        return None
    low = _positive(row.get("session_low") or row.get("low"))
    vwap = _positive(row.get("session_vwap") or row.get("vwap"))
    floors = [
        value
        for value in (
            low,
            _positive(row.get("support")),
            _positive(row.get("prior_low")),
        )
        if value is not None and value < price
    ]
    if floors:
        base = max(floors)
        if base > 0 and (price - base) / base <= _NEAR_SUPPORT:
            return SETUP_SUPPORT
    if vwap is not None and low is not None and low < vwap <= price:
        return SETUP_VWAP
    prior_high = _positive(row.get("prior_high") or row.get("resistance"))
    if prior_high is not None and price > prior_high:
        return SETUP_BREAK
    return None


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
        "name": _listed_name(symbol, raw.get("name")),
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


def _with_prior_closes(feed: Any, row: dict[str, Any]) -> dict[str, Any]:
    noted = dict(row)
    if _positive(noted.get("prior_low")) and _positive(noted.get("prior_high")):
        return noted
    symbol = str(noted.get("symbol") or "").strip().upper()
    quotes = getattr(feed, "_quotes", None)
    history = getattr(quotes, "close_history", None)
    if not symbol or not callable(history):
        return noted
    try:
        bars = history(symbol)
    except Exception:
        return noted
    closes = [_positive(bar.get("close")) for bar in bars or [] if isinstance(bar, dict)]
    closes = [price for price in closes if price is not None]
    recent = closes[-10:]
    if not recent:
        return noted
    if not _positive(noted.get("prior_low")):
        noted["prior_low"] = min(recent)
    if not _positive(noted.get("prior_high")):
        noted["prior_high"] = max(recent)
    return noted


def _rebound_score(row: dict[str, Any], setup: str) -> float:
    price = _positive(row.get("last_price") or row.get("price")) or 0.0
    low = _positive(row.get("session_low") or row.get("low") or row.get("support") or row.get("prior_low"))
    if setup == SETUP_SUPPORT and price and low and price > low:
        return round(100.0 - min(((price - low) / low) * 1000.0, 40.0), 1)
    if setup == SETUP_VWAP:
        return 80.0
    if setup == SETUP_BREAK:
        return 70.0
    return 50.0


def _ensure_two_r(entry: Any, target: Any, stop: Any) -> tuple[float, float, float, float] | None:
    """Keep the locked entry and stop. Extend the target until reward is at least 1:1.5.

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


def _listed_name(symbol: str, given: Any) -> str:
    listed = company_name_for(symbol)
    if listed and listed != symbol:
        return listed
    text = str(given or "").strip()
    if text and text != symbol:
        return text
    return listed or symbol


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
