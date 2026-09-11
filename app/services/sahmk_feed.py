from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.core.config import Settings
from app.models.trade import LiquidityStreamMessage
from app.services.alerts import AlertService
from app.services.broadcaster import ConnectionManager
from app.services.liquidity_engine import LiquidityEngine
from app.services.screener import ScreenerService
from app.services.watchlist import WatchlistService

logger = logging.getLogger(__name__)

_DEFAULT_REST_URL = "https://api.sahmk.sa/api/v1"
_SEEN_LIMIT = 2_000


class SahmkTradeFeed:
    """SAHMK quote poller for delayed (or later realtime) Tadawul prices.

    Starter plans expose 15-minute delayed quotes. Each poll converts a volume
    increase into a print and runs it through LiquidityEngine so the dashboard
    and Telegram interval reports keep working. Switch `SAHMK_DATA_MODE=realtime`
    after upgrading the SAHMK plan.
    """

    def __init__(
        self,
        engine: LiquidityEngine,
        manager: ConnectionManager,
        settings: Settings,
        *,
        alerts: AlertService | None = None,
        watchlist: WatchlistService | None = None,
        screener: ScreenerService | None = None,
    ) -> None:
        self._engine = engine
        self._manager = manager
        self._alerts = alerts
        self._watchlist = watchlist
        self._screener = screener
        self._api_key = settings.sahmk_api_key.strip()
        self._rest_url = (settings.sahmk_rest_url or _DEFAULT_REST_URL).rstrip("/")
        self._data_mode = (settings.sahmk_data_mode or "delayed").strip().lower()
        if self._data_mode not in {"delayed", "realtime"}:
            self._data_mode = "delayed"
        self._poll_seconds = settings.sahmk_poll_seconds
        self._symbols = [
            item.strip().upper()
            for item in settings.sahmk_symbols
            if item.strip()
        ] or ["4030"]
        self._task: asyncio.Task[None] | None = None
        self._client: httpx.AsyncClient | None = None
        self._running = False
        self._seen: deque[str] = deque()
        self._seen_set: set[str] = set()
        self._last_quote_volume: dict[str, Decimal] = {}

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    async def start(self) -> None:
        if self._running:
            return
        if not self.enabled:
            logger.warning("SAHMK_API_KEY is missing; market feed will not start")
            return
        self._running = True
        self._client = httpx.AsyncClient(timeout=20.0)
        self._task = asyncio.create_task(self._run(), name="sahmk-quote-poll")
        logger.info(
            "sahmk quote feed starting symbols=%s mode=%s poll=%.0fs",
            self._symbols,
            self._data_mode,
            self._poll_seconds,
        )

    async def stop(self) -> None:
        self._running = False
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        logger.info("sahmk quote feed stopped")

    def _poll_targets(self) -> list[str]:
        watched = self._watchlist.symbols() if self._watchlist else list(self._symbols)
        extra = self._screener.priority_symbols(8) if self._screener else []
        return list(dict.fromkeys([*watched, *extra]))[:24]

    async def ingest_message(self, payload: dict[str, Any]) -> int:
        """Parse a SAHMK quote/trade payload and push prints into the engine."""

        msg_type = str(payload.get("type") or "").lower()
        if msg_type == "trade":
            return 1 if await self._ingest_trade(payload) else 0
        if msg_type == "trades_snapshot":
            events = payload.get("events") or []
            symbol = str(payload.get("symbol") or "")
            ordered = sorted(events, key=_event_sort_key)
            ingested = 0
            for event in ordered:
                if not isinstance(event, dict):
                    continue
                trade = dict(event)
                trade.setdefault("symbol", symbol)
                if await self._ingest_trade(trade):
                    ingested += 1
            return ingested
        if msg_type == "quote" or "price" in payload:
            return 1 if await self._ingest_quote(payload) else 0
        return 0

    async def _run(self) -> None:
        delay = self._poll_seconds
        try:
            while self._running:
                try:
                    if self._client is not None and self._screener is not None:
                        await self._screener.refresh_leaders(self._client, self._api_key)
                    for symbol in self._poll_targets():
                        if not self._running:
                            break
                        await self._poll_symbol(symbol)
                    delay = self._poll_seconds
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("sahmk quote poll failed")
                    delay = min(delay * 2, 120)
                if not self._running:
                    break
                await asyncio.sleep(delay)
        except asyncio.CancelledError:
            logger.info("sahmk quote feed cancelled")
            raise

    async def _poll_symbol(self, symbol: str) -> bool:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=20.0)
        url = f"{self._rest_url}/quote/{symbol}/"
        try:
            response = await self._client.get(
                url,
                params={"data_mode": self._data_mode},
                headers={
                    "X-API-Key": self._api_key,
                    "Accept": "application/json",
                },
            )
        except httpx.HTTPError:
            logger.warning("sahmk quote request failed for %s", symbol, exc_info=True)
            return True

        if response.status_code in {401, 403}:
            logger.warning(
                "SAHMK quote rejected for %s (HTTP %s)",
                symbol,
                response.status_code,
            )
            return True
        if response.status_code >= 400:
            logger.warning(
                "sahmk quote HTTP %s for %s",
                response.status_code,
                symbol,
            )
            return True

        payload = response.json()
        if not isinstance(payload, dict):
            return True
        if payload.get("error"):
            logger.warning("sahmk quote error for %s: %s", symbol, payload["error"])
            return True
        ingested = await self.ingest_message(payload)
        if self._screener is not None:
            tracked = self._watchlist.contains(symbol) if self._watchlist else symbol in self._symbols
            self._screener.observe_quote(
                payload,
                tracked=tracked,
                session=self._engine.session_snapshot(symbol),
            )
        if ingested:
            logger.info(
                "sahmk %s print ingested mode=%s delayed=%s",
                symbol,
                self._data_mode,
                payload.get("is_delayed"),
            )
        return True

    async def _ingest_quote(self, payload: dict[str, Any]) -> bool:
        symbol = str(payload.get("symbol") or "").strip().upper()
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        if not symbol or not isinstance(data, dict):
            return False
        price = data.get("price", payload.get("price"))
        volume = data.get("volume", data.get("quantity", payload.get("volume")))
        if price is None or volume is None:
            return False
        try:
            cumulative = Decimal(str(volume))
        except (InvalidOperation, TypeError, ValueError):
            return False
        previous = self._last_quote_volume.get(symbol)
        self._last_quote_volume[symbol] = cumulative
        if previous is None:
            logger.info("sahmk seeded %s delayed quote volume=%s", symbol, cumulative)
            return False
        delta = cumulative - previous
        if delta <= 0:
            return False
        return await self._ingest_trade(
            {
                "type": "trade",
                "symbol": symbol,
                "price": price,
                "quantity": delta,
                "event_time": payload.get("updated_at")
                or payload.get("timestamp")
                or data.get("updated_at"),
            }
        )

    async def _ingest_trade(self, payload: dict[str, Any]) -> bool:
        parsed = parse_trade_event(payload)
        if parsed is None:
            return False
        symbol, price, volume, timestamp, dedupe_key = parsed
        if not self._mark_seen(dedupe_key):
            return False
        try:
            result = self._engine.process_trade(
                symbol,
                price,
                volume,
                timestamp=timestamp,
            )
            message = LiquidityStreamMessage.from_trade(result)
            await self._manager.broadcast(symbol, message.as_json())
            if self._alerts is not None:
                await self._alerts.handle_trade(result)
            return True
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("failed to ingest sahmk print for %s", symbol)
            return False

    def _mark_seen(self, key: str) -> bool:
        if key in self._seen_set:
            return False
        if len(self._seen) >= _SEEN_LIMIT:
            expired = self._seen.popleft()
            self._seen_set.discard(expired)
        self._seen.append(key)
        self._seen_set.add(key)
        return True


def parse_trade_event(
    payload: dict[str, Any],
) -> tuple[str, Decimal, Decimal, datetime, str] | None:
    symbol = str(payload.get("symbol") or "").strip().upper()
    if not symbol:
        return None
    try:
        price = Decimal(str(payload.get("price")))
        quantity = payload.get("quantity", payload.get("volume"))
        volume = Decimal(str(quantity))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if price <= 0 or volume < 0:
        return None
    timestamp = _parse_time(payload.get("event_time") or payload.get("timestamp") or payload.get("updated_at"))
    dedupe_key = f"{symbol}|{payload.get('event_time') or timestamp.isoformat()}|{price}|{volume}"
    return symbol, price, volume, timestamp, dedupe_key


def _parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _event_sort_key(event: Any) -> str:
    if not isinstance(event, dict):
        return ""
    return str(event.get("event_time") or event.get("timestamp") or "")
