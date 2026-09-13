from __future__ import annotations

import asyncio

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.database import MarketDataStore
from app.core.middleware import register_exception_handlers
from app.routers.analyze import router as analyze_router
from app.services.broadcaster import ConnectionManager
from app.services.liquidity import LiquidityService
from app.services.liquidity_engine import LiquidityRadarEngine
from app.services.market_data import MarketDataService
from app.services.sahm_analysis import SahmAnalysisService
from app.services.sahm_data_provider import SahmDataProvider


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


def _provider(handler) -> SahmDataProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return SahmDataProvider(_settings(), client=client)


def _service(handler) -> SahmAnalysisService:
    store = MarketDataStore(history_limit=50)
    market = MarketDataService(store, LiquidityService(), ConnectionManager())
    return SahmAnalysisService(_provider(handler), LiquidityRadarEngine(), market_data=market)


def _client(service: SahmAnalysisService) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.state.sahm_analysis = service
    app.include_router(analyze_router)
    return TestClient(app)


def _daily_payload() -> dict:
    return {
        "symbol": "4030",
        "interval": "1d",
        "data": [
            {
                "date": "2026-09-10",
                "open": 24.1,
                "high": 24.8,
                "low": 24.0,
                "close": 24.5,
                "volume": 1000,
            },
            {
                "date": "2026-09-11",
                "open": 24.5,
                "high": 25.0,
                "low": 24.4,
                "close": 24.9,
                "volume": 1500,
            },
        ],
    }


def test_analyze_route_fetches_sahm_candles_without_frontend_payload() -> None:
    service = _service(lambda _request: httpx.Response(200, json=_daily_payload()))
    with _client(service) as client:
        response = client.get("/api/v1/analyze/4030")
    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "4030"
    assert payload["source"] == "sahm"
    assert payload["bars"] == 2
    assert payload["session"]["trade_count"] == 2
    assert payload["levels"]["last_price"] == 24.9
    assert len(payload["candles"]) == 2
    assert payload["candles"][-1]["close"] == 24.9


def test_analyze_missing_key_returns_503() -> None:
    service = SahmAnalysisService(
        SahmDataProvider(_settings(sahmk_api_key="")),
        LiquidityRadarEngine(),
    )
    with _client(service) as client:
        response = client.get("/api/v1/analyze/4030")
    assert response.status_code == 503
    assert response.json()["error"] == "sahm_not_configured"


def test_analyze_unknown_symbol_returns_404() -> None:
    service = _service(lambda _request: httpx.Response(200, json={"data": []}))
    with _client(service) as client:
        response = client.get("/api/v1/analyze/4030")
    assert response.status_code == 404


def test_ensure_seeded_stores_last_bar_for_liquidity_lookup() -> None:
    service = _service(lambda _request: httpx.Response(200, json=_daily_payload()))

    async def run() -> None:
        session = await service.ensure_seeded("4030")
        assert session is not None
        assert session.trade_count == 2
        quote = await service._market_data.get_latest("4030")
        assert quote.last_price == 24.9
        again = await service.ensure_seeded("4030")
        assert again is not None
        assert again.trade_count == 2

    asyncio.run(run())
