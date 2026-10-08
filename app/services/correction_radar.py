"""Correction radar from measured session bars and the live institutional tape.

A pillar counts only when its inputs are present. Missing flow, blocks, MFI,
VWAP, or volume stays silent. Two measured pillars are required, and a symbol
that qualifies for both alerts at once is left off the board.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models.screener import is_tasi_main_symbol
from app.services.shariah import company_name_for, is_prohibited, sector_for
from app.services.tasi_clock import now_riyadh, phase_label, session_phase

KIND_APPROACH = "approach"
KIND_REBOUND = "rebound"

SIGNAL_APPROACH = "⚠️ اقتراب تصحيحي (تصريف مؤسسي خفي)"
SIGNAL_REBOUND = "🟢 انتهاء التصحيح (منطقة تجميع مؤسسي / فرصة ارتداد)"

REASON_VOLUME = "حجم متناقص على 3 جلسات صاعدة"
REASON_FLOW = "صافي تدفق مؤسسي سلبي"
REASON_SELL_BLOCKS = "كتل بيعية مؤكدة"
REASON_RESISTANCE = "السعر عند أعلى إغلاق يومي حديث"
REASON_MFI = "مؤشر السيولة المؤسسية ضعيف والسعر صاعد"
REASON_SUPPORT = "السعر عند أدنى إغلاق يومي حديث"
REASON_ATR = "ملامسة الحد السفلي لتذبذب الإغلاق"
REASON_VWAP = "ارتداد من متوسط الجلسة"
REASON_BUY_BLOCKS = "كتل شرائية عند مستويات منخفضة"
REASON_SURGE = "حجم أعلى من متوسط 10 جلسات وإغلاق إيجابي"

HINT = (
    "يظهر السهم عند اجتماع شرطين مقاسين على الأقل من الحجم أو التدفق أو الكتل أو موقع السعر. "
    "غياب تدفق أو كتلة أو مؤشر سيولة يُبقي ذلك الشرط صامتاً. التنبيه قراءة استباقية وليس دخولاً مؤكداً."
)

_TOUCH = 0.015
_VWAP_RECLAIM = 0.012
_SURGE = 1.5
_PRINT_VOLUME = 10_000.0
_PRINT_MEDIAN = 100_000.0
_RANGE_SESSIONS = 20
_MIN_RANGE = 8
_MFI_WEAK = 40.0


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


def _day_key(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return str(value.isoformat())[:10]
    return str(value or "")[:10]


def _bars(history: Any) -> list[tuple[str, float, float]]:
    """Dated close and volume. A print-sized volume beside real sessions is dropped."""

    raw: list[tuple[str, float, float]] = []
    if not isinstance(history, list):
        return []
    for item in history:
        if not isinstance(item, dict):
            continue
        close = _positive(item.get("close") or item.get("last_price"))
        volume = _positive(item.get("volume"))
        if close is None or volume is None:
            continue
        raw.append((_day_key(item.get("date")), close, volume))
    if not raw:
        return []
    raw.sort(key=lambda row: row[0])
    volumes = [row[2] for row in raw]
    raw = [row for row in raw if not _is_print_volume(row[2], volumes)]
    merged: list[tuple[str, float, float]] = []
    for row in raw:
        if merged and row[0] and merged[-1][0] == row[0]:
            merged[-1] = row
        else:
            merged.append(row)
    return merged


def _is_print_volume(volume: float, peers: list[float]) -> bool:
    if not peers:
        return False
    ordered = sorted(peers)
    median = ordered[len(ordered) // 2]
    return median >= _PRINT_MEDIAN and volume < _PRINT_VOLUME


def _near(price: float, level: float, band: float = _TOUCH) -> bool:
    if price <= 0 or level <= 0:
        return False
    return abs(price - level) / level <= band


def _block(snapshot: dict[str, Any], side: str) -> bool:
    trades = int(_num(snapshot.get("block_trades")) or 0)
    volume = _positive(snapshot.get("block_volume") or snapshot.get("last_block_value"))
    return trades >= 1 and volume is not None and snapshot.get("block_side") == side


def _institutional_net(snapshot: dict[str, Any]) -> float | None:
    """Net institutional riyals from the tape. A stored quote net is not a substitute."""

    if "institutional_inflow" not in snapshot and "institutional_outflow" not in snapshot:
        return None
    inflow = _num(snapshot.get("institutional_inflow"))
    outflow = _num(snapshot.get("institutional_outflow"))
    if inflow is None or outflow is None:
        return None
    if inflow < 0 or outflow < 0 or inflow + outflow <= 0:
        return None
    return inflow - outflow


def _measured_mfi(snapshot: dict[str, Any]) -> float | None:
    if snapshot.get("institutional_mfi") is None:
        return None
    mfi = _num(snapshot.get("institutional_mfi"))
    if mfi is None or mfi < 0 or mfi > 100:
        return None
    return mfi


def _close_atr_lower(closes: list[float]) -> float | None:
    if len(closes) < 11:
        return None
    window = closes[-11:]
    changes = [abs(window[index] - window[index - 1]) for index in range(1, len(window))]
    if len(changes) < 10 or sum(changes) <= 0:
        return None
    atr = sum(changes) / len(changes)
    if atr <= 0:
        return None
    mid = sum(window[-10:]) / 10.0
    lower = mid - atr
    return lower if lower > 0 else None


def _approach(snapshot: dict[str, Any], bars: list[tuple[str, float, float]], price: float) -> tuple[int, list[str]]:
    reasons: list[str] = []
    pillars = 0
    if len(bars) >= 4:
        closes = [row[1] for row in bars[-4:]]
        volumes = [row[2] for row in bars[-3:]]
        rising = closes[1] > closes[0] and closes[2] > closes[1] and closes[3] > closes[2]
        fading = volumes[0] > volumes[1] > volumes[2]
        if rising and fading:
            pillars += 1
            reasons.append(REASON_VOLUME)

    flow_reasons: list[str] = []
    net = _institutional_net(snapshot)
    if net is not None and net < 0:
        flow_reasons.append(REASON_FLOW)
    if _block(snapshot, "sell"):
        flow_reasons.append(REASON_SELL_BLOCKS)
    if flow_reasons:
        pillars += 1
        reasons.extend(flow_reasons)

    location: list[str] = []
    prior = [row[1] for row in bars[:-1]][-_RANGE_SESSIONS:]
    if len(prior) >= _MIN_RANGE:
        resistance = max(prior)
        if price <= resistance * (1 + _TOUCH) and _near(price, resistance):
            location.append(REASON_RESISTANCE)
    mfi = _measured_mfi(snapshot)
    previous = bars[-2][1] if len(bars) >= 2 else None
    if mfi is not None and mfi <= _MFI_WEAK and previous is not None and price > previous:
        location.append(REASON_MFI)
    if location:
        pillars += 1
        reasons.extend(location)
    return pillars, reasons


def _rebound(snapshot: dict[str, Any], bars: list[tuple[str, float, float]], price: float) -> tuple[int, list[str]]:
    reasons: list[str] = []
    pillars = 0
    prior = [row[1] for row in bars[:-1]][-_RANGE_SESSIONS:]
    at_support = False
    if len(prior) >= _MIN_RANGE:
        support = min(prior)
        at_support = price >= support * (1 - _TOUCH) and _near(price, support)
    closes = [row[1] for row in bars]
    lower = _close_atr_lower(closes)
    at_atr = lower is not None and _near(price, lower) and price <= (sum(closes[-10:]) / 10.0)
    vwap = _positive(snapshot.get("session_vwap") or snapshot.get("vwap"))
    session_low = _positive(snapshot.get("session_low"))
    at_vwap = False
    if vwap is not None and session_low is not None and session_low < vwap and price >= vwap:
        at_vwap = (price - vwap) / vwap <= _VWAP_RECLAIM
    location: list[str] = []
    if at_support:
        location.append(REASON_SUPPORT)
    if at_atr:
        location.append(REASON_ATR)
    if at_vwap:
        location.append(REASON_VWAP)
    if location:
        pillars += 1
        reasons.extend(location)

    low_zone = at_support or at_atr or (vwap is not None and price <= vwap)
    if not low_zone and len(prior) >= _MIN_RANGE:
        ordered = sorted(prior)
        low_zone = price <= ordered[max(0, len(ordered) // 4)]
    if _block(snapshot, "buy") and low_zone:
        pillars += 1
        reasons.append(REASON_BUY_BLOCKS)

    if len(bars) >= 11:
        prior_volumes = [row[2] for row in bars[-11:-1]]
        today_volume = bars[-1][2]
        previous_close = bars[-2][1]
        if len(prior_volumes) == 10 and all(volume > 0 for volume in prior_volumes):
            average = sum(prior_volumes) / 10.0
            if average > 0 and today_volume >= average * _SURGE and price > previous_close:
                pillars += 1
                reasons.append(REASON_SURGE)
    return pillars, reasons


def classify_correction(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(snapshot, dict):
        return None
    symbol = str(snapshot.get("symbol") or "").strip().upper()
    if not is_tasi_main_symbol(symbol) or is_prohibited(symbol):
        return None
    price = _positive(snapshot.get("last_price") or snapshot.get("price"))
    if price is None:
        return None
    bars = _bars(snapshot.get("history"))
    session_day = _day_key(snapshot.get("session_date"))
    if price and bars and session_day and session_day != bars[-1][0]:
        today_volume = _positive(snapshot.get("volume"))
        if today_volume is not None and not _is_print_volume(today_volume, [row[2] for row in bars]):
            bars = [*bars, (session_day, price, today_volume)]
    approach_count, approach_reasons = _approach(snapshot, bars, price)
    rebound_count, rebound_reasons = _rebound(snapshot, bars, price)
    if approach_count >= 2 and rebound_count >= 2 and approach_count == rebound_count:
        return None
    if approach_count >= 2 and approach_count >= rebound_count:
        kind = KIND_APPROACH
        signal = SIGNAL_APPROACH
        reasons = approach_reasons
        pillars = approach_count
    elif rebound_count >= 2:
        kind = KIND_REBOUND
        signal = SIGNAL_REBOUND
        reasons = rebound_reasons
        pillars = rebound_count
    else:
        return None
    name = str(snapshot.get("name") or "").strip() or company_name_for(symbol) or symbol
    return {
        "symbol": symbol,
        "name": name,
        "sector": str(snapshot.get("sector") or sector_for(symbol) or ""),
        "last_price": round(price, 4),
        "signal": signal,
        "signal_kind": kind,
        "reasons": reasons,
        "pillars": pillars,
    }


def _tape_snapshot(feed: Any, symbol: str) -> dict[str, Any]:
    tapes = getattr(feed, "_tapes", None)
    if not isinstance(tapes, dict):
        return {}
    tape = tapes.get(symbol)
    if tape is None:
        return {}
    snap = getattr(tape, "snapshot", None)
    if not callable(snap):
        return {}
    try:
        payload = snap()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _levels(feed: Any, symbol: str) -> Any:
    engine = getattr(feed, "_engine", None)
    levels_fn = getattr(engine, "levels_snapshot", None)
    if not callable(levels_fn):
        return None
    try:
        return levels_fn(symbol)
    except Exception:
        return None


def snapshots_from_feed(feed: Any) -> list[dict[str, Any]]:
    if feed is None:
        return []
    universe_fn = getattr(feed, "_universe_symbols", None)
    quotes = getattr(feed, "_quotes", None)
    if not callable(universe_fn) or quotes is None:
        return []
    history_fn = getattr(quotes, "close_history", None)
    price_fn = getattr(quotes, "display_price", None)
    get_fn = getattr(quotes, "get", None)
    if not callable(history_fn) or not callable(price_fn):
        return []
    today = now_riyadh().date().isoformat()
    rows: list[dict[str, Any]] = []
    for symbol in universe_fn() or []:
        ticker = str(symbol or "").strip().upper()
        if not is_tasi_main_symbol(ticker) or is_prohibited(ticker):
            continue
        stored = get_fn(ticker) if callable(get_fn) else None
        stored = stored if isinstance(stored, dict) else {}
        live = _tape_snapshot(feed, ticker)
        levels = _levels(feed, ticker)
        price = _positive(live.get("last_price")) or _positive(price_fn(ticker)) or _positive(stored.get("last_price"))
        if price is None:
            continue
        vwap = _positive(getattr(levels, "vwap", None)) if levels is not None else None
        if vwap is None:
            turnover = _positive(live.get("session_value"))
            quantity = _positive(live.get("session_volume"))
            if turnover is not None and quantity is not None:
                vwap = turnover / quantity
        session_low = _positive(getattr(levels, "session_low", None)) if levels is not None else None
        if session_low is None:
            session_low = _positive(live.get("session_low"))
        volume = _positive(live.get("session_volume")) or _positive(stored.get("volume"))
        rows.append(
            {
                "symbol": ticker,
                "name": company_name_for(ticker) or stored.get("name") or ticker,
                "sector": sector_for(ticker),
                "last_price": price,
                "volume": volume,
                "session_date": today,
                "history": history_fn(ticker),
                "institutional_inflow": live.get("institutional_inflow"),
                "institutional_outflow": live.get("institutional_outflow"),
                "institutional_mfi": live.get("institutional_mfi"),
                "block_trades": live.get("block_trades") or 0,
                "block_volume": live.get("block_volume"),
                "block_side": live.get("block_side"),
                "session_vwap": vwap,
                "session_low": session_low,
            }
        )
    return rows


def scan_correction_radar(
    feed: Any = None,
    *,
    snapshots: list[dict[str, Any]] | None = None,
    moment: Any = None,
    source: str = "TickChart",
) -> dict[str, Any]:
    current = now_riyadh(moment)
    phase = session_phase(current)
    raw = snapshots if snapshots is not None else snapshots_from_feed(feed)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw or []:
        classified = classify_correction(item if isinstance(item, dict) else {})
        if classified is None or classified["symbol"] in seen:
            continue
        seen.add(classified["symbol"])
        rows.append(classified)
    rows.sort(key=lambda row: (-int(row["pillars"]), 0 if row["signal_kind"] == KIND_APPROACH else 1, row["symbol"]))
    scanned = current if isinstance(current, datetime) else now_riyadh()
    return {
        "success": True,
        "session_phase": phase,
        "session_label": phase_label(phase),
        "source": source,
        "count": len(rows),
        "approach_count": sum(1 for row in rows if row["signal_kind"] == KIND_APPROACH),
        "rebound_count": sum(1 for row in rows if row["signal_kind"] == KIND_REBOUND),
        "hint": HINT,
        "scanned_at": scanned.isoformat(),
        "data": rows,
    }
