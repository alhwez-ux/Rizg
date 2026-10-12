"""Curated analyst-house book. Only valid long plans inside their horizon are shown."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Mapping

from app.models.screener import is_tasi_main_symbol
from app.services.entry_snapshot_store import EntrySnapshotStore
from app.services.institutional_strategy import reward_ratio
from app.services.shariah import classified_status, company_name_for, is_prohibited, is_pure, sector_for, shariah_label
from app.services.signals import is_valid_long_plan
from app.services.tasi_clock import now_riyadh

_BOOK_PATH = Path(__file__).resolve().parents[1] / "data" / "analyst_consensus.json"
_HINT = (
    "سجل بيوت الخبرة المُراجع داخل رزق. يُقفل الدخول على آخر سعر لحظة ظهور الإشارة، "
    "ويُحسب الهدف والوقف من ذلك الدخول بحيث يبقى الهدف أعلى من الدخول والوقف تحته."
)
_STORE: EntrySnapshotStore | None = None


def default_analyst_store() -> EntrySnapshotStore:
    global _STORE
    if _STORE is None:
        _STORE = EntrySnapshotStore(Path("data/analyst_entry_snapshots.json"))
    return _STORE


def scale_long_plan(
    template_entry: Any,
    template_target: Any,
    template_stop: Any,
    live_entry: Any,
) -> tuple[Decimal, Decimal, Decimal] | None:
    """Keep the template's risk and reward distances, anchored on the live entry."""

    if not is_valid_long_plan(template_entry, template_target, template_stop):
        return None
    try:
        live = Decimal(str(live_entry))
        base = Decimal(str(template_entry))
        template_target_price = Decimal(str(template_target))
        template_stop_price = Decimal(str(template_stop))
    except (ArithmeticError, TypeError, ValueError):
        return None
    if live <= 0 or base <= 0:
        return None
    risk_pct = (base - template_stop_price) / base
    reward_pct = (template_target_price - base) / base
    if risk_pct <= 0 or reward_pct <= 0:
        return None
    entry = live.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    stop = (entry * (Decimal("1") - risk_pct)).quantize(Decimal("0.01"), rounding=ROUND_FLOOR)
    target = (entry * (Decimal("1") + reward_pct)).quantize(Decimal("0.01"), rounding=ROUND_CEILING)
    if stop >= entry:
        stop = entry - Decimal("0.01")
    if target <= entry:
        target = entry + Decimal("0.01")
    if not is_valid_long_plan(entry, target, stop):
        return None
    return entry, target, stop


def active_consensus(
    *,
    today: date | None = None,
    pure_only: bool = False,
    book: list[dict[str, Any]] | None = None,
    last_prices: Mapping[str, Any] | None = None,
    store: EntrySnapshotStore | None = None,
) -> list[dict[str, Any]]:
    cutoff = today or now_riyadh().date()
    prices = {str(symbol).strip().upper(): value for symbol, value in (last_prices or {}).items()}
    rows: list[dict[str, Any]] = []
    for item in book if book is not None else load_consensus_book():
        symbol = str(item.get("symbol") or "").strip().upper()
        published = _publish(
            item,
            cutoff=cutoff,
            pure_only=pure_only,
            live=prices.get(symbol),
            store=store,
        )
        if published is not None:
            rows.append(published)
    rows.sort(key=lambda row: (str(row["valid_until"]), -float(row["reward_ratio"]), row["symbol"]))
    return rows


def rolling_consensus(
    *,
    today: date | None = None,
    window_days: int = 5,
    pure_only: bool = False,
    book: list[dict[str, Any]] | None = None,
    last_prices: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Buy plans published inside the rolling window, ranked by recorded house agreement.

    A pick with no publish date stays out. Entry, target, and stop stay the report
    figures. The live price is shown beside them and does not move those levels.
    """

    cutoff = today or now_riyadh().date()
    span = max(1, min(int(window_days), 30))
    start = cutoff.fromordinal(cutoff.toordinal() - (span - 1))
    prices = {str(symbol).strip().upper(): value for symbol, value in (last_prices or {}).items()}
    grouped: dict[str, dict[str, Any]] = {}
    for item in book if book is not None else load_consensus_book():
        if not isinstance(item, dict):
            continue
        published = _publish_report(item, start=start, cutoff=cutoff, pure_only=pure_only)
        if published is None:
            continue
        symbol = published["symbol"]
        bucket = grouped.setdefault(symbol, {"plans": [], "houses": {}})
        for plan in published["plans"]:
            house = plan["house"]
            previous = bucket["houses"].get(house)
            if previous is None or plan["published_on"] >= previous["published_on"]:
                bucket["houses"][house] = plan
    rows: list[dict[str, Any]] = []
    for symbol, bucket in grouped.items():
        plans = list(bucket["houses"].values())
        if not plans:
            continue
        rows.append(_consensus_row(symbol, plans, live=_positive(prices.get(symbol)), window_days=span))
    rows.sort(key=lambda row: (-float(row["consensus_strength"]), -int(row["analyst_count"]), row["symbol"]))
    return rows


def _publish_report(
    item: dict[str, Any],
    *,
    start: date,
    cutoff: date,
    pure_only: bool,
) -> dict[str, Any] | None:
    symbol = str(item.get("symbol") or "").strip().upper()
    if not symbol or not is_tasi_main_symbol(symbol) or is_prohibited(symbol):
        return None
    if pure_only and not is_pure(symbol):
        return None
    stance = str(item.get("stance") or "buy").strip().lower()
    if stance not in {"buy", "entry"}:
        return None
    published = _as_date(item.get("published_on"))
    if published is None or published < start or published > cutoff:
        return None
    if not is_valid_long_plan(item.get("entry_price"), item.get("target_price"), item.get("stop_loss")):
        return None
    houses = [str(name).strip() for name in (item.get("houses") or []) if str(name).strip()]
    if not houses:
        return None
    try:
        weight = float(item.get("weight") if item.get("weight") is not None else 1)
    except (TypeError, ValueError):
        weight = 1.0
    if weight <= 0:
        weight = 1.0
    entry = Decimal(str(item["entry_price"]))
    target = Decimal(str(item["target_price"]))
    stop = Decimal(str(item["stop_loss"]))
    plans = [
        {
            "house": house,
            "published_on": published.isoformat(),
            "weight": weight,
            "entry": entry,
            "target": target,
            "stop": stop,
            "note": str(item.get("note") or "").strip(),
        }
        for house in houses
    ]
    return {"symbol": symbol, "plans": plans}


def _consensus_row(symbol: str, plans: list[dict[str, Any]], *, live: float | None, window_days: int) -> dict[str, Any]:
    entries = [plan["entry"] for plan in plans]
    targets = [plan["target"] for plan in plans]
    stops = [plan["stop"] for plan in plans]
    entry_low, entry_high = min(entries), max(entries)
    target_low, target_high = min(targets), max(targets)
    stop_low, stop_high = min(stops), max(stops)
    strength = sum(float(plan["weight"]) for plan in plans)
    latest = max(str(plan["published_on"]) for plan in plans)
    ratio = reward_ratio(entry_low, target_high, stop_low)
    status = classified_status(symbol)
    notes = [str(plan["note"]) for plan in plans if plan.get("note")]
    return {
        "symbol": symbol,
        "name": company_name_for(symbol) or symbol,
        "sector": sector_for(symbol) or "",
        "houses": [str(plan["house"]) for plan in plans],
        "analyst_count": len(plans),
        "consensus_strength": round(strength, 2),
        "published_on": latest,
        "window_days": window_days,
        "last_price": None if live is None else round(live, 2),
        "entry_price": f"{entry_low:.2f}",
        "entry_low": f"{entry_low:.2f}",
        "entry_high": f"{entry_high:.2f}",
        "target_price": f"{target_high:.2f}",
        "target_low": f"{target_low:.2f}",
        "target_high": f"{target_high:.2f}",
        "stop_loss": f"{stop_low:.2f}",
        "stop_low": f"{stop_low:.2f}",
        "stop_high": f"{stop_high:.2f}",
        "reward_ratio": 0 if ratio is None else round(float(ratio), 2),
        "timeframe": f"{window_days} أيام",
        "valid_until": latest,
        "note": notes[0] if notes else "",
        "entry_locked_at": None,
        "shariah_status": status,
        "shariah_label": shariah_label(symbol),
    }


def consensus_payload(
    *,
    today: date | None = None,
    pure_only: bool = False,
    last_prices: Mapping[str, Any] | None = None,
    store: EntrySnapshotStore | None = None,
    window_days: int | None = None,
) -> dict[str, Any]:
    cutoff = today or now_riyadh().date()
    if window_days is not None:
        span = max(1, min(int(window_days), 30))
        rows = rolling_consensus(
            today=cutoff,
            window_days=span,
            pure_only=pure_only,
            last_prices=last_prices,
        )
        return {
            "success": True,
            "source": "curated",
            "count": len(rows),
            "as_of": cutoff.isoformat(),
            "window_days": span,
            "hint": (
                f"توصيات شراء مؤرخة خلال آخر {span} أيام. الترتيب بعدد بيوت الخبرة وثقل التوصية المسجّل. "
                "الدخول والهدف والوقف أرقام التقارير، والسعر الحالي من التسعير الحي إن وُجد."
            ),
            "data": rows,
        }
    rows = active_consensus(
        today=cutoff,
        pure_only=pure_only,
        last_prices=last_prices,
        store=store or default_analyst_store(),
    )
    return {
        "success": True,
        "source": "curated",
        "count": len(rows),
        "as_of": cutoff.isoformat(),
        "hint": _HINT,
        "data": rows,
    }


def load_consensus_book() -> list[dict[str, Any]]:
    if not _BOOK_PATH.exists():
        return []
    try:
        payload = json.loads(_BOOK_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get("picks", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def collect_last_prices(feed: Any) -> dict[str, float]:
    """Live prints from the feed. A quote book on disk is used only when the feed has none."""

    prices: dict[str, float] = {}
    raw = getattr(feed, "last_prices", None)
    if isinstance(raw, dict):
        for symbol, value in raw.items():
            number = _positive(value)
            if number is not None:
                prices[str(symbol).strip().upper()] = number
    quotes = getattr(feed, "_quotes", None)
    snapshot = quotes.snapshot() if quotes is not None and hasattr(quotes, "snapshot") else []
    for row in snapshot or []:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        number = _positive(row.get("last_price") or row.get("price") or row.get("close"))
        if symbol and number is not None:
            prices[symbol] = number
    if prices:
        return prices
    try:
        from app.services.last_quotes import LastQuoteBook

        for row in LastQuoteBook().snapshot():
            symbol = str(row.get("symbol") or "").strip().upper()
            number = _positive(row.get("last_price"))
            if symbol and number is not None:
                prices[symbol] = number
    except Exception:
        return prices
    return prices


def _publish(
    item: dict[str, Any],
    *,
    cutoff: date,
    pure_only: bool,
    live: Any,
    store: EntrySnapshotStore | None,
) -> dict[str, Any] | None:
    symbol = str(item.get("symbol") or "").strip().upper()
    if not symbol or not is_tasi_main_symbol(symbol) or is_prohibited(symbol):
        return None
    if pure_only and not is_pure(symbol):
        return None
    horizon = _as_date(item.get("valid_until") or item.get("expires_on"))
    if horizon is None or horizon < cutoff:
        return None
    live_price = _positive(live)
    if live_price is None:
        return None
    scaled = scale_long_plan(item.get("entry_price"), item.get("target_price"), item.get("stop_loss"), live_price)
    if scaled is None:
        return None
    entry, target, stop = scaled
    locked_at = None
    if store is not None:
        locked = store.lock(
            symbol=symbol,
            scan_mode="analyst",
            session_date=horizon.isoformat(),
            entry_price=entry,
            target_price=target,
            stop_loss=stop,
            signal_kind="analyst",
        )
        if locked is None:
            return None
        entry = Decimal(str(locked["entry_price"]))
        target = Decimal(str(locked["target_price"]))
        stop = Decimal(str(locked["stop_loss"]))
        locked_at = locked.get("triggered_at")
    if not is_valid_long_plan(entry, target, stop):
        return None
    ratio = reward_ratio(entry, target, stop)
    if ratio is None:
        return None
    houses = [str(name).strip() for name in (item.get("houses") or []) if str(name).strip()]
    if not houses:
        return None
    status = classified_status(symbol)
    return {
        "symbol": symbol,
        "name": str(item.get("name") or company_name_for(symbol) or symbol),
        "sector": str(item.get("sector") or sector_for(symbol) or ""),
        "houses": houses,
        "last_price": round(live_price, 2),
        "entry_price": f"{entry:.2f}",
        "target_price": f"{target:.2f}",
        "stop_loss": f"{stop:.2f}",
        "reward_ratio": round(float(ratio), 2),
        "timeframe": str(item.get("timeframe") or "").strip() or "غير محدد",
        "valid_until": horizon.isoformat(),
        "note": str(item.get("note") or "").strip(),
        "entry_locked_at": locked_at,
        "shariah_status": status,
        "shariah_label": shariah_label(symbol),
    }


def _positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number <= 0:
        return None
    return number


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()[:10]
    if len(text) < 10:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None
