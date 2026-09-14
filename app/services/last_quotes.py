"""Persist last TickChart prints and rolling daily close/volume history."""

from __future__ import annotations

import json
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app.services.tasi_clock import now_riyadh

_DEFAULT_PATH = Path("data/tickchart_last_quotes.json")
_HISTORY_LIMIT = 40


class LastQuoteBook:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _DEFAULT_PATH
        self._guard = threading.RLock()
        self._quotes: dict[str, dict[str, Any]] = {}
        self._history: dict[str, list[dict[str, Any]]] = {}
        self._load()

    def remember(self, symbol: str, price: Any, *, volume: Any = None, session_date: date | None = None) -> None:
        self.apply_closes(
            [
                {
                    "symbol": symbol,
                    "last_price": price,
                    "volume": volume,
                    "session_date": session_date,
                }
            ],
            accumulate_volume=True,
        )

    def apply_closes(self, rows: list[dict[str, Any]], *, accumulate_volume: bool = False) -> int:
        """Store last-close quotes in one write. Volume is replaced unless accumulating prints."""

        applied = 0
        day_default = now_riyadh().date()
        with self._guard:
            for item in rows:
                ticker, number, extras = _close_row(item)
                if not ticker or number is None:
                    continue
                qty = extras.get("volume")
                session_date = extras.pop("session_date", None)
                day = (session_date if isinstance(session_date, date) else day_default).isoformat()
                row: dict[str, Any] = {
                    "symbol": ticker,
                    "last_price": number,
                    "at": datetime.now(timezone.utc).isoformat(),
                }
                if qty and qty > 0:
                    row["volume"] = qty
                for key in ("value_traded", "change_percent"):
                    value = extras.get(key)
                    if value is not None:
                        row[key] = value
                previous = self._quotes.get(ticker) or {}
                if not accumulate_volume:
                    for key in ("volume", "value_traded", "change_percent"):
                        if row.get(key) is None and previous.get(key) is not None:
                            row[key] = previous[key]
                self._quotes[ticker] = row
                bars = list(self._history.get(ticker) or [])
                if bars and str(bars[-1].get("date")) == day:
                    bars[-1]["close"] = number
                    if qty and qty > 0:
                        current = float(bars[-1].get("volume") or 0)
                        bars[-1]["volume"] = current + qty if accumulate_volume else qty
                else:
                    bars.append({"date": day, "close": number, "volume": qty if qty and qty > 0 else 0.0})
                self._history[ticker] = bars[-_HISTORY_LIMIT:]
                applied += 1
            if applied:
                self._save()
        return applied

    def get(self, symbol: str) -> dict[str, Any] | None:
        ticker = str(symbol or "").strip().upper()
        with self._guard:
            row = self._quotes.get(ticker)
            return dict(row) if row else None

    def price(self, symbol: str) -> float | None:
        row = self.get(symbol)
        if not row:
            return None
        try:
            number = float(row.get("last_price"))
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    def snapshot(self) -> list[dict[str, Any]]:
        with self._guard:
            return [dict(row) for row in self._quotes.values()]

    def close_history(self, symbol: str) -> list[dict[str, Any]]:
        ticker = str(symbol or "").strip().upper()
        with self._guard:
            return [dict(row) for row in self._history.get(ticker) or []]

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        rows = payload.get("quotes") if isinstance(payload, dict) else payload
        history = payload.get("history") if isinstance(payload, dict) else {}
        if isinstance(rows, dict):
            for key, value in rows.items():
                if isinstance(value, dict) and value.get("last_price"):
                    self._quotes[str(key).upper()] = dict(value)
        if isinstance(history, dict):
            for key, bars in history.items():
                if isinstance(bars, list):
                    self._history[str(key).upper()] = [dict(bar) for bar in bars if isinstance(bar, dict)]

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"quotes": self._quotes, "history": self._history}
        self._path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _close_row(item: dict[str, Any]) -> tuple[str, float | None, dict[str, Any]]:
    ticker = str(item.get("symbol") or "").strip().upper()
    price = _positive(item.get("last_price") or item.get("close") or item.get("price"))
    extras: dict[str, Any] = {
        "volume": _positive(item.get("volume") or item.get("session_volume")),
        "value_traded": _positive(item.get("value_traded") or item.get("session_value")),
        "change_percent": _number(item.get("change_percent") or item.get("price_change_pct")),
        "session_date": item.get("session_date"),
    }
    return ticker, price, extras


def _positive(value: Any) -> float | None:
    number = _number(value)
    return number if number is not None and number > 0 else None


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or abs(number) == float("inf"):
        return None
    return number
