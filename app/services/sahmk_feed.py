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
from app.services.market_cache import MarketCache
from app.services.sahm_data_provider import resolve_sahm_api_key, sahm_auth_headers
from app.services.screener import ScreenerService
from app.services.shariah import is_prohibited
from app.services.watchlist import WatchlistService

logger = logging.getLogger(__name__)

_DEFAULT_REST_URL = "https://api.sahmcapital.com/v1"
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
        self._api_key = resolve_sahm_api_key(settings)
        self._rest_url = (settings.sahmk_rest_url or _DEFAULT_REST_URL).rstrip("/")
        self._data_mode = (settings.sahmk_data_mode or "delayed").strip().lower()
        if self._data_mode not in {"delayed", "realtime"}:
            self._data_mode = "delayed"
        self._poll_seconds = settings.sahmk_poll_seconds
        self._watchlist_poll = settings.sahmk_watchlist_poll_seconds
        self._market_scan = settings.sahmk_market_scan_seconds
        self._batch_size = settings.sahmk_batch_size
        self._request_gap = settings.sahmk_request_gap_seconds
        self._max_backoff = settings.sahmk_max_backoff_seconds
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
        self._cache = screener.cache if screener is not None else MarketCache(
            ttl_seconds=settings.sahmk_cache_ttl_seconds
        )
        self._radar_cursor = 0

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    async def start(self) -> None:
        if self._running:
            return
        if not self.enabled:
            logger.warning("SAHM_API_KEY is missing; market feed will not start")
            return
        self._running = True
        self._client = httpx.AsyncClient(
            timeout=20.0,
            headers=sahm_auth_headers(self._api_key),
        )
        self._task = asyncio.create_task(self._run(), name="sahmk-quote-poll")
        logger.info(
            "sahmk quote feed starting watchlist=%s mode=%s watch=%.0fs market=%.0fs batch=%s",
            self._symbols,
            self._data_mode,
            self._watchlist_poll,
            self._market_scan,
            self._batch_size,
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

    def _watchlist_targets(self) -> list[str]:
        if self._watchlist:
            return [symbol for symbol in self._watchlist.symbols() if not is_prohibited(symbol)]
        return [symbol for symbol in self._symbols if not is_prohibited(symbol)]

    def _radar_targets(self) -> list[str]:
        watched = set(self._watchlist_targets())
        extra = self._screener.radar_universe(40) if self._screener else []
        return [symbol for symbol in extra if symbol not in watched]

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
        last_watch = 0.0
        last_market = 0.0
        idle = min(self._watchlist_poll, self._poll_seconds, 8.0)
        try:
            while self._running:
                try:
                    if self._cache.cooling_down():
                        self._replay_watchlist()
                        remaining = self._cache.cooldown_remaining()
                        await asyncio.sleep(min(max(remaining, 1.0), idle))
                        continue

                    now = asyncio.get_running_loop().time()
                    if now - last_watch >= self._watchlist_poll:
                        for symbol in self._watchlist_targets():
                            if not self._running or self._cache.cooling_down():
                                break
                            await self._poll_symbol(symbol)
                            await asyncio.sleep(self._request_gap)
                        last_watch = asyncio.get_running_loop().time()

                    if (
                        self._screener is not None
                        and self._client is not None
                        and not self._cache.cooling_down()
                        and now - last_market >= self._market_scan
                    ):
                        await self._screener.refresh_leaders(self._client, self._api_key)
                        last_market = asyncio.get_running_loop().time()

                    radar = self._radar_targets()
                    if radar and not self._cache.cooling_down() and self._running:
                        if self._radar_cursor >= len(radar):
                            self._radar_cursor = 0
                        batch = radar[self._radar_cursor : self._radar_cursor + self._batch_size]
                        if not batch:
                            self._radar_cursor = 0
                            batch = radar[: self._batch_size]
                        self._radar_cursor += len(batch)
                        for symbol in batch:
                            if not self._running or self._cache.cooling_down():
                                break
                            await self._poll_symbol(symbol)
                            await asyncio.sleep(self._request_gap)

                    await asyncio.sleep(idle)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.warning("sahmk scan cycle failed; backing off", exc_info=True)
                    await asyncio.sleep(min(idle * 2, self._max_backoff))
        except asyncio.CancelledError:
            logger.info("sahmk quote feed cancelled")
            raise

    def _replay_watchlist(self) -> None:
        for symbol in self._watchlist_targets():
            self._apply_cached_quote(symbol)

    def _apply_cached_quote(self, symbol: str) -> None:
        payload = self._cache.get_quote(symbol)
        if payload is None or self._screener is None:
            return
        tracked = self._watchlist.contains(symbol) if self._watchlist else symbol in self._symbols
        try:
            self._screener.observe_quote(
                payload,
                tracked=tracked,
                session=self._engine.session_snapshot(symbol),
            )
        except Exception:
            logger.warning("failed to apply cached quote for %s", symbol, exc_info=True)

    async def _poll_symbol(self, symbol: str) -> bool:
        if self._cache.cooling_down():
            self._apply_cached_quote(symbol)
            return False
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=20.0,
                headers=sahm_auth_headers(self._api_key),
            )
        url = f"{self._rest_url}/quote/{symbol}/"
        try:
            response = await self._client.get(
                url,
                params={"data_mode": self._data_mode},
                headers=sahm_auth_headers(self._api_key),
            )
        except httpx.HTTPError:
            logger.warning("sahmk quote network error for %s; using cache", symbol)
            self._apply_cached_quote(symbol)
            return False

        if response.status_code == 429:
            wait = self._cache.trip_rate_limit(_retry_after(response))
            logger.warning("sahmk quote rate limited (HTTP 429) for %s; cooling %.0fs", symbol, wait)
            self._apply_cached_quote(symbol)
            return False
        if response.status_code in {401, 403}:
            logger.warning(
                "SAHMK quote rejected for %s (HTTP %s)",
                symbol,
                response.status_code,
            )
            self._apply_cached_quote(symbol)
            return False
        if response.status_code >= 400:
            logger.warning("sahmk quote HTTP %s for %s; using cache", response.status_code, symbol)
            self._apply_cached_quote(symbol)
            return False

        payload = _response_json(response)
        if not isinstance(payload, dict):
            self._apply_cached_quote(symbol)
            return False
        if payload.get("error"):
            logger.warning("sahmk quote error for %s: %s", symbol, payload["error"])
            self._apply_cached_quote(symbol)
            return False

        self._cache.put_quote(symbol, payload)
        return await self._apply_live_quote(payload, symbol)

    async def _apply_live_quote(self, payload: dict[str, Any], symbol: str) -> bool:
        try:
            ingested = await self.ingest_message(payload)
            if self._screener is not None:
                tracked = (
                    self._watchlist.contains(symbol) if self._watchlist else symbol in self._symbols
                )
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
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("sahmk failed to apply quote for %s", symbol, exc_info=True)
            return False

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


def _response_json(response: httpx.Response) -> dict[str, Any] | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def _retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None
