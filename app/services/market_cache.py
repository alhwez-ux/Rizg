from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Any


class MarketCache:
    """In-memory last-known quotes and market lists for TASI batch scanning.

    Used when SAHMK returns HTTP 429 or a network error so the screener and
    WebSocket keep serving the last verified snapshot instead of crashing.
    """

    def __init__(self, *, ttl_seconds: float = 180) -> None:
        self._ttl = timedelta(seconds=max(ttl_seconds, 5))
        self._guard = threading.RLock()
        self._quotes: dict[str, tuple[datetime, dict[str, Any]]] = {}
        self._markets: dict[str, tuple[datetime, dict[str, Any]]] = {}
        self._cool_until: datetime | None = None

    def put_quote(self, symbol: str, payload: dict[str, Any]) -> None:
        ticker = symbol.strip().upper()
        if not ticker or not payload:
            return
        with self._guard:
            self._quotes[ticker] = (datetime.now(timezone.utc), dict(payload))

    def get_quote(self, symbol: str, *, allow_stale: bool = True) -> dict[str, Any] | None:
        ticker = symbol.strip().upper()
        with self._guard:
            item = self._quotes.get(ticker)
        return _unwrap(item, self._ttl, allow_stale=allow_stale)

    def put_market(self, key: str, payload: dict[str, Any]) -> None:
        if not key or not payload:
            return
        with self._guard:
            self._markets[key] = (datetime.now(timezone.utc), dict(payload))

    def get_market(self, key: str, *, allow_stale: bool = True) -> dict[str, Any] | None:
        with self._guard:
            item = self._markets.get(key)
        return _unwrap(item, self._ttl, allow_stale=allow_stale)

    def trip_rate_limit(self, retry_after_seconds: float | None = None) -> float:
        wait = 30.0 if retry_after_seconds is None else max(5.0, float(retry_after_seconds))
        wait = min(wait, 180.0)
        until = datetime.now(timezone.utc) + timedelta(seconds=wait)
        with self._guard:
            if self._cool_until is None or until > self._cool_until:
                self._cool_until = until
        return wait

    def cooling_down(self) -> bool:
        with self._guard:
            until = self._cool_until
        if until is None:
            return False
        if datetime.now(timezone.utc) >= until:
            with self._guard:
                if self._cool_until is not None and datetime.now(timezone.utc) >= self._cool_until:
                    self._cool_until = None
            return False
        return True

    def cooldown_remaining(self) -> float:
        with self._guard:
            until = self._cool_until
        if until is None:
            return 0.0
        remaining = (until - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, remaining)


def _unwrap(
    item: tuple[datetime, dict[str, Any]] | None,
    ttl: timedelta,
    *,
    allow_stale: bool,
) -> dict[str, Any] | None:
    if item is None:
        return None
    stored_at, payload = item
    if not allow_stale and datetime.now(timezone.utc) - stored_at > ttl:
        return None
    return dict(payload)
