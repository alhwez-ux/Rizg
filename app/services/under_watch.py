"""Dynamically flagged Under Watch names (explosive momentum / accumulation)."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping

from app.models.screener import is_tasi_main_symbol, normalize_tasi_symbol
from app.services.explosive_momentum import ExplosiveDecision, ExplosiveInputs, evaluate_explosive
from app.services.shariah import company_name_for, is_prohibited, sector_for

_DEFAULT_PATH = Path("data/under_watch.json")
_GRACE_SECONDS = 8 * 60
_MAX_AGE_SECONDS = 6 * 60 * 60
_MAX_SYMBOLS = 24


class UnderWatchService:
    """Session-scoped auto watchlist. Names drop when the setup fades."""

    def __init__(self, path: Path | None = None, *, max_symbols: int = _MAX_SYMBOLS) -> None:
        self._path = path or _DEFAULT_PATH
        self._max = max_symbols
        self._guard = threading.RLock()
        self._rows: dict[str, dict[str, Any]] = {}
        self._load()

    def symbols(self) -> list[str]:
        with self._guard:
            self._prune_locked()
            return [row["symbol"] for row in self._sorted_locked()]

    def contains(self, symbol: str) -> bool:
        ticker = str(symbol or "").strip().upper()
        with self._guard:
            self._prune_locked()
            return ticker in self._rows

    def snapshot(self) -> list[dict[str, Any]]:
        with self._guard:
            self._prune_locked()
            return [dict(row) for row in self._sorted_locked()]

    def upsert(
        self,
        inputs: ExplosiveInputs,
        decision: ExplosiveDecision | None = None,
        *,
        extra: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        verdict = decision or evaluate_explosive(inputs)
        if not verdict.watch or not verdict.flag:
            return None
        ticker = str(inputs.symbol or "").strip().upper()
        try:
            ticker = normalize_tasi_symbol(ticker)
        except ValueError:
            if not is_tasi_main_symbol(ticker):
                return None
        if is_prohibited(ticker):
            return None
        now = datetime.now(timezone.utc)
        payload = _row_payload(ticker, inputs, verdict, extra, now)
        with self._guard:
            existing = self._rows.get(ticker)
            if existing:
                payload["first_seen_at"] = existing.get("first_seen_at") or payload["first_seen_at"]
            changed = (
                existing is None
                or existing.get("flag") != payload["flag"]
                or existing.get("explosive") != payload["explosive"]
            )
            self._rows[ticker] = payload
            self._cap_locked()
            if changed:
                self._save_locked()
            return dict(self._rows[ticker])

    def observe(self, inputs: ExplosiveInputs, *, extra: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
        decision = evaluate_explosive(inputs)
        if decision.watch:
            return self.upsert(inputs, decision, extra=extra)
        self.miss(inputs.symbol)
        return None

    def miss(self, symbol: str) -> None:
        ticker = str(symbol or "").strip().upper()
        with self._guard:
            row = self._rows.get(ticker)
            if row is None:
                return
            # Keep the card until grace expires; last_hit_at stays as the last confirmation.

    def retain(self, active: Iterable[str]) -> list[dict[str, Any]]:
        alive = {str(symbol or "").strip().upper() for symbol in active if str(symbol or "").strip()}
        now = datetime.now(timezone.utc)
        with self._guard:
            drop: list[str] = []
            for ticker, row in self._rows.items():
                if ticker in alive:
                    row["last_hit_at"] = now.isoformat()
                    continue
                if _stale(row, now):
                    drop.append(ticker)
            for ticker in drop:
                self._rows.pop(ticker, None)
            if drop:
                self._save_locked()
            return [dict(row) for row in self._sorted_locked()]

    def _sorted_locked(self) -> list[dict[str, Any]]:
        return sorted(
            self._rows.values(),
            key=lambda row: (bool(row.get("explosive")), float(row.get("score") or 0), abs(float(row.get("net_flow") or 0))),
            reverse=True,
        )

    def _cap_locked(self) -> None:
        ranked = self._sorted_locked()
        if len(ranked) <= self._max:
            return
        keep = {row["symbol"] for row in ranked[: self._max]}
        self._rows = {symbol: row for symbol, row in self._rows.items() if symbol in keep}

    def _prune_locked(self) -> None:
        now = datetime.now(timezone.utc)
        stale = [ticker for ticker, row in self._rows.items() if _stale(row, now, age_only=True)]
        for ticker in stale:
            self._rows.pop(ticker, None)

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        rows = payload.get("rows", payload) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            return
        now = datetime.now(timezone.utc)
        loaded: dict[str, dict[str, Any]] = {}
        for item in rows:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "").strip().upper()
            if not is_tasi_main_symbol(symbol) or is_prohibited(symbol):
                continue
            if _stale(item, now, age_only=True):
                continue
            loaded[symbol] = item
        self._rows = loaded

    def _save_locked(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"rows": list(self._rows.values())}
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        tmp.replace(self._path)


def _row_payload(
    symbol: str,
    inputs: ExplosiveInputs,
    decision: ExplosiveDecision,
    extra: Mapping[str, Any] | None,
    now: datetime,
) -> dict[str, Any]:
    extras = dict(extra or {})
    name = inputs.name or extras.get("name") or company_name_for(symbol) or symbol
    return {
        "symbol": symbol,
        "name": name,
        "sector": extras.get("sector") or sector_for(symbol),
        "price": _json_number(inputs.price),
        "change_percent": _json_number(inputs.change_percent),
        "volume": _json_number(inputs.volume),
        "volume_ratio": _json_number(decision.volume_ratio),
        "net_flow": _json_number(inputs.net_flow),
        "buy_ratio": _buy_ratio(inputs),
        "flag": decision.flag,
        "explosive": decision.explosive,
        "compressed": decision.compressed,
        "upward": decision.upward,
        "aggressive_buy": decision.aggressive_buy,
        "flow_spike": decision.flow_spike,
        "resistance_break": decision.resistance_break,
        "score": _json_number(decision.score) or 0,
        "reasons": list(decision.reasons),
        "first_seen_at": now.isoformat(),
        "last_hit_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }


def _buy_ratio(inputs: ExplosiveInputs) -> float | None:
    buy = inputs.buy_volume
    sell = inputs.sell_volume
    if buy is None or sell is None:
        buy = inputs.inflow
        sell = inputs.outflow
    if buy is None or sell is None:
        return None
    total = buy + sell
    if total <= 0:
        return None
    return float(buy / total)


def _stale(row: Mapping[str, Any], now: datetime, *, age_only: bool = False) -> bool:
    last = _parse_time(row.get("last_hit_at") or row.get("updated_at"))
    first = _parse_time(row.get("first_seen_at") or row.get("updated_at"))
    if first is not None and (now - first).total_seconds() > _MAX_AGE_SECONDS:
        return True
    if age_only:
        return False
    if last is None:
        return True
    return (now - last).total_seconds() > _GRACE_SECONDS


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _json_number(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None
