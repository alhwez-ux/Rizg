"""TASI pre-open market intelligence: order-book imbalance and opening auction bias.

Window: 09:30–10:00 Asia/Riyadh. Classifies names as تجميع مبكر or ضغط بيعي مبكر
from buy vs sell book volume, expected opening variation, and large block prints.
"""

from __future__ import annotations

from typing import Any

from app.models.screener import is_tasi_main_symbol
from app.services.shariah import company_name_for, is_prohibited, sector_for
from app.services.tasi_clock import is_preopen_window, now_riyadh, phase_label, session_phase

SIGNAL_ACCUMULATION = "تجميع مبكر"
SIGNAL_DISTRIBUTION = "ضغط بيعي مبكر"
SIGNAL_BALANCED = "توازن مبكر"

KIND_ACCUMULATION = "accumulation"
KIND_DISTRIBUTION = "distribution"
KIND_BALANCED = "balanced"

LIQUIDITY_ACCUMULATION = "تجميع"
LIQUIDITY_DISTRIBUTION = "تصريف"
LIQUIDITY_BALANCED = "توازن"

WINDOW_START = "09:30"
WINDOW_END = "10:00"
TIMEZONE = "Asia/Riyadh"

_IMBALANCE_THRESHOLD = 0.12
_VARIATION_BOOST = 0.35
_BLOCK_BOOST = 0.18

HINT_LIVE = "مزاد افتتاح تاسي مباشر (09:30–10:00) — حجم الطلبات مقابل العروض وصفقات الكتل يحدد التجميع أو التصريف المبكر"
HINT_IDLE = "نافذة القراءة 09:30–10:00 بتوقيت الرياض — تُعرض آخر لقطة لدفاتر الأوامر حتى يبدأ المزاد"


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _positive(value: Any) -> float:
    number = _number(value)
    if number is None or number < 0:
        return 0.0
    return number


def _wall_quantity(wall: Any) -> float:
    if isinstance(wall, dict):
        return _positive(wall.get("quantity") or wall.get("size") or wall.get("volume"))
    return _positive(wall)


def expected_opening_price(
    *,
    bid: float | None,
    ask: float | None,
    last: float | None,
    buy_volume: float,
    sell_volume: float,
) -> float | None:
    """Indicative open: auction last if inside the spread, else pressure-weighted mid.

    Buy-heavy books pull the theoretical open toward the offer; sell-heavy books
    pull it toward the bid.
    """

    total = buy_volume + sell_volume
    if bid and ask and bid > 0 and ask > 0 and total > 0:
        weighted = (ask * buy_volume + bid * sell_volume) / total
        if last and bid <= last <= ask:
            return round(float(last), 4)
        return round(float(weighted), 4)
    if last and last > 0:
        return round(float(last), 4)
    if bid and ask and bid > 0 and ask > 0:
        return round((bid + ask) / 2.0, 4)
    if bid and bid > 0:
        return round(float(bid), 4)
    if ask and ask > 0:
        return round(float(ask), 4)
    return None


def classify_preopen(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Turn one order-book snapshot into a pre-open momentum row."""

    symbol = str(snapshot.get("symbol") or "").strip().upper()
    if not is_tasi_main_symbol(symbol) or is_prohibited(symbol):
        return None

    bid = _number(snapshot.get("bid"))
    ask = _number(snapshot.get("ask"))
    last = _number(snapshot.get("last_price") or snapshot.get("indicative_open") or snapshot.get("expected_open"))
    prev_close = _number(snapshot.get("prev_close"))
    extra_bid = _wall_quantity(snapshot.get("bid_wall"))
    extra_ask = _wall_quantity(snapshot.get("ask_wall"))
    buy_book = max(_positive(snapshot.get("bid_size")), extra_bid)
    sell_book = max(_positive(snapshot.get("ask_size")), extra_ask)
    buy_prints = _positive(snapshot.get("buy_volume"))
    sell_prints = _positive(snapshot.get("sell_volume"))
    if buy_book > 0 or sell_book > 0:
        buy_volume, sell_volume = buy_book, sell_book
    else:
        buy_volume, sell_volume = buy_prints, sell_prints

    block_trades = int(_positive(snapshot.get("block_trades")))
    last_block_value = _number(snapshot.get("last_block_value"))
    inst_in = _positive(snapshot.get("institutional_inflow"))
    inst_out = _positive(snapshot.get("institutional_outflow"))

    if buy_volume <= 0 and sell_volume <= 0 and last is None and bid is None and ask is None:
        return None

    expected = expected_opening_price(
        bid=bid,
        ask=ask,
        last=last,
        buy_volume=buy_volume,
        sell_volume=sell_volume,
    )
    variation = None
    if expected is not None and prev_close and prev_close > 0:
        variation = round(((expected - prev_close) / prev_close) * 100.0, 3)

    book_total = buy_volume + sell_volume
    buy_share = (buy_volume / book_total) if book_total > 0 else None
    imbalance = ((buy_volume - sell_volume) / book_total) if book_total > 0 else None

    block_bias = 0.0
    large_block_side = None
    if inst_in > 0 or inst_out > 0 or block_trades > 0 or extra_bid > 0 or extra_ask > 0:
        if inst_in > inst_out * 1.15:
            block_bias = _BLOCK_BOOST
            large_block_side = "buy"
        elif inst_out > inst_in * 1.15:
            block_bias = -_BLOCK_BOOST
            large_block_side = "sell"
        elif extra_bid > extra_ask * 1.5 and extra_bid > 0:
            block_bias = _BLOCK_BOOST
            large_block_side = "buy"
        elif extra_ask > extra_bid * 1.5 and extra_ask > 0:
            block_bias = -_BLOCK_BOOST
            large_block_side = "sell"
        elif block_trades > 0:
            large_block_side = "mixed"

    variation_bias = 0.0
    if variation is not None:
        variation_bias = max(-1.0, min(1.0, variation / 2.0)) * _VARIATION_BOOST

    book_bias = (imbalance or 0.0) * 0.55
    score = round(book_bias + variation_bias + block_bias, 4)

    if score >= _IMBALANCE_THRESHOLD:
        signal, kind, state = SIGNAL_ACCUMULATION, KIND_ACCUMULATION, LIQUIDITY_ACCUMULATION
    elif score <= -_IMBALANCE_THRESHOLD:
        signal, kind, state = SIGNAL_DISTRIBUTION, KIND_DISTRIBUTION, LIQUIDITY_DISTRIBUTION
    else:
        signal, kind, state = SIGNAL_BALANCED, KIND_BALANCED, LIQUIDITY_BALANCED

    return {
        "symbol": symbol,
        "name": str(snapshot.get("name") or company_name_for(symbol) or symbol),
        "sector": str(snapshot.get("sector") or sector_for(symbol) or ""),
        "expected_open": expected,
        "prev_close": prev_close,
        "open_variation_pct": variation,
        "buy_volume": round(buy_volume, 2),
        "sell_volume": round(sell_volume, 2),
        "book_imbalance": round(imbalance, 4) if imbalance is not None else None,
        "buy_share": round(buy_share, 4) if buy_share is not None else None,
        "block_trades": block_trades,
        "last_block_value": last_block_value,
        "large_block_side": large_block_side,
        "signal": signal,
        "signal_kind": kind,
        "liquidity_state": state,
        "score": score,
    }


def snapshots_from_feed(feed: Any) -> list[dict[str, Any]]:
    if feed is None:
        return []
    custom = getattr(feed, "preopen_snapshots", None)
    if callable(custom):
        try:
            rows = custom()
        except Exception:
            rows = []
        if isinstance(rows, list) and rows:
            return rows
    reports: list[dict[str, Any]] = []
    universe_fn = getattr(feed, "_universe_symbols", None)
    report_fn = getattr(feed, "radar_report", None)
    if not callable(universe_fn) or not callable(report_fn):
        return reports
    for symbol in universe_fn() or []:
        ticker = str(symbol or "").strip().upper()
        if not is_tasi_main_symbol(ticker) or is_prohibited(ticker):
            continue
        try:
            report = report_fn(ticker)
        except Exception:
            continue
        if isinstance(report, dict):
            reports.append(report)
    return reports


def scan_preopen(
    feed: Any = None,
    *,
    snapshots: list[dict[str, Any]] | None = None,
    moment: Any = None,
    source: str = "TickChart",
) -> dict[str, Any]:
    current = now_riyadh(moment)
    phase = session_phase(current)
    in_window = is_preopen_window(current)
    raw = snapshots if snapshots is not None else snapshots_from_feed(feed)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw or []:
        classified = classify_preopen(item if isinstance(item, dict) else {})
        if classified is None:
            continue
        if classified["symbol"] in seen:
            continue
        seen.add(classified["symbol"])
        rows.append(classified)
    rows.sort(key=lambda row: abs(float(row.get("score") or 0)), reverse=True)
    accumulation = sum(1 for row in rows if row["signal_kind"] == KIND_ACCUMULATION)
    distribution = sum(1 for row in rows if row["signal_kind"] == KIND_DISTRIBUTION)
    return {
        "success": True,
        "session_phase": phase,
        "session_label": phase_label(phase),
        "in_window": in_window,
        "window_start": WINDOW_START,
        "window_end": WINDOW_END,
        "timezone": TIMEZONE,
        "source": source,
        "count": len(rows),
        "accumulation_count": accumulation,
        "distribution_count": distribution,
        "hint": HINT_LIVE if in_window else HINT_IDLE,
        "scanned_at": current.isoformat(),
        "data": rows,
    }
