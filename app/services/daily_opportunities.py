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
    "أسهم اقتربت من دعم، أو ارتدت من متوسط السيولة، أو اخترقت مقاومة اليوم، "
    "أو صعدت بتسارع خلال آخر 3 إلى 5 جلسات. هذه ليست قائمة أعلى سيولة."
)
CLOSE_HINT = "فرص الإغلاق التي بقيت قرب الدعم أو أكملت ارتداد الجلسة."
SETUP_SUPPORT = "ارتداد من دعم رئيسي"
SETUP_VWAP = "ارتداد من متوسط السيولة"
SETUP_BREAK = "اختراق مقاومة يومية"
SETUP_MOMENTUM = "زخم متراكم"
TIMEFRAME_MOMENTUM = "3–5 جلسات"
_NEAR_SUPPORT = 0.015
_MIN_CHANGE_3 = 8.0
_MIN_CHANGE_5 = 12.0
_VOLUME_SURGE = 1.5


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
    price = _positive(noted.get("last_price") or noted.get("price") or noted.get("close"))
    if price is None:
        return None
    momentum = multi_day_momentum(noted.get("recent_closes") or [], noted.get("recent_volumes") or [])
    setup = None if momentum is not None else rebound_setup(noted)
    if momentum is None and setup is None:
        return None
    bound = _bind_live_levels(price, price, None, None)
    if bound is None:
        return None
    entry, target, stop = bound
    if momentum is not None:
        return {
            "symbol": symbol,
            "name": _listed_name(symbol, noted.get("name")),
            "sector": noted.get("sector") or sector_for(symbol) or "",
            "last_price": price,
            "entry_price": entry,
            "target_price": target,
            "stop_loss": stop,
            "signal_kind": "momentum",
            "setup": SETUP_MOMENTUM,
            "reason": momentum["reason"],
            "score": momentum["score"],
            "timeframe": TIMEFRAME_MOMENTUM,
        }
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
        "timeframe": str(raw.get("timeframe") or TIMEFRAME),
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
    session_day = str(noted.get("session_date") or now_riyadh().date().isoformat())[:10]
    price = _positive(noted.get("last_price") or noted.get("price") or noted.get("close"))
    closes = []
    for bar in bars or []:
        if not isinstance(bar, dict):
            continue
        bar_day = str(bar.get("date") or bar.get("session_date") or "")[:10]
        close = _positive(bar.get("close"))
        if close is None or (len(bar_day) >= 10 and bar_day >= session_day):
            continue
        closes.append(close)
    recent = closes[-10:]
    if recent:
        if not _positive(noted.get("prior_low")):
            noted["prior_low"] = min(recent)
        if not _positive(noted.get("prior_high")):
            noted["prior_high"] = max(recent)
    noted["recent_closes"] = _momentum_closes(bars, session_day, price)
    noted["recent_volumes"] = _momentum_volumes(bars, session_day, noted)
    return noted


def multi_day_momentum(closes: list[float], volumes: list[float]) -> dict[str, Any] | None:
    """A measured 3-to-5 session rise, or a close that left the prior base, with volume when it exists."""

    prices = [value for value in (_positive(item) for item in closes) if value is not None]
    if len(prices) < 4:
        return None
    last = prices[-1]
    change_3 = _span_change(prices, 3)
    change_5 = _span_change(prices, 5) if len(prices) >= 6 else None
    window = 5 if change_5 is not None and change_5 >= _MIN_CHANGE_5 else 3
    change = change_5 if window == 5 else change_3
    if change is None:
        return None
    accelerated = change_3 is not None and change_3 >= _MIN_CHANGE_3
    if change_5 is not None and change_5 >= _MIN_CHANGE_5:
        accelerated = True
    base = prices[-8:-3] if len(prices) >= 8 else []
    left_base = bool(base) and last > max(base) and change_3 is not None and change_3 > 0
    surge = _volume_surge(volumes)
    if surge is False:
        return None
    if not accelerated and not (left_base and surge is True):
        return None
    if not accelerated and surge is None:
        return None
    parts = [f"صعود {change:.2f}% خلال {window} جلسات"]
    if surge is True:
        parts.append("مع ارتفاع حجم آخر 3 جلسات عن متوسط الجلسات السابقة")
    if left_base:
        parts.append("وخرج من نطاق التجميع السابق")
    score = min(99.0, 60.0 + max(change, 0.0))
    return {"reason": " ".join(parts), "score": round(score, 1), "change": round(change, 4), "sessions": window}


def _span_change(prices: list[float], sessions: int) -> float | None:
    if len(prices) < sessions + 1:
        return None
    start = prices[-(sessions + 1)]
    last = prices[-1]
    if start <= 0:
        return None
    return ((last - start) / start) * 100


def _volume_surge(volumes: list[float]) -> bool | None:
    """True when the last 3 sessions are at least 1.5× the sessions before them. None if volume was not measured."""

    amounts = []
    for item in volumes:
        number = _positive(item)
        if number is not None:
            amounts.append(number)
    if len(amounts) < 6:
        return None
    recent = amounts[-3:]
    earlier = amounts[-6:-3]
    baseline = sum(earlier) / len(earlier)
    if baseline <= 0:
        return None
    return (sum(recent) / len(recent)) / baseline >= _VOLUME_SURGE


def _momentum_closes(bars: list[dict[str, Any]] | None, session_day: str, price: float | None) -> list[float]:
    ordered: list[tuple[str, float]] = []
    for bar in bars or []:
        if not isinstance(bar, dict):
            continue
        day = str(bar.get("date") or bar.get("session_date") or "")[:10]
        close = _positive(bar.get("close"))
        if close is None or len(day) < 10:
            continue
        ordered.append((day, close))
    ordered.sort(key=lambda item: item[0])
    closes = [close for day, close in ordered if not session_day or day <= session_day]
    if price is not None and (not closes or not _near(closes[-1], price)):
        closes.append(price)
    return closes[-6:]


def _momentum_volumes(bars: list[dict[str, Any]] | None, session_day: str, row: dict[str, Any]) -> list[float]:
    ordered: list[tuple[str, float]] = []
    for bar in bars or []:
        if not isinstance(bar, dict):
            continue
        day = str(bar.get("date") or bar.get("session_date") or "")[:10]
        volume = _positive(bar.get("volume"))
        if volume is None or len(day) < 10:
            continue
        if session_day and day > session_day:
            continue
        ordered.append((day, volume))
    ordered.sort(key=lambda item: item[0])
    volumes = [volume for _, volume in ordered]
    current = _positive(row.get("session_volume") or row.get("volume"))
    if current is not None and ordered and session_day and ordered[-1][0] == session_day:
        volumes[-1] = current
    elif current is not None:
        volumes.append(current)
    return volumes[-6:]


def _near(left: float, right: float) -> bool:
    return abs(left - right) <= max(right * 0.0001, 0.0001)


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
