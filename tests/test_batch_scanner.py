from __future__ import annotations

import asyncio
from decimal import Decimal

import httpx

from app.core.config import Settings
from app.services.broadcaster import ConnectionManager
from app.services.liquidity_engine import LiquidityEngine
from app.services.market_cache import MarketCache
from app.services.sahmk_feed import SahmkTradeFeed
from app.services.screener import ScreenerService
from app.services.watchlist import WatchlistService


def _settings(**overrides: object) -> Settings:
    payload: dict[str, object] = {
        "sahmk_api_key": "test-key",
        "sahmk_symbols": ["4030"],
        "sahmk_request_gap_seconds": 0.05,
        "sahmk_watchlist_poll_seconds": 20,
        "sahmk_market_scan_seconds": 90,
        "sahmk_batch_size": 2,
        "telegram_bot_token": "",
        "telegram_chat_id": "",
        "enable_mock_feed": False,
    }
    payload.update(overrides)
    return Settings(_env_file=None, **payload)


def _quote(symbol: str, price: str, volume: str, **extra: object) -> dict:
    payload = {
        "symbol": symbol,
        "price": price,
        "volume": volume,
        "change_percent": "1.2",
        "liquidity": {
            "inflow_value": "90000",
            "outflow_value": "20000",
            "net_value": "70000",
            "inflow_volume": "8000",
            "outflow_volume": "2000",
        },
    }
    payload.update(extra)
    return payload


def test_cache_returns_last_quote_after_rate_limit() -> None:
    cache = MarketCache(ttl_seconds=60)
    cache.put_quote("4030", {"symbol": "4030", "price": "24.80"})
    wait = cache.trip_rate_limit(12)
    assert wait == 12
    assert cache.cooling_down() is True
    assert cache.get_quote("4030")["price"] == "24.80"


def test_quote_429_falls_back_to_cached_price(tmp_path) -> None:
    watchlist = WatchlistService(path=tmp_path / "watchlist.json", initial=["4030"])
    settings = _settings()
    screener = ScreenerService(settings, watchlist)
    engine = LiquidityEngine()
    feed = SahmkTradeFeed(engine, ConnectionManager(), settings, watchlist=watchlist, screener=screener)
    hits = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["count"] += 1
        if hits["count"] == 1:
            return httpx.Response(200, json=_quote("4030", "36.64", "1000"))
        return httpx.Response(429, headers={"Retry-After": "15"}, json={"error": "rate"})

    async def run() -> None:
        feed._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        assert await feed._poll_symbol("4030") is True
        assert screener.snapshot().watchlist[0].price == Decimal("36.64")
        assert await feed._poll_symbol("4030") is False
        assert screener.snapshot().watchlist[0].price == Decimal("36.64")
        assert feed._cache.cooling_down() is True
        await feed._client.aclose()

    asyncio.run(run())
    assert hits["count"] == 2


def test_network_error_uses_cache_without_raising(tmp_path) -> None:
    watchlist = WatchlistService(path=tmp_path / "watchlist.json", initial=["4030"])
    settings = _settings()
    screener = ScreenerService(settings, watchlist)
    feed = SahmkTradeFeed(
        LiquidityEngine(),
        ConnectionManager(),
        settings,
        watchlist=watchlist,
        screener=screener,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    async def run() -> None:
        feed._cache.put_quote("4030", _quote("4030", "24.50", "500"))
        feed._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        assert await feed._poll_symbol("4030") is False
        assert screener.snapshot().watchlist[0].price == Decimal("24.50")
        await feed._client.aclose()

    asyncio.run(run())


def test_market_scan_keeps_rows_when_all_endpoints_rate_limit(tmp_path) -> None:
    watchlist = WatchlistService(path=tmp_path / "watchlist.json", initial=["4030"])
    settings = _settings(screener_leader_limit=5)
    screener = ScreenerService(settings, watchlist)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] <= 4:
            if "/gainers/" in str(request.url):
                return httpx.Response(
                    200,
                    json={
                        "gainers": [
                            {
                                "symbol": "2380",
                                "name": "بترو رابغ",
                                "price": "18.39",
                                "change_percent": "1.6",
                                "volume": "1000",
                                "inflow": "80000",
                                "outflow": "10000",
                            }
                        ]
                    },
                )
            return httpx.Response(200, json={"stocks": [], "index": "TASI"})
        return httpx.Response(429, headers={"Retry-After": "20"})

    async def run() -> None:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        assert await screener.refresh_leaders(client, "test-key") is True
        first = screener.snapshot()
        assert any(row.symbol == "2380" for row in first.radar) or first.scanned >= 1
        scanned = first.scanned
        assert await screener.refresh_leaders(client, "test-key") is True
        second = screener.snapshot()
        assert second.scanned == scanned
        await client.aclose()

    asyncio.run(run())


def test_radar_batch_excludes_watchlist(tmp_path) -> None:
    watchlist = WatchlistService(path=tmp_path / "watchlist.json", initial=["4030"])
    settings = _settings()
    screener = ScreenerService(settings, watchlist)
    screener.observe_quote(
        _quote("2380", "18.39", "2000", name="بترو رابغ"),
        tracked=False,
    )
    feed = SahmkTradeFeed(
        LiquidityEngine(),
        ConnectionManager(),
        settings,
        watchlist=watchlist,
        screener=screener,
    )
    assert "4030" not in feed._radar_targets()
    assert "2380" in feed._radar_targets()
    assert feed._watchlist_targets() == ["4030"]
