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


def consensus_payload(
    *,
    today: date | None = None,
    pure_only: bool = False,
    last_prices: Mapping[str, Any] | None = None,
    store: EntrySnapshotStore | None = None,
) -> dict[str, Any]:
    cutoff = today or now_riyadh().date()
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
