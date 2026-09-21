"""Persist the first دخول print so entry/target/stop never chase live ticks."""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from app.services.signals import is_valid_long_plan, keep_long_recommendations, long_trade_levels
from app.services.tasi_clock import now_riyadh

_DEFAULT_PATH = Path("data/entry_snapshots.json")
_SCHEMA_VERSION = 1


def _positive(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _fmt(value: float) -> str:
    return f"{float(value):.2f}"


def _key(scan_mode: str, session_date: str, symbol: str) -> str:
    return f"{scan_mode}:{session_date}:{symbol}"


class EntrySnapshotStore:
    """Session-scoped lock of the first valid long entry for each symbol."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _DEFAULT_PATH
        self._guard = threading.RLock()
        self._rows: dict[str, dict[str, Any]] = {}
        self._load()

    def lock(
        self,
        *,
        symbol: str,
        scan_mode: str,
        session_date: str,
        entry_price: Any,
        target_price: Any,
        stop_loss: Any,
        atr: Any = None,
        signal_kind: str | None = None,
    ) -> dict[str, Any] | None:
        ticker = str(symbol or "").strip().upper()
        mode = str(scan_mode or "live").strip() or "live"
        day = str(session_date or "").strip() or now_riyadh().date().isoformat()
        if not ticker:
            return None
        entry = _positive(entry_price)
        if entry is None:
            return None
        token = _key(mode, day, ticker)
        with self._guard:
            existing = self._rows.get(token)
            if existing:
                return dict(existing)
            target = _positive(target_price)
            stop = _positive(stop_loss)
            if not is_valid_long_plan(entry, target, stop):
                computed_target, computed_stop = long_trade_levels(entry, atr=atr)
                target = float(computed_target)
                stop = float(computed_stop)
            if not is_valid_long_plan(entry, target, stop):
                return None
            row = {
                "symbol": ticker,
                "scan_mode": mode,
                "session_date": day,
                "entry_price": round(entry, 4),
                "target_price": round(float(target), 4),
                "stop_loss": round(float(stop), 4),
                "atr": _positive(atr),
                "signal_kind": signal_kind,
                "status": "open",
                "triggered_at": now_riyadh().isoformat(),
            }
            self._rows[token] = row
            self._save()
            return dict(row)

    def complete(self, *, symbol: str, scan_mode: str, session_date: str) -> None:
        ticker = str(symbol or "").strip().upper()
        mode = str(scan_mode or "live").strip() or "live"
        day = str(session_date or "").strip()
        token = _key(mode, day, ticker)
        with self._guard:
            row = self._rows.get(token)
            if not row:
                return
            row["status"] = "completed"
            row["completed_at"] = now_riyadh().isoformat()
            self._save()

    def retain(self, scan_mode: str, session_date: str, symbols: Iterable[str]) -> None:
        """Keep open locks for the session. Forget completed names once they leave the scan."""

        mode = str(scan_mode or "live").strip() or "live"
        day = str(session_date or "").strip()
        scanned = {str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()}
        with self._guard:
            stale: list[str] = []
            for token, row in self._rows.items():
                if str(row.get("scan_mode")) != mode:
                    continue
                if str(row.get("session_date")) != day:
                    stale.append(token)
                    continue
                ticker = str(row.get("symbol") or "").upper()
                if str(row.get("status") or "open") == "completed" and ticker not in scanned:
                    stale.append(token)
            if not stale:
                return
            for token in stale:
                self._rows.pop(token, None)
            self._save()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        rows = payload.get("data") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            return
        loaded: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "").strip().upper()
            mode = str(row.get("scan_mode") or "live")
            day = str(row.get("session_date") or "")
            if not symbol or not day:
                continue
            loaded[_key(mode, day, symbol)] = dict(row)
        self._rows = loaded

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": _SCHEMA_VERSION,
            "saved_at": datetime.now().isoformat(),
            "data": list(self._rows.values()),
        }
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def apply_locked_entries(
    rows: list[dict[str, Any]] | None,
    *,
    store: EntrySnapshotStore,
    scan_mode: str,
    session_date: str | None = None,
    last_prices: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Freeze entry/target/stop, hide names that already hit target, and allow a later fresh setup."""

    day = session_date or now_riyadh().date().isoformat()
    mode = str(scan_mode or "live")
    kept: list[dict[str, Any]] = []
    scanned: list[str] = []
    for raw in rows or []:
        if not isinstance(raw, dict):
            continue
        symbol = str(raw.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        scanned.append(symbol)
        last = _positive((last_prices or {}).get(symbol))
        if last is None:
            last = _positive(raw.get("last_price") or raw.get("close_price") or raw.get("entry_price"))
        candidate = _positive(raw.get("entry_price")) or last
        locked = store.lock(
            symbol=symbol,
            scan_mode=mode,
            session_date=day,
            entry_price=candidate,
            target_price=raw.get("target_price"),
            stop_loss=raw.get("stop_loss"),
            atr=raw.get("atr"),
            signal_kind=str(raw.get("signal_kind") or "") or None,
        )
        if locked is None:
            continue
        if str(locked.get("status") or "open") == "completed":
            continue
        last_now = float(last if last is not None else locked["entry_price"])
        target_now = float(locked["target_price"])
        stop_now = float(locked["stop_loss"])
        if last_now >= target_now or last_now <= stop_now:
            store.complete(symbol=symbol, scan_mode=mode, session_date=day)
            continue
        row = dict(raw)
        row["last_price"] = round(last_now, 2)
        row["close_price"] = round(last_now, 2)
        row["entry_price"] = _fmt(float(locked["entry_price"]))
        row["target_price"] = _fmt(target_now)
        row["stop_loss"] = _fmt(stop_now)
        row["entry_locked_at"] = locked.get("triggered_at")
        row["target_hit"] = False
        row["stop_hit"] = False
        kept.append(row)
    store.retain(mode, day, scanned)
    return keep_long_recommendations(kept)


def live_last_index(quotes: Any, tapes: Mapping[str, Any] | None = None) -> dict[str, float]:
    """Best live last print from the quote book and in-memory tapes."""

    index: dict[str, float] = {}
    snapshot = quotes.snapshot() if quotes is not None and hasattr(quotes, "snapshot") else []
    for row in snapshot or []:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        last = _positive(row.get("last_price") or row.get("close") or row.get("price"))
        if symbol and last is not None:
            index[symbol] = last
    for symbol, tape in (tapes or {}).items():
        ticker = str(symbol or "").strip().upper()
        snap = tape.snapshot() if tape is not None and hasattr(tape, "snapshot") else None
        last = _positive((snap or {}).get("last_price") if isinstance(snap, dict) else None)
        if ticker and last is not None:
            index[ticker] = last
    return index
