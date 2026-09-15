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
    overlay = _status_overlay.get(ticker)
    if overlay is not None:
        return overlay == "PROHIBITED"
    return ticker in prohibited_symbols()


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
