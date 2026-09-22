"""Institutional footprint + smart-money flow score from TASI TickChart tapes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models.screener import is_tasi_main_symbol
from app.services.shariah import company_name_for, is_prohibited, sector_for
from app.services.signals import is_valid_long_plan, long_trade_levels
from app.services.tasi_clock import now_riyadh, phase_label, session_phase

KIND_ACCUMULATION = "accumulation"
KIND_DISTRIBUTION = "distribution"
KIND_WATCH = "watch"

SIGNAL_ACCUMULATION = "تجميع صناديق"
SIGNAL_DISTRIBUTION = "تصريف مؤسسي"
SIGNAL_WATCH = "مراقبة مؤسسية"

BADGE_FUNDS = "صناديق"
BADGE_PORTFOLIO = "محفظة كبرى"
BADGE_DISTRIBUTION = "تصريف مؤسسي"
BADGE_WATCH = "مراقبة"

MIN_INST_VALUE = 50_000.0
MIN_SCORE_ACCUMULATION = 55.0
MIN_SCORE_DISTRIBUTION = 52.0
MIN_SCORE_WATCH = 45.0
PORTFOLIO_SCORE = 82.0
PORTFOLIO_BLOCK_VALUE = 1_000_000.0

HINT = (
    "صفقات الكتل والتجميع قرب جدار الطلب — درجة التدفق المؤسسي تقيس سيطرة الصناديق مقابل التجزئة. "
    "الأسهم ذات الشارة تُعرض مع هدف ووقف موثّقين لاتباع المحافظ الكبرى دون مطاردة السيولة الصغيرة."
)


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


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _wall_qty(wall: Any) -> float:
    if not isinstance(wall, dict):
        return 0.0
    return max(0.0, _num(wall.get("quantity")) or 0.0)


def _wall_price(wall: Any) -> float | None:
    if not isinstance(wall, dict):
        return None
    price = _num(wall.get("price"))
    return price if price is not None and price > 0 else None


def score_institutional_flow(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Measure smart-money dominance versus retail on a single TASI tape snapshot.

    Institutional Flow Score is 0–100:
      32% share of tape value that is institutional
      28% directional conviction (|institutional MFI − 50| × 2)
      18% block-print density
      14% clustered size near support / bid wall
       8% Level-2 wall alignment
    """

    inst_in = max(0.0, _num(snapshot.get("institutional_inflow")) or 0.0)
    inst_out = max(0.0, _num(snapshot.get("institutional_outflow")) or 0.0)
    retail_in = max(0.0, _num(snapshot.get("retail_inflow")) or 0.0)
    retail_out = max(0.0, _num(snapshot.get("retail_outflow")) or 0.0)
    inst_total = inst_in + inst_out
    retail_total = retail_in + retail_out
    all_flow = inst_total + retail_total
    inst_share = (inst_total / all_flow * 100.0) if all_flow > 0 else 0.0
    retail_share = (100.0 - inst_share) if all_flow > 0 else 0.0

    inst_mfi = _num(snapshot.get("institutional_mfi"))
    if inst_mfi is None:
        inst_mfi = (inst_in / inst_total * 100.0) if inst_total > 0 else 50.0
    retail_mfi = _num(snapshot.get("retail_mfi"))
    if retail_mfi is None:
        retail_mfi = (retail_in / retail_total * 100.0) if retail_total > 0 else 50.0

    blocks = max(0, int(_num(snapshot.get("block_trades")) or 0))
    clustered_buys = max(0, int(_num(snapshot.get("clustered_buys")) or 0))
    clustered_sells = max(0, int(_num(snapshot.get("clustered_sells")) or 0))
    clustered = max(0, int(_num(snapshot.get("clustered")) or (clustered_buys + clustered_sells)))
    cluster_run = max(0, int(_num(snapshot.get("cluster_run")) or 0))
    near_bid = bool(snapshot.get("near_bid_wall"))
    bid_qty = _wall_qty(snapshot.get("bid_wall"))
    ask_qty = _wall_qty(snapshot.get("ask_wall"))

    dominance = inst_share
    conviction = abs(inst_mfi - 50.0) * 2.0
    block_score = min(blocks / 8.0, 1.0) * 100.0
    cluster_raw = max(clustered, cluster_run * 1.2, clustered_buys, clustered_sells)
    cluster_score = min(cluster_raw / 6.0, 1.0) * 100.0
    if near_bid and clustered_buys >= 3:
        cluster_score = min(100.0, cluster_score + 15.0)

    wall_score = 0.0
    if bid_qty > 0 and bid_qty >= max(ask_qty, 1.0) * 1.5:
        wall_score = 80.0 if inst_mfi >= 52 else 40.0
    elif ask_qty > 0 and ask_qty >= max(bid_qty, 1.0) * 1.5:
        wall_score = 80.0 if inst_mfi <= 48 else 40.0
    if near_bid:
        wall_score = max(wall_score, 70.0)

    score = (
        0.32 * dominance
        + 0.28 * conviction
        + 0.18 * block_score
        + 0.14 * cluster_score
        + 0.08 * wall_score
    )
    return {
        "score": round(_clamp(score), 1),
        "inst_share": round(_clamp(inst_share), 1),
        "retail_share": round(_clamp(retail_share), 1),
        "inst_mfi": round(_clamp(inst_mfi), 1),
        "retail_mfi": round(_clamp(retail_mfi), 1),
        "net_inst": inst_in - inst_out,
        "inst_total": inst_total,
        "retail_total": retail_total,
        "blocks": blocks,
        "clustered": clustered,
        "clustered_buys": clustered_buys,
        "clustered_sells": clustered_sells,
        "cluster_run": cluster_run,
        "near_bid_wall": near_bid,
        "bid_wall_qty": bid_qty,
        "ask_wall_qty": ask_qty,
    }


def _has_footprint(metrics: dict[str, Any]) -> bool:
    if metrics["blocks"] >= 1:
        return True
    if metrics["inst_total"] >= MIN_INST_VALUE:
        return True
    if metrics["clustered"] >= 3 or metrics["cluster_run"] >= 3:
        return True
    if metrics["near_bid_wall"] and metrics["inst_mfi"] >= 55:
        return True
    return False


def _kind(metrics: dict[str, Any]) -> str | None:
    if not _has_footprint(metrics):
        return None
    net = metrics["net_inst"]
    mfi = metrics["inst_mfi"]
    score = metrics["score"]
    clustered_buys = metrics["clustered_buys"]
    clustered_sells = metrics["clustered_sells"]
    blocks = metrics["blocks"]
    near_bid = metrics["near_bid_wall"]
    buy_cluster = clustered_buys >= 3 or (near_bid and clustered_buys >= 2) or metrics["cluster_run"] >= 3
    sell_cluster = clustered_sells >= 3 or metrics["cluster_run"] >= 3
    if (
        net > 0
        and mfi >= 54
        and score >= MIN_SCORE_ACCUMULATION
        and (blocks >= 2 or buy_cluster or (near_bid and mfi >= 58))
    ):
        return KIND_ACCUMULATION
    if (
        net < 0
        and mfi <= 46
        and score >= MIN_SCORE_DISTRIBUTION
        and (blocks >= 2 or sell_cluster)
    ):
        return KIND_DISTRIBUTION
    if score >= MIN_SCORE_WATCH:
        return KIND_WATCH
    return None


def _badge(kind: str, score: float, last_block_value: float | None) -> str:
    if kind == KIND_ACCUMULATION:
        if score >= PORTFOLIO_SCORE or (last_block_value or 0) >= PORTFOLIO_BLOCK_VALUE:
            return BADGE_PORTFOLIO
        return BADGE_FUNDS
    if kind == KIND_DISTRIBUTION:
        return BADGE_DISTRIBUTION
    return BADGE_WATCH


def _reason(kind: str, metrics: dict[str, Any]) -> str:
    share = metrics["inst_share"]
    blocks = metrics["blocks"]
    if kind == KIND_ACCUMULATION:
        if metrics["near_bid_wall"] and metrics["clustered_buys"] >= 3:
            return (
                f"كتل شرائية متجمعة قرب جدار الطلب — الصناديق تهيمن بنسبة {share:.0f}% مقابل التجزئة"
            )
        if blocks >= 2:
            return f"{blocks} صفقات كتل شرائية — تدفق مؤسسي داخل السهم مقابل سيولة تجزئة أضعف"
        return "تجميع مؤسسي موثّق قرب الدعم مع سيطرة الصناديق على الشريط"
    if kind == KIND_DISTRIBUTION:
        return f"كتل بيعية وتدفق مؤسسي خارج — الصناديق تصرّف بنسبة سيطرة {share:.0f}%"
    return "نشاط مؤسسي مختلط — راقب الكتل وجدار الطلب قبل الركوب مع المحافظ"


def _long_plan(snapshot: dict[str, Any]) -> tuple[float | None, float | None, float | None, bool]:
    last = _num(snapshot.get("last_price") or snapshot.get("entry") or snapshot.get("close"))
    if last is None or last <= 0:
        return None, None, None, False
    atr = _num(snapshot.get("atr"))
    floors = [
        value
        for value in (
            _num(snapshot.get("support")),
            _num(snapshot.get("session_low")),
            _num(snapshot.get("swing_low")),
            _wall_price(snapshot.get("bid_wall")),
        )
        if value is not None and 0 < value < last
    ]
    swing = min(floors) if floors else None
    try:
        target, stop = long_trade_levels(last, atr=atr, swing_low=swing)
    except ValueError:
        return round(last, 4), None, None, False
    entry = round(last, 4)
    target_f = round(float(target), 4)
    stop_f = round(float(stop), 4)
    return entry, target_f, stop_f, is_valid_long_plan(entry, target_f, stop_f)


def classify_smart_money(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Turn a tape snapshot into a smart-money radar row, or None if retail-only."""

    symbol = str(snapshot.get("symbol") or "").strip().upper()
    if not is_tasi_main_symbol(symbol) or is_prohibited(symbol):
        return None
    metrics = score_institutional_flow(snapshot)
    kind = _kind(metrics)
    if kind is None:
        return None
    last_block = _num(snapshot.get("last_block_value"))
    entry = target = stop = None
    plan_ok = False
    if kind == KIND_ACCUMULATION:
        entry, target, stop, plan_ok = _long_plan(snapshot)
        if not plan_ok:
            return None
    else:
        last = _num(snapshot.get("last_price") or snapshot.get("close"))
        entry = round(last, 4) if last is not None and last > 0 else None
    signal = {
        KIND_ACCUMULATION: SIGNAL_ACCUMULATION,
        KIND_DISTRIBUTION: SIGNAL_DISTRIBUTION,
        KIND_WATCH: SIGNAL_WATCH,
    }[kind]
    badge = _badge(kind, metrics["score"], last_block)
    return {
        "symbol": symbol,
        "name": snapshot.get("name") or company_name_for(symbol) or symbol,
        "sector": snapshot.get("sector") or sector_for(symbol) or "",
        "last_price": entry if kind == KIND_ACCUMULATION else (_num(snapshot.get("last_price"))),
        "institutional_flow_score": metrics["score"],
        "inst_share_pct": metrics["inst_share"],
        "retail_share_pct": metrics["retail_share"],
        "institutional_mfi": metrics["inst_mfi"],
        "retail_mfi": metrics["retail_mfi"],
        "block_trades": metrics["blocks"],
        "last_block_value": last_block,
        "clustered": metrics["clustered"],
        "clustered_buys": metrics["clustered_buys"],
        "cluster_run": metrics["cluster_run"],
        "near_bid_wall": metrics["near_bid_wall"],
        "bid_wall": snapshot.get("bid_wall") if isinstance(snapshot.get("bid_wall"), dict) else None,
        "ask_wall": snapshot.get("ask_wall") if isinstance(snapshot.get("ask_wall"), dict) else None,
        "signal": signal,
        "signal_kind": kind,
        "badge": badge,
        "reason": _reason(kind, metrics),
        "entry": entry,
        "target": target,
        "stop": stop,
        "plan_ok": plan_ok,
        "score": metrics["score"],
    }


def snapshots_from_feed(feed: Any) -> list[dict[str, Any]]:
    if feed is None:
        return []
    custom = getattr(feed, "smart_money_snapshots", None)
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


def scan_smart_money(
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
        classified = classify_smart_money(item if isinstance(item, dict) else {})
        if classified is None:
            continue
        if classified["symbol"] in seen:
            continue
        seen.add(classified["symbol"])
        rows.append(classified)
    kind_rank = {KIND_ACCUMULATION: 0, KIND_WATCH: 1, KIND_DISTRIBUTION: 2}
    rows.sort(
        key=lambda row: (
            kind_rank.get(str(row.get("signal_kind")), 9),
            -float(row.get("institutional_flow_score") or 0),
        )
    )
    accumulation = sum(1 for row in rows if row["signal_kind"] == KIND_ACCUMULATION)
    distribution = sum(1 for row in rows if row["signal_kind"] == KIND_DISTRIBUTION)
    watch = sum(1 for row in rows if row["signal_kind"] == KIND_WATCH)
    scanned = current if isinstance(current, datetime) else now_riyadh()
    return {
        "success": True,
        "session_phase": phase,
        "session_label": phase_label(phase),
        "source": source,
        "count": len(rows),
        "accumulation_count": accumulation,
        "distribution_count": distribution,
        "watch_count": watch,
        "hint": HINT,
        "scanned_at": scanned.isoformat(),
        "data": rows,
    }
