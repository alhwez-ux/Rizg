"""Smart position recovery: loss snapshot, optional averaging, rotation into momentum names."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.exceptions import InvalidSymbolError, ProhibitedSymbolError, SymbolNotFoundError
from app.models.screener import is_tasi_main_symbol, normalize_tasi_symbol
from app.services.shariah import company_name_for, is_prohibited, sector_for
from app.services.signals import is_valid_long_plan, long_trade_levels
from app.services.smart_money import KIND_ACCUMULATION, scan_smart_money
from app.services.tasi_clock import now_riyadh, phase_label, session_phase

HIDDEN_KINDS = frozenset({"hidden_accumulation", "silent_accumulation"})
MAX_ALTERNATIVES = 4
MIN_CANDIDATE_SCORE = 38.0
ROTATION_SHARE = 0.45

HINT = (
    "لا يُنصح بمطاردة الخسارة على نفس السهم إن كان التصريف واضحاً. "
    "الحاسبة تدور جزءاً من السيولة إلى أسماء بزخم مؤسسي أو تجميع خفي أو جاهزية كسر، مع هدف ووقف موثّقين."
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


def _trap_kind(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("kind") or "").strip()
    return str(value or "").strip()


def snapshot_position(
    *,
    symbol: str,
    name: str,
    quantity: float,
    avg_price: float,
    last_price: float,
    sector: str = "",
) -> dict[str, Any]:
    cost = quantity * avg_price
    market = quantity * last_price
    pnl = market - cost
    loss_amount = max(0.0, -pnl)
    pnl_pct = ((last_price - avg_price) / avg_price) * 100.0 if avg_price > 0 else 0.0
    return {
        "symbol": symbol,
        "name": name or symbol,
        "sector": sector,
        "quantity": round(quantity, 4),
        "avg_price": round(avg_price, 4),
        "last_price": round(last_price, 4),
        "cost_basis": round(cost, 2),
        "market_value": round(market, 2),
        "unrealized_pnl": round(pnl, 2),
        "loss_amount": round(loss_amount, 2),
        "pnl_pct": round(pnl_pct, 2),
        "in_loss": pnl < 0,
    }


def _constructive(row: dict[str, Any]) -> bool:
    trap = _trap_kind(row.get("trap"))
    inst = _num(row.get("institutional_mfi")) or 50.0
    net = _num(row.get("net_flow") or row.get("institutional_inflow")) or 0.0
    if bool(row.get("hidden_accumulation")) or trap in HIDDEN_KINDS:
        return True
    if bool(row.get("compressed")) and inst >= 52:
        return True
    if inst >= 54 and net >= 0:
        return True
    if str(row.get("signal_kind") or "") == KIND_ACCUMULATION:
        return True
    return False


def _dumping(row: dict[str, Any]) -> bool:
    trap = _trap_kind(row.get("trap"))
    if trap in {"silent_distribution", "bull_trap"}:
        return True
    inst = _num(row.get("institutional_mfi"))
    net = _num(row.get("net_flow")) or 0.0
    if inst is not None and inst <= 42 and net < 0:
        return True
    if str(row.get("signal_kind") or "") == "distribution":
        return True
    return False


def average_down_plan(position: dict[str, Any], owned: dict[str, Any]) -> dict[str, Any] | None:
    if not position.get("in_loss"):
        return None
    if _dumping(owned) or not _constructive(owned):
        return None
    last = float(position["last_price"])
    qty = float(position["quantity"])
    avg = float(position["avg_price"])
    extra = max(1, int(round(qty)))
    extra_cost = extra * last
    new_qty = qty + extra
    new_avg = (qty * avg + extra * last) / new_qty
    try:
        target, stop = long_trade_levels(
            last,
            atr=_num(owned.get("atr")),
            swing_low=_num(owned.get("session_low") or owned.get("support") or owned.get("low")),
        )
    except ValueError:
        return None
    target_f = round(float(target), 4)
    stop_f = round(float(stop), 4)
    if not is_valid_long_plan(last, target_f, stop_f):
        return None
    return {
        "recommended": True,
        "extra_quantity": extra,
        "extra_cost": round(extra_cost, 2),
        "new_quantity": round(new_qty, 4),
        "new_avg_price": round(new_avg, 4),
        "entry": round(last, 4),
        "target": target_f,
        "stop": stop_f,
        "reason": "السهم لا يزال في تجميع/تدفق مؤسسي — تعديل الكمية يخفض المتوسط دون مطاردة التصريف",
    }


def candidate_score(row: dict[str, Any], *, exclude: str) -> float | None:
    symbol = str(row.get("symbol") or "").strip().upper()
    if not is_tasi_main_symbol(symbol) or symbol == exclude or is_prohibited(symbol):
        return None
    last = _num(row.get("last_price") or row.get("price") or row.get("entry"))
    if last is None or last <= 0:
        return None
    trap = _trap_kind(row.get("trap"))
    hidden = bool(row.get("hidden_accumulation")) or trap in HIDDEN_KINDS
    explosive = bool(row.get("explosive") or row.get("resistance_break"))
    under_watch = bool(row.get("under_watch"))
    inst = _num(row.get("institutional_mfi"))
    net = _num(row.get("net_flow")) or 0.0
    signal = str(row.get("signal") or "")
    kind = str(row.get("signal_kind") or "")
    flow_score = _num(row.get("institutional_flow_score") or row.get("score")) or 0.0
    volume_ratio = _num(row.get("volume_ratio")) or 0.0
    eligible = bool(
        hidden
        or explosive
        or under_watch
        or kind == KIND_ACCUMULATION
        or signal == "entry"
        or (inst is not None and inst >= 54 and net > 0)
        or (flow_score >= 55 and kind == KIND_ACCUMULATION)
    )
    if not eligible or _dumping(row):
        return None
    score = 0.0
    if hidden:
        score += 28.0
    if explosive:
        score += 24.0
    if under_watch:
        score += 10.0
    if kind == KIND_ACCUMULATION:
        score += 16.0
    if inst is not None:
        score += max(0.0, inst - 50.0) * 0.45
    if net > 0:
        score += min(12.0, 4.0 + net / 50_000.0)
    if volume_ratio >= 1.5:
        score += 8.0
    score += min(18.0, flow_score * 0.18)
    if score < MIN_CANDIDATE_SCORE:
        return None
    return round(score, 2)


def _plan_levels(row: dict[str, Any]) -> tuple[float, float, float] | None:
    last = _num(row.get("entry") or row.get("last_price") or row.get("price"))
    if last is None or last <= 0:
        return None
    existing_target = _num(row.get("target") or row.get("target_price"))
    existing_stop = _num(row.get("stop") or row.get("stop_loss"))
    if existing_target and existing_stop and is_valid_long_plan(last, existing_target, existing_stop):
        return round(last, 4), round(existing_target, 4), round(existing_stop, 4)
    try:
        target, stop = long_trade_levels(
            last,
            atr=_num(row.get("atr")),
            swing_low=_num(row.get("session_low") or row.get("support") or row.get("low") or row.get("swing_low")),
        )
    except ValueError:
        return None
    target_f = round(float(target), 4)
    stop_f = round(float(stop), 4)
    if not is_valid_long_plan(last, target_f, stop_f):
        return None
    return round(last, 4), target_f, stop_f


def _tags(row: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    trap = _trap_kind(row.get("trap"))
    if bool(row.get("hidden_accumulation")) or trap in HIDDEN_KINDS:
        tags.append("تجميع مؤسسي خفي")
    if bool(row.get("explosive") or row.get("resistance_break")):
        tags.append("جاهزية كسر")
    if str(row.get("signal_kind") or "") == KIND_ACCUMULATION or (_num(row.get("institutional_mfi")) or 0) >= 54:
        tags.append("تدفق مؤسسي")
    if bool(row.get("under_watch")) and "تجميع مؤسسي خفي" not in tags:
        tags.append("تحت المراقبة")
    return tags or ["زخم إيجابي"]


def allocate_rotation(
    budget: float,
    ranked: list[tuple[float, dict[str, Any]]],
    *,
    limit: int = MAX_ALTERNATIVES,
) -> list[dict[str, Any]]:
    picked: list[tuple[float, dict[str, Any], float, float, float]] = []
    for score, row in ranked[: limit * 2]:
        levels = _plan_levels(row)
        if levels is None:
            continue
        picked.append((score, row, *levels))
        if len(picked) >= limit:
            break
    if not picked or budget <= 0:
        return []
    total_score = sum(item[0] for item in picked) or 1.0
    leftover = budget
    rows: list[dict[str, Any]] = []
    for index, (score, row, entry, target, stop) in enumerate(picked):
        weight = score / total_score
        remaining_slots = len(picked) - index
        alloc = leftover if remaining_slots == 1 else min(leftover, budget * weight)
        shares = int(alloc // entry) if entry > 0 else 0
        if shares < 1:
            continue
        spent = shares * entry
        leftover = max(0.0, leftover - spent)
        expected = shares * (target - entry)
        symbol = str(row.get("symbol") or "").strip().upper()
        rows.append(
            {
                "symbol": symbol,
                "name": row.get("name") or company_name_for(symbol) or symbol,
                "sector": row.get("sector") or sector_for(symbol) or "",
                "score": score,
                "tags": _tags(row),
                "weight_pct": round(weight * 100.0, 1),
                "allocation": round(spent, 2),
                "shares": shares,
                "entry": entry,
                "target": target,
                "stop": stop,
                "expected_gain": round(expected, 2),
                "reason": row.get("reason")
                or row.get("watch_flag")
                or ("تجميع خفي مع حجم مرتفع" if "تجميع مؤسسي خفي" in _tags(row) else "زخم مؤسسي جاهز للدخول"),
            }
        )
    return rows


def rotation_budget(position: dict[str, Any]) -> float:
    market = float(position["market_value"])
    loss = float(position["loss_amount"])
    if market <= 0:
        return 0.0
    if loss <= 0:
        return 0.0
    needed = max(loss * 2.4, market * 0.30)
    return round(min(market * ROTATION_SHARE, needed, market), 2)


def build_recovery_plan(
    *,
    symbol: str,
    quantity: float,
    avg_price: float,
    last_price: float,
    name: str = "",
    sector: str = "",
    owned: dict[str, Any] | None = None,
    candidates: list[dict[str, Any]] | None = None,
    moment: Any = None,
    source: str = "TickChart",
) -> dict[str, Any]:
    ticker = _require_symbol(symbol)
    if quantity <= 0 or avg_price <= 0 or last_price <= 0:
        raise InvalidSymbolError(ticker, message="الكمية ومتوسط الشراء والسعر الحالي يجب أن تكون أكبر من صفر")
    position = snapshot_position(
        symbol=ticker,
        name=name or company_name_for(ticker) or ticker,
        quantity=quantity,
        avg_price=avg_price,
        last_price=last_price,
        sector=sector or sector_for(ticker) or "",
    )
    owned_row = dict(owned or {})
    averaging = average_down_plan(position, owned_row)
    ranked: list[tuple[float, dict[str, Any]]] = []
    seen: set[str] = set()
    for item in candidates or []:
        if not isinstance(item, dict):
            continue
        score = candidate_score(item, exclude=ticker)
        if score is None:
            continue
        alt = str(item.get("symbol") or "").strip().upper()
        if alt in seen:
            continue
        seen.add(alt)
        ranked.append((score, item))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    budget = rotation_budget(position)
    allocations = allocate_rotation(budget, ranked)
    expected = sum(float(row["expected_gain"]) for row in allocations)
    loss = float(position["loss_amount"])
    cover = round((expected / loss) * 100.0, 1) if loss > 0 and expected > 0 else 0.0
    if not position["in_loss"]:
        stance = "hold"
        stance_label = "المركز رابح — لا حاجة لتعويض خسارة"
    elif averaging and allocations:
        stance = "mixed"
        stance_label = "تعديل محدود على نفس السهم مع تدوير جزء من السيولة لأسماء أقوى"
    elif averaging:
        stance = "average"
        stance_label = "يمكن التعديل على نفس السهم لأن التجميع ما زال قائماً"
    elif allocations:
        stance = "rotate"
        stance_label = "يُفضّل تدوير السيولة إلى أسماء بزخم مؤسسي بدل مطاردة نفس الخسارة"
    else:
        stance = "wait"
        stance_label = "لا توجد بدائل زخم موثّقة الآن — أبقِ المراقبة دون زيادة الكمية"
    current = now_riyadh(moment)
    phase = session_phase(current)
    return {
        "success": True,
        "session_phase": phase,
        "session_label": phase_label(phase),
        "source": source,
        "stance": stance,
        "stance_label": stance_label,
        "hint": HINT,
        "scanned_at": (current if isinstance(current, datetime) else now_riyadh()).isoformat(),
        "position": position,
        "averaging": averaging,
        "rotation_budget": budget,
        "expected_recovery": round(expected, 2),
        "cover_pct": cover,
        "count": len(allocations),
        "data": allocations,
    }


def _require_symbol(symbol: str) -> str:
    raw = str(symbol or "").strip().upper()
    try:
        ticker = normalize_tasi_symbol(raw)
    except ValueError as exc:
        raise InvalidSymbolError(raw) from exc
    if not is_tasi_main_symbol(ticker):
        raise InvalidSymbolError(ticker)
    return ticker


def _quote_from_feed(feed: Any, symbol: str) -> dict[str, Any]:
    report: dict[str, Any] = {}
    radar = getattr(feed, "radar_report", None)
    if callable(radar):
        try:
            payload = radar(symbol)
        except Exception:
            payload = None
        if isinstance(payload, dict):
            report.update(payload)
    quotes = getattr(feed, "_quotes", None)
    stored: dict[str, Any] = {}
    if quotes is not None:
        getter = getattr(quotes, "get", None)
        if callable(getter):
            stored = getter(symbol) or {}
        elif isinstance(quotes, dict):
            stored = quotes.get(symbol) or {}
    last = _num(report.get("last_price")) or _num(stored.get("last_price"))
    if last:
        report.setdefault("last_price", last)
    report.setdefault("name", stored.get("name") or company_name_for(symbol) or symbol)
    report.setdefault("sector", stored.get("sector") or sector_for(symbol) or "")
    report.setdefault("atr", stored.get("atr"))
    report.setdefault("session_low", stored.get("low") or stored.get("session_low"))
    report.setdefault("symbol", symbol)
    return report


def _candidates_from_feed(feed: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if feed is None:
        return rows
    market = getattr(feed, "market_rows", None)
    if callable(market):
        try:
            rows.extend(item for item in (market() or []) if isinstance(item, dict))
        except Exception:
            pass
    watch = getattr(feed, "under_watch_rows", None)
    if callable(watch):
        try:
            for item in watch() or []:
                if isinstance(item, dict):
                    rows.append({**item, "under_watch": True, "last_price": item.get("last_price") or item.get("price")})
        except Exception:
            pass
    try:
        smart = scan_smart_money(feed)
        for item in smart.get("data") or []:
            if isinstance(item, dict):
                rows.append(item)
    except Exception:
        pass
    return rows


def plan_from_feed(
    feed: Any,
    *,
    symbol: str,
    quantity: float,
    avg_price: float,
) -> dict[str, Any]:
    ticker = _require_symbol(symbol)
    if is_prohibited(ticker):
        raise ProhibitedSymbolError(ticker)
    owned = _quote_from_feed(feed, ticker) if feed is not None else {}
    last = _num(owned.get("last_price"))
    if last is None or last <= 0:
        raise SymbolNotFoundError(ticker)
    return build_recovery_plan(
        symbol=ticker,
        quantity=quantity,
        avg_price=avg_price,
        last_price=last,
        name=str(owned.get("name") or company_name_for(ticker) or ticker),
        sector=str(owned.get("sector") or sector_for(ticker) or ""),
        owned=owned,
        candidates=_candidates_from_feed(feed),
    )
