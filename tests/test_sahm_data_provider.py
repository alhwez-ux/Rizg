from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import httpx
import pandas as pd
import pytest

from app.core.exceptions import InvalidSymbolError, SahmApiError
from app.core.config import Settings
from app.services.liquidity_engine import LiquidityRadarEngine
from app.services.sahm_data_provider import (
    CANDLE_COLUMNS,
    RADAR_COLUMNS,
    SahmDataProvider,
    candles_to_radar_frame,
)


def _settings(**overrides: object) -> Settings:
    payload: dict[str, object] = {
        "sahmk_api_key": "test-key",
        "sahmk_request_gap_seconds": 0.05,
        "sahmk_max_backoff_seconds": 15,
        "telegram_bot_token": "",
        "telegram_chat_id": "",
        "enable_mock_feed": False,
    }
    payload.update(overrides)
    return Settings(_env_file=None, **payload)


def _provider(handler, **overrides: object) -> SahmDataProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="https://api.sahmk.sa")
    return SahmDataProvider(_settings(**overrides), client=client)


@pytest.fixture(autouse=True)
def _fast_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def instant(_delay: float = 0) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", instant)


def test_historical_candles_normalize_to_radar_frame() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/historical/4030/")
        assert request.headers["X-API-Key"] == "test-key"
        params = parse_qs(request.url.query.decode() if isinstance(request.url.query, bytes) else request.url.query)
        assert params["interval"] == ["1d"]
        return httpx.Response(
            200,
            json={
                "symbol": "4030",
                "interval": "1d",
                "count": 2,
                "data": [
                    {
                        "date": "2026-09-10",
                        "open": 24.1,
                        "high": 24.8,
                        "low": 24.0,
                        "close": 24.5,
                        "volume": 1000,
                        "turnover": 24500.0,
                        "adjusted_close": 24.5,
                    },
                    {
                        "date": "2026-09-11",
                        "open": 24.5,
                        "high": 25.0,
                        "low": 24.4,
                        "close": 24.9,
                        "volume": 1500,
                        "turnover": 37000.0,
                    },
                ],
            },
        )

    provider = _provider(handler)

    async def run() -> pd.DataFrame:
        async with provider:
            return await provider.historical_candles("4030", from_date=date(2026, 9, 1), to_date="2026-09-11")

    frame = asyncio.run(run())
    assert list(frame.columns) == list(RADAR_COLUMNS)
    assert len(frame) == 2
    assert frame.iloc[0]["symbol"] == "4030"
    assert frame.iloc[-1]["close"] == pytest.approx(24.9)
    assert bool(frame.iloc[0]["is_intraday"]) is False
    assert frame["timestamp"].dt.tz is not None


def test_intraday_candles_and_engine_ingest() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        params = parse_qs(request.url.query.decode() if isinstance(request.url.query, bytes) else request.url.query)
        assert params["interval"] == ["60m"]
        return httpx.Response(
            200,
            json={
                "symbol": "2222",
                "interval": "60m",
                "metadata": {"is_intraday": True, "is_final": True},
                "count": 2,
                "data": [
                    {
                        "date": "2026-09-11T07:00:00+00:00",
                        "open": 25.3,
                        "high": 25.4,
                        "low": 25.2,
                        "close": 25.35,
                        "volume": 800,
                        "number_of_trades": 12,
                        "is_final": True,
                    },
                    {
                        "date": "2026-09-11T08:00:00+00:00",
                        "open": 25.35,
                        "high": 25.5,
                        "low": 25.3,
                        "close": 25.48,
                        "volume": 1200,
                        "number_of_trades": 18,
                        "partial": False,
                    },
                ],
            },
        )

    provider = _provider(handler)
    engine = LiquidityRadarEngine()

    async def run() -> pd.DataFrame:
        return await provider.intraday_candles("2222", interval="60m", from_date="2026-09-11")

    frame = asyncio.run(run())
    results = engine.ingest(frame)
    assert bool(frame.iloc[0]["is_intraday"]) is True
    assert len(results) == 2
    session = engine.get_session("2222")
    assert session.trade_count == 2
    assert session.last_price == Decimal("25.48")
    assert session.buy_volume == Decimal("1200")


def test_pagination_follows_has_more() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = parse_qs(request.url.query.decode() if isinstance(request.url.query, bytes) else request.url.query)
        offset = int(params.get("offset", ["0"])[0])
        calls.append(offset)
        if offset == 0:
            return httpx.Response(
                200,
                json={
                    "symbol": "1120",
                    "interval": "1d",
                    "limit": 1,
                    "offset": 0,
                    "has_more": True,
                    "data": [{"date": "2026-09-01", "close": 90.0, "volume": 10, "open": 89, "high": 91, "low": 88}],
                },
            )
        return httpx.Response(
            200,
            json={
                "symbol": "1120",
                "interval": "1d",
                "limit": 1,
                "offset": 1,
                "has_more": False,
                "data": [{"date": "2026-09-02", "close": 91.0, "volume": 12, "open": 90, "high": 92, "low": 89}],
            },
        )

    provider = _provider(handler)
    frame = asyncio.run(provider.fetch_candles("1120"))
    assert calls == [0, 1]
    assert list(frame["close"]) == [90.0, 91.0]


def test_plan_limit_raises() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"error": {"code": "PLAN_LIMIT", "message": "60m requires Pro or higher"}},
        )

    provider = _provider(handler)
    with pytest.raises(SahmApiError) as exc:
        asyncio.run(provider.intraday_candles("4030", interval="30m"))
    assert exc.value.error_code == "sahm_plan_limit"
    assert exc.value.status_code == 403


def test_retries_after_rate_limit() -> None:
    hits = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        hits["count"] += 1
        if hits["count"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": {"code": "RATE_LIMIT"}})
        return httpx.Response(
            200,
            json={
                "symbol": "4030",
                "interval": "1d",
                "data": [{"date": "2026-09-11", "close": 24.0, "volume": 1, "open": 24, "high": 24, "low": 24}],
            },
        )

    provider = _provider(handler)
    frame = asyncio.run(provider.historical_candles("4030"))
    assert hits["count"] == 2
    assert len(frame) == 1


def test_missing_api_key() -> None:
    provider = SahmDataProvider(_settings(sahmk_api_key=""))
    with pytest.raises(SahmApiError) as exc:
        asyncio.run(provider.historical_candles("4030"))
    assert exc.value.error_code == "sahm_not_configured"


def test_invalid_symbol_rejected() -> None:
    provider = _provider(lambda _request: httpx.Response(200, json={"data": []}))
    with pytest.raises(InvalidSymbolError):
        asyncio.run(provider.historical_candles("AAPL"))


def test_list_tasi_symbols() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/companies/" in request.url.path
        params = parse_qs(urlparse(str(request.url)).query)
        assert params["market"] == ["TASI"]
        return httpx.Response(
            200,
            json={
                "results": [
                    {"symbol": "2222", "market": "TASI", "status": "active"},
                    {"symbol": "4030", "market": "TASI", "status": "active"},
                    {"symbol": "9999", "market": "TASI", "status": "suspended"},
                ],
                "total": 3,
                "limit": 500,
                "offset": 0,
            },
        )

    provider = _provider(handler)
    symbols = asyncio.run(provider.list_tasi_symbols())
    assert symbols == ["2222", "4030"]


def test_empty_payload_keeps_radar_schema() -> None:
    frame = candles_to_radar_frame([], symbol="4030", interval="1d", is_intraday=False)
    assert list(frame.columns) == list(RADAR_COLUMNS)
    assert frame.empty
    engine = LiquidityRadarEngine()
    assert engine.ingest(frame) == []


def test_fetch_historical_candles_bridge_normalizes_symbol_and_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/historical/1120/")
        assert request.headers["Authorization"].startswith("Bearer ")
        assert request.headers["X-API-Key"] == "test-key"
        return httpx.Response(
            200,
            json={
                "data": {
                    "candles": [
                        [1725840000000, 90.0, 91.0, 89.5, 90.5, 1000],
                        [1725926400000, 90.5, 92.0, 90.0, 91.2, 1400],
                    ]
                }
            },
        )

    provider = _provider(handler)
    frame = provider.fetch_historical_candles("1120.SR", interval="1d", limit=1)
    assert frame is not None
    assert list(CANDLE_COLUMNS) == ["timestamp", "open", "high", "low", "close", "volume"]
    for column in CANDLE_COLUMNS:
        assert column in frame.columns
    assert len(frame) == 1
    assert frame.iloc[0]["symbol"] == "1120"
    assert frame.iloc[0]["close"] == pytest.approx(91.2)


def test_fetch_historical_candles_maps_hour_interval() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = parse_qs(request.url.query.decode() if isinstance(request.url.query, bytes) else request.url.query)
        seen.append(params["interval"][0])
        return httpx.Response(
            200,
            json={
                "interval": "60m",
                "data": [
                    {
                        "timestamp": "2026-09-11T08:00:00+00:00",
                        "open": 25.0,
                        "high": 25.2,
                        "low": 24.9,
                        "close": 25.1,
                        "volume": 500,
                    }
                ],
            },
        )

    provider = _provider(handler)
    frame = provider.fetch_historical_candles("4030", interval="1h", limit=100)
    assert seen == ["60m"]
    assert frame is not None
    assert len(frame) == 1


def test_fetch_historical_candles_returns_none_on_http_error() -> None:
    provider = _provider(lambda _request: httpx.Response(500, json={"error": "boom"}))
    assert provider.fetch_historical_candles("4030") is None


def test_fetch_historical_candles_rejects_minute_bars() -> None:
    provider = _provider(lambda _request: httpx.Response(200, json={"data": []}))
    assert provider.fetch_historical_candles("4030", interval="5m") is None
