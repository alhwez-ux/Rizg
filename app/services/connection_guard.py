"""Gate live ingestion on backend health, an active plan, and a real client."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

HEARTBEAT_TTL_SECONDS = 30.0
_TERMINAL_MARKERS = (
    "plan is inactive",
    "plan inactive",
    "subscription inactive",
    "subscription is inactive",
    "invalid api",
    "invalid api key",
    "unauthorized",
    "authentication",
    "forbidden",
    "api key",
)


OWNER_ID = "owner"


class ConnectionGuard:
    """Gates live feeds on the single project owner being present."""

    def __init__(self, *, plan_active: bool = True, plan_reason: str | None = None) -> None:
        self._healthy = True
        self._plan_active = plan_active
        self._plan_reason = plan_reason
        self._owner_seen: float | None = None
        self._owner_sockets = 0
        self._lock = threading.Lock()
        self._event: asyncio.Event | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        del loop
        self._event = asyncio.Event()

    @property
    def healthy(self) -> bool:
        return self._healthy

    @property
    def plan_active(self) -> bool:
        return self._plan_active

    @property
    def plan_reason(self) -> str | None:
        return self._plan_reason

    @property
    def is_connected(self) -> bool:
        return self._healthy and self._plan_active and self.client_count() > 0

    def snapshot(self) -> dict[str, Any]:
        return {
            "healthy": self._healthy,
            "plan_active": self._plan_active,
            "plan_reason": self._plan_reason,
            "clients": self.client_count(),
            "owner": OWNER_ID,
            "is_connected": self.is_connected,
        }

    def client_count(self) -> int:
        """The project has one client: the owner. Returns 1 only while that session is present."""

        with self._lock:
            self._drop_stale_owner()
            present = self._owner_seen is not None or self._owner_sockets > 0
        return 1 if present else 0

    def beat(self, client_id: str = OWNER_ID) -> None:
        del client_id
        if not self._healthy or not self._plan_active:
            return
        with self._lock:
            self._owner_seen = time.monotonic()
        self._notify()

    def release(self, client_id: str = OWNER_ID) -> None:
        del client_id
        with self._lock:
            self._owner_seen = None
        self._notify()

    def note_websocket(self, delta: int) -> None:
        with self._lock:
            self._owner_sockets = max(0, self._owner_sockets + int(delta))
        self._notify()

    def mark_plan_inactive(self, reason: str) -> None:
        text = (reason or "plan_inactive").strip()[:180]
        changed = self._plan_active or self._plan_reason != text
        self._plan_active = False
        self._plan_reason = text
        with self._lock:
            self._owner_seen = None
        if changed:
            logger.warning("live feeds paused: %s", text)
        self._notify()

    def mark_plan_active(self) -> None:
        if self._plan_active and not self._plan_reason:
            return
        self._plan_active = True
        self._plan_reason = None
        logger.info("live feeds plan marked active")
        self._notify()

    def shutdown(self) -> None:
        self._healthy = False
        self._notify()

    def clear_event(self) -> None:
        event = self._event
        if event is not None:
            event.clear()

    async def wait_for_change(self, timeout: float = 5.0) -> None:
        event = self._event
        if event is None:
            await asyncio.sleep(timeout)
            return
        try:
            await asyncio.wait_for(event.wait(), timeout)
        except TimeoutError:
            return

    async def expire_loop(self) -> None:
        try:
            while self._healthy:
                await asyncio.sleep(HEARTBEAT_TTL_SECONDS / 2)
                if not self._healthy:
                    return
                self.client_count()
                self._notify()
        except asyncio.CancelledError:
            raise

    def _drop_stale_owner(self) -> None:
        seen = self._owner_seen
        if seen is None:
            return
        if time.monotonic() - seen > HEARTBEAT_TTL_SECONDS:
            self._owner_seen = None

    def _notify(self) -> None:
        event = self._event
        if event is not None:
            event.set()


def text_is_terminal(value: str) -> bool:
    folded = value.lower()
    return any(marker in folded for marker in _TERMINAL_MARKERS)


def is_terminal_feed_error(exc: BaseException) -> bool:
    status = _status_code(exc)
    if status in {401, 403}:
        return True
    return text_is_terminal(_exception_text(exc))


def _exception_text(exc: BaseException) -> str:
    parts = [type(exc).__name__, str(exc)]
    response = getattr(exc, "response", None)
    if response is not None:
        parts.append(str(getattr(response, "status_code", "")))
        body = getattr(response, "body", None)
        if isinstance(body, (bytes, bytearray)):
            parts.append(body.decode("utf-8", errors="replace")[:400])
        elif body:
            parts.append(str(body)[:400])
    reason = getattr(exc, "reason", None)
    if reason is not None:
        parts.append(str(getattr(reason, "reason", reason))[:200])
    return " ".join(parts)


def _status_code(exc: BaseException) -> int | None:
    for attr in ("status_code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    if response is None:
        return None
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None
