"""Persist the last recorded TickChart print so closed-session views stay populated."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DEFAULT_PATH = Path("data/tickchart_last_quotes.json")


class LastQuoteBook:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _DEFAULT_PATH
        self._guard = threading.RLock()
        self._quotes: dict[str, dict[str, Any]] = {}
        self._load()

    def remember(self, symbol: str, price: Any, *, volume: Any = None) -> None:
        ticker = str(symbol or "").strip().upper()
        try:
            number = float(price)
        except (TypeError, ValueError):
            return
        if not ticker or number <= 0:
            return
        row: dict[str, Any] = {
            "symbol": ticker,
            "last_price": number,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            qty = float(volume) if volume is not None else None
        except (TypeError, ValueError):
            qty = None
        if qty:
            row["volume"] = qty
        with self._guard:
            self._quotes[ticker] = row
            self._save()

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

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        rows = payload.get("quotes") if isinstance(payload, dict) else payload
        if not isinstance(rows, dict):
            return
        for key, value in rows.items():
            if isinstance(value, dict) and value.get("last_price"):
                self._quotes[str(key).upper()] = dict(value)

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"quotes": self._quotes}
        self._path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
