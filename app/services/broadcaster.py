from __future__ import annotations

import asyncio
import logging
import threading
from collections import defaultdict
from collections.abc import Iterable
from concurrent.futures import Future
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)

_WILDCARD = "*"


class ConnectionManager:
    """Fan-out manager for symbol-scoped WebSocket rooms.

    Connection maps are guarded by a threading lock so mutations are safe from
    both the event loop and worker threads. Sends never hold the lock, and a
    failed send to one client does not abort the rest of a broadcast.
    """

    def __init__(self) -> None:
        self._rooms: dict[str, set[WebSocket]] = defaultdict(set)
        self._subscriptions: dict[WebSocket, set[str]] = {}
        self._guard = threading.RLock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(
        self,
        websocket: WebSocket,
        symbols: str | Iterable[str] | None = None,
    ) -> None:
        await websocket.accept()
        normalized = self._normalize_symbols(symbols)
        with self._guard:
            self._subscriptions[websocket] = set(normalized)
            for symbol in normalized:
                self._rooms[symbol].add(websocket)
        logger.info(
            "websocket connected client=%s subscriptions=%s",
            _client_label(websocket),
            sorted(normalized) or [_WILDCARD],
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        with self._guard:
            symbols = self._subscriptions.pop(websocket, set())
            for symbol in symbols:
                room = self._rooms.get(symbol)
                if not room:
                    continue
                room.discard(websocket)
                if not room:
                    self._rooms.pop(symbol, None)
        logger.info("websocket disconnected client=%s", _client_label(websocket))

    async def subscribe(self, websocket: WebSocket, symbols: Iterable[str]) -> set[str]:
        normalized = self._normalize_symbols(symbols)
        with self._guard:
            current = self._subscriptions.setdefault(websocket, set())
            current.update(normalized)
            for symbol in normalized:
                self._rooms[symbol].add(websocket)
            return set(current)

    async def unsubscribe(self, websocket: WebSocket, symbols: Iterable[str]) -> set[str]:
        normalized = self._normalize_symbols(symbols)
        with self._guard:
            current = self._subscriptions.setdefault(websocket, set())
            current.difference_update(normalized)
            for symbol in normalized:
                room = self._rooms.get(symbol)
                if not room:
                    continue
                room.discard(websocket)
                if not room:
                    self._rooms.pop(symbol, None)
            return set(current)

    async def broadcast(self, symbol: str, message: dict[str, Any]) -> None:
        """Send `message` to every client subscribed to `symbol`.

        Empty subscription sets and the `*` room receive every ticker.
        """

        targets = self._targets_for(symbol)
        if not targets:
            return

        results = await asyncio.gather(
            *(self._safe_send(websocket, message) for websocket in targets),
            return_exceptions=True,
        )
        stale = [
            websocket
            for websocket, result in zip(targets, results, strict=True)
            if result is not True
        ]
        for websocket in stale:
            try:
                await self.disconnect(websocket)
            except Exception:
                logger.warning(
                    "failed to drop stale websocket client=%s",
                    _client_label(websocket),
                    exc_info=True,
                )

    async def publish(self, symbol: str, message: dict[str, Any]) -> None:
        """Alias used by quote ingestion and the mock tick feed."""

        await self.broadcast(symbol, message)

    def broadcast_threadsafe(self, symbol: str, message: dict[str, Any]) -> None:
        """Schedule a broadcast from a worker thread onto the app event loop."""

        loop = self._loop
        if loop is None or not loop.is_running():
            logger.warning("cannot broadcast %s; event loop is not bound", symbol)
            return

        future = asyncio.run_coroutine_threadsafe(self.broadcast(symbol, message), loop)

        def _log_result(done: Future[None]) -> None:
            if done.cancelled():
                return
            exc = done.exception()
            if exc is not None:
                logger.warning("threadsafe broadcast failed for %s: %s", symbol, exc)

        future.add_done_callback(_log_result)

    def subscribed_symbols(self) -> set[str]:
        with self._guard:
            return {symbol for symbol in self._rooms if symbol != _WILDCARD}

    def subscriber_count(self, symbol: str | None = None) -> int:
        with self._guard:
            if symbol is None:
                return len(self._subscriptions)
            ticker = symbol.upper()
            return len(self._rooms.get(ticker, ()))

    async def close_all(self) -> None:
        with self._guard:
            connections = list(self._subscriptions)
            self._subscriptions.clear()
            self._rooms.clear()
        results = await asyncio.gather(
            *(_safe_close(websocket) for websocket in connections),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                logger.warning("error while closing websocket: %s", result)

    def _targets_for(self, symbol: str) -> list[WebSocket]:
        ticker = symbol.upper()
        with self._guard:
            targets = set(self._rooms.get(ticker, ()))
            targets.update(self._rooms.get(_WILDCARD, ()))
            for websocket, subscriptions in self._subscriptions.items():
                if not subscriptions:
                    targets.add(websocket)
            return list(targets)

    async def _safe_send(self, websocket: WebSocket, message: dict[str, Any]) -> bool:
        try:
            if websocket.client_state != WebSocketState.CONNECTED:
                return False
            await websocket.send_json(message)
            return True
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "websocket send failed client=%s",
                _client_label(websocket),
                exc_info=True,
            )
            return False

    @staticmethod
    def _normalize_symbols(symbols: str | Iterable[str] | None) -> set[str]:
        if symbols is None:
            return set()
        if isinstance(symbols, str):
            values = [symbols]
        else:
            values = list(symbols)
        return {value.strip().upper() for value in values if value and value.strip()}


def _client_label(websocket: WebSocket) -> str:
    client = getattr(websocket, "client", None)
    if client is None:
        return "unknown"
    return f"{client.host}:{client.port}"


async def _safe_close(websocket: WebSocket) -> None:
    try:
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close()
    except Exception:
        logger.warning("websocket close failed client=%s", _client_label(websocket), exc_info=True)
