from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_CANDIDATES = (
    _ROOT / "web" / "prisma" / "tasi-universe.json",
    _ROOT / "data" / "tasi_compliance.json",
)
_status_overlay: dict[str, str] = {}


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
    ticker = (symbol or "").strip().upper()
    if not ticker:
        return ""
    for item in compliance_universe():
        if str(item.get("symbol") or "").strip().upper() != ticker:
            continue
        name = str(item.get("companyNameAr") or item.get("name") or "").strip()
        return name or ticker
    return ticker
