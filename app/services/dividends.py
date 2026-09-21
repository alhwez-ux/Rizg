"""TASI cash-dividend calendar. Only names still eligible today stay on the tape."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.models.screener import is_tasi_main_symbol
from app.services.shariah import classified_status, company_name_for, is_prohibited, sector_for, shariah_label
from app.services.tasi_clock import add_tasi_calendar_days, now_riyadh

_DATA_PATH = Path("data/tasi_dividends.json")
_BUNDLED_PATH = Path(__file__).resolve().parents[1] / "data" / "tasi_dividends.json"

# Offsets from the Riyadh session date so the sample book always has live + expired rows.
_SAMPLE: tuple[dict[str, Any], ...] = (
    {"symbol": "2222", "cash_dividend": 0.438, "eligibility_offset": 9, "payment_offset": 23},
    {"symbol": "1120", "cash_dividend": 1.25, "eligibility_offset": 4, "payment_offset": 18},
    {"symbol": "1150", "cash_dividend": 0.55, "eligibility_offset": 14, "payment_offset": 30},
    {"symbol": "7010", "cash_dividend": 0.40, "eligibility_offset": 2, "payment_offset": 16},
    {"symbol": "4190", "cash_dividend": 1.80, "eligibility_offset": 21, "payment_offset": 40},
    {"symbol": "2280", "cash_dividend": 0.50, "eligibility_offset": 7, "payment_offset": 22},
    {"symbol": "2020", "cash_dividend": 2.00, "eligibility_offset": 11, "payment_offset": 27},
    {"symbol": "4030", "cash_dividend": 0.75, "eligibility_offset": 16, "payment_offset": 32},
    {"symbol": "1140", "cash_dividend": 0.80, "eligibility_offset": 6, "payment_offset": 20},
    {"symbol": "8230", "cash_dividend": 0.35, "eligibility_offset": 19, "payment_offset": 35},
    {"symbol": "2010", "cash_dividend": 1.10, "eligibility_offset": -2, "payment_offset": 12},
    {"symbol": "1180", "cash_dividend": 0.90, "eligibility_offset": 8, "payment_offset": 24},
    {"symbol": "1010", "cash_dividend": 0.70, "eligibility_offset": 5, "payment_offset": 19},
    {"symbol": "5110", "cash_dividend": 0.70, "eligibility_offset": -10, "payment_offset": -1},
)


def active_dividends(*, today: date | None = None, pure_only: bool = False) -> list[dict[str, Any]]:
    """Return TASI names whose eligibility date is still today or later."""

    cutoff = today or now_riyadh().date()
    rows: list[dict[str, Any]] = []
    for item in load_dividend_book(as_of=cutoff):
        ticker = str(item.get("symbol") or "").strip().upper()
        eligibility = _as_date(item.get("eligibility_date"))
        if not ticker or not is_tasi_main_symbol(ticker) or eligibility is None:
            continue
        if eligibility < cutoff:
            continue
        if is_prohibited(ticker):
            continue
        status = classified_status(ticker)
        if pure_only and status != "PURE":
            continue
        payment = _as_date(item.get("payment_date") or item.get("distribution_date"))
        cash = _cash(item.get("cash_dividend") or item.get("amount_per_share") or item.get("dividend_per_share"))
        if cash is None or cash <= 0:
            continue
        rows.append(
            {
                "symbol": ticker,
                "name": str(item.get("name") or company_name_for(ticker) or ticker),
                "sector": str(item.get("sector") or sector_for(ticker) or "أخرى"),
                "cash_dividend": round(cash, 4),
                "eligibility_date": eligibility.isoformat(),
                "payment_date": (payment or eligibility).isoformat(),
                "shariah_status": status,
                "shariah_label": shariah_label(ticker) or item.get("shariah_label") or "",
                "days_to_eligibility": (eligibility - cutoff).days,
            }
        )
    rows.sort(key=lambda row: (str(row["eligibility_date"]), str(row["symbol"])))
    return rows


def load_dividend_book(*, as_of: date | None = None) -> list[dict[str, Any]]:
    cutoff = as_of or now_riyadh().date()
    loaded = _read_json(_DATA_PATH) or _read_json(_BUNDLED_PATH)
    if loaded:
        return list(loaded)
    return [_materialize(item, cutoff) for item in _SAMPLE]


def _materialize(item: dict[str, Any], as_of: date) -> dict[str, Any]:
    ticker = str(item.get("symbol") or "").strip().upper()
    elig = add_tasi_calendar_days(as_of, int(item.get("eligibility_offset") or 0))
    pay = add_tasi_calendar_days(as_of, int(item.get("payment_offset") or 0))
    if pay < elig:
        pay = add_tasi_calendar_days(elig, 10)
    return {
        "symbol": ticker,
        "name": company_name_for(ticker) or ticker,
        "sector": sector_for(ticker),
        "cash_dividend": float(item.get("cash_dividend") or 0),
        "eligibility_date": elig.isoformat(),
        "payment_date": pay.isoformat(),
    }


def _read_json(path: Path) -> list[dict[str, Any]] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    rows = payload.get("dividends", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return None
    return [row for row in rows if isinstance(row, dict)]


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


def _cash(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None
