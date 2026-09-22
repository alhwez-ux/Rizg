"""Daily Sahm/SAHMK REST budget so the free-tier 100-request cap is never blown."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from app.services.tasi_clock import now_riyadh

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path("data/sahm_quota.json")
_DEFAULT_LIMIT = 90
_LOCK = threading.RLock()
_INSTANCE: "SahmQuota | None" = None


class SahmQuota:
    """Persisted Riyadh-day REST counter shared by every Sahm caller."""

    def __init__(
        self,
        *,
        daily_limit: int = _DEFAULT_LIMIT,
        path: Path | None = None,
    ) -> None:
        self._limit = max(1, int(daily_limit))
        self._path = path
        self._guard = threading.RLock()
        self._day = ""
        self._used = 0
        self._exhausted = False
        self._reason = ""
        self._load()

    def snapshot(self) -> dict[str, Any]:
        self._roll()
        with self._guard:
            remaining = max(0, self._limit - self._used)
            return {
                "day": self._day,
                "limit": self._limit,
                "used": self._used,
                "remaining": remaining,
                "exhausted": self._exhausted or remaining <= 0,
                "reason": self._reason,
            }

    def remaining(self) -> int:
        return int(self.snapshot()["remaining"])

    def exhausted(self) -> bool:
        return bool(self.snapshot()["exhausted"])

    def allow(self, count: int = 1) -> bool:
        needed = max(1, int(count))
        self._roll()
        with self._guard:
            if self._exhausted:
                return False
            return self._used + needed <= self._limit

    def consume(self, count: int = 1) -> int:
        needed = max(1, int(count))
        self._roll()
        with self._guard:
            self._used += needed
            if self._used >= self._limit:
                self._exhausted = True
                self._reason = self._reason or "daily_limit"
            remaining = max(0, self._limit - self._used)
            self._persist()
            return remaining

    def trip(self, reason: str = "rate_limit") -> None:
        self._roll()
        with self._guard:
            self._exhausted = True
            self._reason = reason or "rate_limit"
            if self._used < self._limit:
                self._used = self._limit
            self._persist()
        logger.warning("Sahm REST quota exhausted reason=%s day=%s used=%s", reason, self._day, self._used)

    def _roll(self) -> None:
        today = now_riyadh().date().isoformat()
        with self._guard:
            if self._day == today:
                return
            self._day = today
            self._used = 0
            self._exhausted = False
            self._reason = ""
            self._persist()

    def _load(self) -> None:
        today = now_riyadh().date().isoformat()
        if self._path is None:
            raw = {}
        else:
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                raw = {}
        with self._guard:
            stored_day = str(raw.get("day") or "")
            if stored_day == today:
                self._day = stored_day
                self._used = max(0, int(raw.get("used") or 0))
                self._exhausted = bool(raw.get("exhausted"))
                self._reason = str(raw.get("reason") or "")
            else:
                self._day = today
                self._used = 0
                self._exhausted = False
                self._reason = ""

    def _persist(self) -> None:
        if self._path is None:
            return
        payload = {
            "day": self._day,
            "used": self._used,
            "exhausted": self._exhausted,
            "reason": self._reason,
            "limit": self._limit,
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(payload), encoding="utf-8")
        except OSError:
            logger.debug("sahm quota persist skipped", exc_info=True)


def get_sahm_quota(*, daily_limit: int | None = None, path: Path | None = None) -> SahmQuota:
    global _INSTANCE
    with _LOCK:
        if _INSTANCE is None:
            _INSTANCE = SahmQuota(
                daily_limit=daily_limit or _DEFAULT_LIMIT,
                path=path if path is not None else _DEFAULT_PATH,
            )
        elif daily_limit is not None:
            _INSTANCE._limit = max(1, int(daily_limit))
        return _INSTANCE


def set_sahm_quota_for_tests(quota: SahmQuota) -> SahmQuota:
    global _INSTANCE
    with _LOCK:
        _INSTANCE = quota
        return quota


def reset_sahm_quota_for_tests() -> None:
    global _INSTANCE
    with _LOCK:
        _INSTANCE = None
