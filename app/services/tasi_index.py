"""Live TASI index quote, pushed on the same liquidity websocket as market ticks."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

INDEX_SYMBOL = "TASI"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETASI.SR"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
_REFRESH_SECONDS = 5.0
_TICK_PUSH_SECONDS = 1.0

_cached: dict[str, Any] | None = None
_last_push = 0.0


def quote_from_meta(meta: dict[str, Any] | None) -> dict[str, Any] | None:
    """Points, net change, and percent from a Yahoo chart meta block."""

    if not isinstance(meta, dict):
        return None
    value = _finite(meta.get("regularMarketPrice"))
    previous = _finite(meta.get("chartPreviousClose") or meta.get("previousClose"))
    change = _finite(meta.get("regularMarketChange"))
    if change is None and value is not None and previous not in (None, 0):
        change = value - previous
    percent = _finite(meta.get("regularMarketChangePercent"))
    if percent is None and change is not None and previous not in (None, 0):
        percent = (change / previous) * 100.0
    if value is None and change is None:
        return None
    return {
        "type": "index",
        "symbol": INDEX_SYMBOL,
        "value": None if value is None else round(value, 2),
        "change": None if change is None else round(change, 2),
        "change_percent": None if percent is None else round(percent, 4),
        "previous": None if previous is None else round(previous, 2),
    }


def current_tasi_index() -> dict[str, Any] | None:
    return dict(_cached) if _cached else None


def fetch_tasi_index() -> dict[str, Any] | None:
    """Download the latest Tadawul index print and keep it for tick broadcasts."""

    global _cached
    try:
        with httpx.Client(timeout=httpx.Timeout(6.0, connect=3.0), headers={"User-Agent": _UA}) as http:
            response = http.get(YAHOO_CHART, params={"interval": "1m", "range": "1d"})
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("TASI index fetch failed: %s", exc)
        return current_tasi_index()
    result = ((payload.get("chart") or {}).get("result") or [None])[0] or {}
    quote = quote_from_meta(result.get("meta") if isinstance(result, dict) else None)
    if quote is not None:
        _cached = quote
    return current_tasi_index()


async def publish_cached_index(broadcaster: Any, *, force: bool = False) -> None:
    """Push the latest index on the TASI room. Tick ingest calls this at most once a second."""

    global _last_push
    quote = current_tasi_index()
    if quote is None or broadcaster is None:
        return
    now = time.monotonic()
    if not force and now - _last_push < _TICK_PUSH_SECONDS:
        return
    _last_push = now
    await broadcaster.broadcast(INDEX_SYMBOL, quote)


async def run_tasi_index_publisher(broadcaster: Any, stop: asyncio.Event) -> None:
    """Refresh the index and publish it on the liquidity socket while the app is up."""

    while not stop.is_set():
        quote = await asyncio.to_thread(fetch_tasi_index)
        if quote is not None:
            await publish_cached_index(broadcaster, force=True)
        try:
            await asyncio.wait_for(stop.wait(), timeout=_REFRESH_SECONDS)
        except TimeoutError:
            continue


def _finite(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or abs(number) == float("inf"):
        return None
    return number
