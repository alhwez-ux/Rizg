from __future__ import annotations

import asyncio

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.core.config import Settings
from app.routers.market import router as market_router
from app.services.sahm_data_provider import SahmDataProvider


@pytest.fixture(autouse=True)
def _fast_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def instant(_delay: float = 0) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", instant)


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        sahmk_api_key="test-key",
        sahmk_request_gap_seconds=0.05,
        sahmk_max_backoff_seconds=15,
        telegram_bot_token="",
        telegram_chat_id="",
    )


def test_ranking_matrix_uses_live_sahm_quotes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = str(request.url)
        if "/companies/" in path:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"symbol": "1120", "name": "الراجحي", "sector": "المصارف", "status": "active", "pe_ratio": 15.8, "roe": 19.0},
                        {"symbol": "2222", "name": "أرامكو السعودية", "sector": "الطاقة", "status": "active", "pe_ratio": 15.0, "roe": 26.0},
                    ],
                    "total": 2,
                    "limit": 500,
                    "offset": 0,
                },
            )
        if "/market/gainers/" in path:
            return httpx.Response(
                200,
                json={"gainers": [{"symbol": "1120", "change_percent": 1.4, "volume": 5_000_000, "value": 450_000_000, "dividend_yield": 3.4}]},
            )
        if "/market/volume/" in path or "/market/value/" in path:
            return httpx.Response(
                200,
                json={"stocks": [{"symbol": "2222", "change_percent": 0.8, "volume": 12_000_000, "value": 1_100_000_000, "dividend_yield": 7.0}]},
            )
        if "/market/summary/" in path:
            return httpx.Response(200, json={"index": "TASI"})
        if "/quote/" in path:
            ticker = path.rsplit("/", 2)[-2]
            return httpx.Response(
                200,
                json={"symbol": ticker, "data": {"price": 90.0, "change_percent": 1.0, "volume": 1000, "value": 90000, "pe_ratio": 14.0}},
            )
        return httpx.Response(404, json={"error": "missing"})

    provider = SahmDataProvider(_settings(), client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    app = FastAPI()
    app.state.sahm = provider
    app.include_router(market_router)
    response = TestClient(app).get("/api/v1/market/ranking-matrix")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "Sahm API"
    symbols = {row["symbol"] for row in payload["data"]}
    assert {"1120", "2222"} <= symbols
    assert payload["total_companies"] >= 40
    assert payload["data"][0]["rank"] == 1
