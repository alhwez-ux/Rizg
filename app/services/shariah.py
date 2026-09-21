from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_CANDIDATES = (
    _ROOT / "web" / "prisma" / "tasi-universe.json",
    _ROOT / "data" / "tasi_compliance.json",
)
_LISTED_NAMES_PATH = _ROOT / "web" / "prisma" / "tasi-listed-names.json"
_status_overlay: dict[str, str] = {}
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_ALEF = str.maketrans("أإآٱ", "اااا")
_SYMBOL_RE = re.compile(r"^\d{4}$")


@lru_cache(maxsize=1)
def compliance_universe() -> tuple[dict[str, object], ...]:
    for path in _CANDIDATES:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, list):
            return tuple(item for item in payload if isinstance(item, dict))
    return ()


def apply_status_overlay(symbol: str, status: str) -> None:
    ticker = (symbol or "").strip().upper()
    category = (status or "").strip().upper()
    if ticker and category:
        _status_overlay[ticker] = category


def reset_status_overlay() -> None:
    _status_overlay.clear()


def current_status(symbol: str) -> str | None:
    ticker = (symbol or "").strip().upper()
    if not ticker:
        return None
    overlay = _status_overlay.get(ticker)
    if overlay:
        return overlay
    for item in compliance_universe():
        if str(item.get("symbol") or "").strip().upper() == ticker:
            status = str(item.get("currentStatus") or "").strip().upper()
            return status or None
    return None


def prohibited_symbols() -> set[str]:
    blocked = {
        str(item["symbol"]).strip().upper()
        for item in compliance_universe()
        if str(item.get("currentStatus") or "").upper() == "PROHIBITED" and item.get("symbol")
    }
    for ticker, status in _status_overlay.items():
        if status == "PROHIBITED":
            blocked.add(ticker)
        else:
            blocked.discard(ticker)
    return blocked


def is_prohibited(symbol: str) -> bool:
    ticker = (symbol or "").strip().upper()
    if not ticker:
        return False
    return classified_status(ticker) == "PROHIBITED"


MAX_DEBT_RATIO = 0.33
MAX_INTEREST_SECURITIES = 0.33
MAX_IMPURE_INCOME = 0.05
PURE_DEBT_RATIO = 0.12
PURE_IMPURE_INCOME = 0.005
STATUS_AR = {"PURE": "نقي", "MIXED": "مختلط", "PROHIBITED": "محرم"}


def classify_shariah(
    *,
    debt_ratio: float | None = None,
    impure_income_ratio: float | None = None,
    interest_securities_ratio: float | None = None,
    core_prohibited: bool = False,
) -> str:
    """AAOIFI-style TASI screen: نقي / مختلط / محرم from financial ratios.

    محرم when the core business is non-compliant, non-permissible income is
    5%+, or interest-bearing debt/securities exceed 33% of market cap.
    نقي when those ratios are near zero. Otherwise مختلط (passed the 5%/33%
    gates but still needs purification).
    """

    if core_prohibited:
        return "PROHIBITED"
    impure = _ratio(impure_income_ratio)
    debt = _ratio(debt_ratio)
    securities = _ratio(interest_securities_ratio)
    # AAOIFI-style: ratios must not exceed 5% / 33%. Equality still passes the gate.
    if impure > MAX_IMPURE_INCOME or debt > MAX_DEBT_RATIO or securities > MAX_INTEREST_SECURITIES:
        return "PROHIBITED"
    if impure <= PURE_IMPURE_INCOME and debt <= PURE_DEBT_RATIO and securities <= PURE_DEBT_RATIO:
        return "PURE"
    return "MIXED"


def classified_status(symbol: str) -> str | None:
    ticker = (symbol or "").strip().upper()
    if not ticker:
        return None
    overlay = _status_overlay.get(ticker)
    if overlay:
        return overlay
    for item in compliance_universe():
        if str(item.get("symbol") or "").strip().upper() != ticker:
            continue
        stored = str(item.get("currentStatus") or "").strip().upper()
        debt = _float(item.get("debtRatio") or item.get("debt_ratio"))
        impure = _float(item.get("impureIncomeRatio") or item.get("impure_income_ratio"))
        securities = _float(item.get("interestSecuritiesRatio") or item.get("interest_securities_ratio"))
        computed = classify_shariah(
            debt_ratio=debt,
            impure_income_ratio=impure,
            interest_securities_ratio=securities,
            core_prohibited=stored == "PROHIBITED",
        )
        if stored == "PROHIBITED":
            return "PROHIBITED"
        if debt is None and impure is None and securities is None:
            return stored or computed
        return computed or stored
    return None


def is_pure(symbol: str) -> bool:
    return classified_status(symbol) == "PURE"


def shariah_label(symbol: str) -> str:
    status = classified_status(symbol) or ""
    return STATUS_AR.get(status, "")


def screen_universe(*, pure_only: bool = False) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in compliance_universe():
        symbol = str(item.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        status = classified_status(symbol)
        if status == "PROHIBITED":
            continue
        if pure_only and status != "PURE":
            continue
        rows.append(
            {
                "symbol": symbol,
                "name": company_name_for(symbol) or item.get("companyNameAr") or symbol,
                "sector": str(item.get("sector") or sector_for(symbol) or "أخرى"),
                "status": status,
                "status_ar": STATUS_AR.get(status or "", ""),
                "debt_ratio": _float(item.get("debtRatio")),
                "impure_income_ratio": _float(item.get("impureIncomeRatio")),
                "purification_rate": _float(item.get("purificationRate")),
            }
        )
    return rows


def _ratio(value: float | None) -> float:
    if value is None:
        return 0.0
    return max(0.0, float(value))


def _float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def sector_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in compliance_universe():
        symbol = str(item.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        mapping[symbol] = str(item.get("sector") or "أخرى").strip() or "أخرى"
    return mapping


def sector_for(symbol: str) -> str:
    ticker = (symbol or "").strip().upper()
    return sector_map().get(ticker, "أخرى")


def company_name_for(symbol: str) -> str:
    ticker = (symbol or "").strip().translate(_ARABIC_DIGITS).upper()
    if not ticker:
        return ""
    listed = listed_name_map().get(ticker)
    if listed:
        return listed
    for item in compliance_universe():
        if str(item.get("symbol") or "").strip().upper() != ticker:
            continue
        name = str(item.get("companyNameAr") or item.get("name") or "").strip()
        return name or ticker
    return ticker


@lru_cache(maxsize=1)
def listed_name_map() -> dict[str, str]:
    names: dict[str, str] = {}
    for item in compliance_universe():
        symbol = str(item.get("symbol") or "").strip().upper()
        label = str(item.get("companyNameAr") or item.get("name") or "").strip()
        if symbol and label:
            names[symbol] = label
    if _LISTED_NAMES_PATH.exists():
        try:
            payload = json.loads(_LISTED_NAMES_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        if isinstance(payload, dict):
            for symbol, label in payload.items():
                ticker = str(symbol).strip().upper()
                name = str(label or "").strip()
                if ticker and name:
                    names[ticker] = name
    return names


def _norm_query(value: str) -> str:
    text = value.strip().translate(_ARABIC_DIGITS).translate(_ALEF)
    text = re.sub(r"[\s\-_./]+", "", text)
    text = text.replace("ة", "ه").replace("ى", "ي")
    if text.startswith("ال") and len(text) > 3:
        text = text[2:]
    return text.casefold()


def search_listed_companies(query: str, *, limit: int = 8) -> list[tuple[str, str]]:
    needle = _norm_query(query)
    if not needle or len(needle) < 2:
        return []
    ranked: list[tuple[int, str, str]] = []
    for symbol, name in listed_name_map().items():
        hay = _norm_query(f"{symbol}{name}")
        if needle == _norm_query(symbol) or needle == _norm_query(name):
            ranked.append((0, symbol, name))
        elif hay.startswith(needle) or _norm_query(name).startswith(needle):
            ranked.append((1, symbol, name))
        elif needle in hay:
            ranked.append((2, symbol, name))
    ranked.sort(key=lambda item: (item[0], len(item[2]), item[1]))
    seen: set[str] = set()
    matches: list[tuple[str, str]] = []
    for _, symbol, name in ranked:
        if symbol in seen:
            continue
        seen.add(symbol)
        matches.append((symbol, name))
        if len(matches) >= limit:
            break
    return matches


def resolve_listed_company(query: str) -> tuple[str, str] | None:
    raw = (query or "").strip()
    if not raw:
        return None
    ticker = raw.translate(_ARABIC_DIGITS).upper()
    if _SYMBOL_RE.fullmatch(ticker):
        return ticker, company_name_for(ticker)
    matches = search_listed_companies(raw, limit=8)
    if not matches:
        return None
    exact = [item for item in matches if _norm_query(item[1]) == _norm_query(raw) or item[1] == raw]
    if len(exact) == 1:
        return exact[0]
    if len(matches) == 1:
        return matches[0]
    return None
