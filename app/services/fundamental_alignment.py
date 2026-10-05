"""السهم يتبع ورقته: دخول وتجميع فقط إذا كانت الورقة سليمة، والضخ على ورقة ضعيفة خروج أو تصريف."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from app.services.shariah import MAX_DEBT_RATIO, compliance_universe

MAX_HEALTHY_PE = 35.0
PUMP_CHANGE_PERCENT = 5.0
PUMP_VOLUME_SURGE = 1.5

_ROOT = Path(__file__).resolve().parents[2]
_MARKET_BOOK = _ROOT / "web" / "lib" / "marketData.ts"
_OBJECT = re.compile(r"\{([^{}]+)\}", re.S)
_SYMBOL = re.compile(r'symbol:\s*"(\d{4})"')
_PE = re.compile(r"pe_ratio:\s*(null|-?\d+(?:\.\d+)?)")
_INCOME = re.compile(r"net_income:\s*(-?\d[\d_]*)")
_GUARD = threading.RLock()
_CACHE: dict[str, dict[str, float | None]] | None = None


@dataclass(frozen=True)
class FinancialPaper:
    symbol: str
    pe_ratio: float | None = None
    debt_ratio: float | None = None
    net_income: float | None = None
    eps: float | None = None


@dataclass(frozen=True)
class PaperVerdict:
    healthy: bool
    weak: bool
    reasons: tuple[str, ...]


def reset_paper_cache() -> None:
    global _CACHE
    with _GUARD:
        _CACHE = None


def load_paper(symbol: str, overlay: Mapping[str, Any] | None = None) -> FinancialPaper:
    """Real stored figures only. A missing multiple or debt stays missing."""

    ticker = str(symbol or "").strip().upper()
    stored = _metrics().get(ticker, {})
    merged = {
        "pe_ratio": stored.get("pe_ratio"),
        "debt_ratio": stored.get("debt_ratio"),
        "net_income": stored.get("net_income"),
        "eps": stored.get("eps"),
    }
    for key in merged:
        if overlay and overlay.get(key) not in (None, ""):
            merged[key] = _float(overlay.get(key))
    return FinancialPaper(
        symbol=ticker,
        pe_ratio=_float(merged["pe_ratio"]),
        debt_ratio=_float(merged["debt_ratio"]),
        net_income=_float(merged["net_income"]),
        eps=_float(merged["eps"]),
    )


def judge(paper: FinancialPaper) -> PaperVerdict:
    reasons: list[str] = []
    weak = False
    if paper.net_income is not None and paper.net_income <= 0:
        weak = True
        reasons.append("صافي الدخل غير موجب")
    if paper.eps is not None and paper.eps < 0:
        weak = True
        reasons.append("ربحية السهم سالبة")
    if paper.pe_ratio is not None and paper.pe_ratio <= 0:
        weak = True
        reasons.append("مكرر الربحية غير موجب")
    if paper.pe_ratio is not None and paper.pe_ratio > MAX_HEALTHY_PE:
        weak = True
        reasons.append(f"مكرر الربحية {paper.pe_ratio:.1f} أعلى من {MAX_HEALTHY_PE:.0f}")
    if paper.debt_ratio is not None and paper.debt_ratio > MAX_DEBT_RATIO:
        weak = True
        reasons.append("دين الفائدة أعلى من 33% من القيمة")

    pe_ok = paper.pe_ratio is not None and 0 < paper.pe_ratio <= MAX_HEALTHY_PE
    debt_ok = paper.debt_ratio is not None and 0 <= paper.debt_ratio <= MAX_DEBT_RATIO
    loss = (paper.net_income is not None and paper.net_income <= 0) or (
        paper.eps is not None and paper.eps < 0
    )
    earnings_ok = not loss and (pe_ok or (paper.net_income is not None and paper.net_income > 0) or (
        paper.eps is not None and paper.eps > 0
    ))
    healthy = pe_ok and debt_ok and earnings_ok and not weak
    if not healthy and not weak:
        missing: list[str] = []
        if not pe_ok:
            missing.append("مكرر الربحية")
        if paper.debt_ratio is None:
            missing.append("صحة الدين")
        if not earnings_ok:
            missing.append("الوضع المالي")
        reasons.append("شرط الورقة غير مكتمل: " + "، ".join(missing))
    return PaperVerdict(healthy=healthy, weak=weak, reasons=tuple(reasons))


def is_pumping(
    *,
    change_percent: float | None,
    volume_surge: float | None,
    net_positive: bool,
    liquidity_event: bool = False,
) -> bool:
    """Short-term liquidity expansion. A classified accumulation tape counts as that event."""

    if liquidity_event:
        return True
    change = change_percent or 0.0
    surge = volume_surge or 0.0
    if change >= PUMP_CHANGE_PERCENT and (net_positive or surge >= 1.25):
        return True
    return surge >= PUMP_VOLUME_SURGE and change > 0 and net_positive


def align_tape(
    entry: bool,
    exit_signal: bool,
    *,
    symbol: str | None,
    change_percent: float | None = None,
    volume_surge: float | None = None,
    net_positive: bool = False,
    overlay: Mapping[str, Any] | None = None,
) -> tuple[bool, bool, tuple[str, ...]]:
    ticker = str(symbol or "").strip().upper()
    if not ticker and not overlay:
        return entry, exit_signal, ()
    verdict = judge(load_paper(ticker, overlay))
    pumping = is_pumping(
        change_percent=change_percent,
        volume_surge=volume_surge,
        net_positive=net_positive,
    )
    if verdict.weak and pumping:
        detail = verdict.reasons[0] if verdict.reasons else "الورقة ضعيفة"
        return False, True, (f"السيولة المرتفعة لا تتبع الورقة: {detail} — خروج/تصريف",)
    if entry and not verdict.healthy:
        detail = verdict.reasons[0] if verdict.reasons else "الورقة غير مكتملة"
        return False, exit_signal, (f"لا دخول قبل سلامة الورقة: {detail}",)
    if entry and verdict.healthy:
        return entry, exit_signal, ("الورقة المالية سليمة: مكرر الربحية ودين الفائدة والربحية ضمن الحدود",)
    return entry, exit_signal, ()


def align_smart_kind(
    kind: str,
    symbol: str,
    snapshot: Mapping[str, Any] | None = None,
) -> tuple[str, str | None]:
    """تجميع يتطلب ورقة سليمة. سيولة مرتفعة على ورقة ضعيفة تصبح تصريفاً."""

    payload = snapshot if isinstance(snapshot, Mapping) else {}
    verdict = judge(load_paper(symbol, _overlay(payload)))
    change = _float(payload.get("change_percent") if payload.get("change_percent") not in (None, "") else payload.get("price_change_pct"))
    surge = _float(payload.get("volume_surge") if payload.get("volume_surge") not in (None, "") else payload.get("volume_ratio"))
    inflow = _float(payload.get("institutional_inflow")) or 0.0
    outflow = _float(payload.get("institutional_outflow")) or 0.0
    net_positive = inflow > outflow
    if kind == "accumulation":
        if verdict.weak and is_pumping(
            change_percent=change,
            volume_surge=surge,
            net_positive=net_positive,
            liquidity_event=True,
        ):
            detail = verdict.reasons[0] if verdict.reasons else "الورقة ضعيفة"
            return "distribution", f"السيولة المرتفعة لا تتبع الورقة: {detail} — تصريف"
        if not verdict.healthy:
            detail = verdict.reasons[0] if verdict.reasons else "الورقة غير مكتملة"
            return "watch", f"لا تجميع قبل سلامة الورقة: {detail}"
        return kind, "الورقة المالية سليمة: مكرر الربحية ودين الفائدة والربحية ضمن الحدود"
    if kind == "watch" and verdict.weak and is_pumping(
        change_percent=change,
        volume_surge=surge,
        net_positive=net_positive or (change or 0) >= PUMP_CHANGE_PERCENT,
    ):
        detail = verdict.reasons[0] if verdict.reasons else "الورقة ضعيفة"
        return "distribution", f"السيولة المرتفعة لا تتبع الورقة: {detail} — تصريف"
    return kind, None


def entry_allowed(symbol: str, overlay: Mapping[str, Any] | None = None) -> bool:
    return judge(load_paper(symbol, overlay)).healthy


def _overlay(snapshot: Mapping[str, Any]) -> dict[str, Any] | None:
    found: dict[str, Any] = {}
    aliases = {
        "pe_ratio": ("pe_ratio", "pe"),
        "debt_ratio": ("debt_ratio", "debtRatio"),
        "net_income": ("net_income", "netIncome"),
        "eps": ("eps",),
    }
    for key, names in aliases.items():
        for name in names:
            if snapshot.get(name) not in (None, ""):
                found[key] = snapshot.get(name)
                break
    return found or None


def _metrics() -> dict[str, dict[str, float | None]]:
    global _CACHE
    with _GUARD:
        if _CACHE is None:
            _CACHE = _build_metrics()
        return _CACHE


def _build_metrics() -> dict[str, dict[str, float | None]]:
    rows: dict[str, dict[str, float | None]] = {}
    for symbol, pe, income in _market_rows():
        rows[symbol] = {"pe_ratio": pe, "debt_ratio": None, "net_income": income, "eps": None}
    for item in compliance_universe():
        symbol = str(item.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        slot = rows.setdefault(symbol, {"pe_ratio": None, "debt_ratio": None, "net_income": None, "eps": None})
        slot["debt_ratio"] = _float(item.get("debtRatio") or item.get("debt_ratio"))
    try:
        from app.services.ranking_store import RankingStore

        for row in RankingStore().snapshot():
            symbol = str(row.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            slot = rows.setdefault(symbol, {"pe_ratio": None, "debt_ratio": None, "net_income": None, "eps": None})
            pe = _float(row.get("pe_ratio"))
            income = _float(row.get("net_income"))
            eps = _float(row.get("eps"))
            if pe is not None:
                slot["pe_ratio"] = pe
            if income is not None:
                slot["net_income"] = income
            if eps is not None:
                slot["eps"] = eps
    except Exception:
        pass
    return rows


def _market_rows() -> list[tuple[str, float | None, float | None]]:
    if not _MARKET_BOOK.exists():
        return []
    try:
        text = _MARKET_BOOK.read_text(encoding="utf-8")
    except OSError:
        return []
    parsed: list[tuple[str, float | None, float | None]] = []
    for block in _OBJECT.findall(text):
        symbol_match = _SYMBOL.search(block)
        if symbol_match is None:
            continue
        pe_match = _PE.search(block)
        income_match = _INCOME.search(block)
        pe = None if pe_match is None or pe_match.group(1) == "null" else _float(pe_match.group(1))
        income = _float(income_match.group(1).replace("_", "")) if income_match else None
        parsed.append((symbol_match.group(1), pe, income))
    return parsed


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = value.replace("_", "").replace(",", "")
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number
