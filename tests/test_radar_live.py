from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.middleware import register_exception_handlers
from app.routers.radar import router as radar_router
from app.services.liquidity_engine import LiquidityRadarEngine
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


def _frame() -> pd.DataFrame:
    stamps = [
        datetime(2026, 9, 10, tzinfo=timezone.utc),
        datetime(2026, 9, 11, tzinfo=timezone.utc),
        datetime(2026, 9, 12, tzinfo=timezone.utc),
    ]
    return pd.DataFrame(
        {
            "timestamp": stamps,
            "symbol": ["4030", "4030", "4030"],
            "open": [24.0, 24.5, 25.4],
            "high": [24.6, 25.0, 26.2],
            "low": [23.9, 24.4, 24.8],
            "close": [24.5, 24.9, 24.9],
            "volume": [1000.0, 1200.0, 2800.0],
        }
    )


def test_engine_accepts_dataframe_and_builds_signal_report() -> None:
    engine = LiquidityRadarEngine(_frame())
    report = engine.get_latest_signal_report()
    assert report["symbol"] == "4030"
    assert report["trade_count"] == 3
    assert report["last_price"] == 24.9
    assert report["signal"] in {"entry", "exit", "trap", "neutral"}
    assert isinstance(report["reasons"], list)


def test_engine_detects_bull_trap_from_upper_wick() -> None:
    frame = _frame()
    frame.loc[2, ["open", "high", "low", "close"]] = [25.4, 26.8, 25.3, 25.35]
    engine = LiquidityRadarEngine(frame)
    report = engine.get_latest_signal_report()
    assert report["trap"] is not None
    assert report["trap"]["kind"] == "bull_trap"


def test_live_radar_route_fetches_sahm_automatically() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/quote/" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "symbol": "4030",
                    "data": {"price": 24.9, "volume": 1500, "value": 37350, "change_percent": 1.63},
                },
            )
        return httpx.Response(
            200,
            json={
                "symbol": "4030",
                "interval": "1d",
                "data": [
                    {"date": "2026-09-10", "open": 24.0, "high": 24.6, "low": 23.9, "close": 24.5, "volume": 1000},
                    {"date": "2026-09-11", "open": 24.5, "high": 25.0, "low": 24.4, "close": 24.9, "volume": 1500},
                ],
            },
        )

    provider = SahmDataProvider(
        _settings(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    app = FastAPI()
    register_exception_handlers(app)
    app.state.sahm = provider
    app.include_router(radar_router)
    with TestClient(app) as client:
        response = client.get("/api/v1/radar/live/4030")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["source"] == "Sahm API"
    assert payload["symbol"] == "4030"
    assert payload["analysis"]["symbol"] == "4030"
    assert payload["analysis"]["trade_count"] == 2
    assert payload["analysis"]["value_traded"] == 37350
    assert payload["analysis"]["live_quote"] is True


def test_live_radar_route_sends_telegram_radar_event() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/quote/" in str(request.url):
            return httpx.Response(200, json={"symbol": "4030", "data": {"price": 25.35, "volume": 2800}})
        return httpx.Response(
            200,
            json={
                "symbol": "4030",
                "interval": "1d",
                "data": [
                    {"date": "2026-09-10", "open": 24.0, "high": 24.6, "low": 23.9, "close": 24.5, "volume": 1000},
                    {"date": "2026-09-11", "open": 24.5, "high": 25.0, "low": 24.4, "close": 24.9, "volume": 1500},
                    {"date": "2026-09-12", "open": 25.4, "high": 26.8, "low": 25.3, "close": 25.35, "volume": 2800},
                ],
            },
        )

    class _Telegram:
        def __init__(self) -> None:
            self.reports: list[dict[str, object]] = []

        async def send_radar_event(self, report: dict[str, object]) -> bool:
            self.reports.append(report)
            return True

    provider = SahmDataProvider(
        _settings(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    telegram = _Telegram()
    app = FastAPI()
    register_exception_handlers(app)
    app.state.sahm = provider
    app.state.telegram = telegram
    app.include_router(radar_router)
    with TestClient(app) as client:
        response = client.get("/api/v1/radar/live/4030")
    assert response.status_code == 200
    assert len(telegram.reports) == 1
    assert telegram.reports[0]["symbol"] == "4030"
    assert telegram.reports[0]["trap"] is not None


def test_live_radar_route_returns_404_when_sahm_has_no_candles() -> None:
    provider = SahmDataProvider(
        _settings(),
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"data": []}))
        ),
    )
    app = FastAPI()
    register_exception_handlers(app)
    app.state.sahm = provider
    app.include_router(radar_router)
    with TestClient(app) as client:
        response = client.get("/api/v1/radar/live/4030")
    assert response.status_code == 404
    assert "Sahm API" in response.json()["message"]


def test_trigger_test_alert_sends_intraday_message() -> None:
    class _Alerts:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str, str]] = []

        async def send_intraday_alert(
            self,
            symbol: str,
            symbol_name: str,
            signal_type: str,
            details: str,
        ) -> bool:
            self.calls.append((symbol, symbol_name, signal_type, details))
            return True

    alerts = _Alerts()
    app = FastAPI()
    register_exception_handlers(app)
    app.state.telegram_alerts = alerts
    app.include_router(radar_router)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/radar/trigger-test-alert",
            params={"symbol": "4030", "name": "البحري", "signal": "دخول مؤسسي"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "تيليجرام" in payload["message"]
    assert alerts.calls == [
        ("4030", "البحري", "دخول مؤسسي", "رصد حجم تداول غير طبيعي مع تراكم تدفق سيولة مؤسسي إيجابي.")
    ]


def test_trigger_test_alert_fails_when_bot_not_configured() -> None:
    app = FastAPI()
    register_exception_handlers(app)
    app.state.settings = _settings()
    app.include_router(radar_router)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/radar/trigger-test-alert",
            params={"symbol": "4030", "name": "البحري", "signal": "فخ سعري"},
        )
    assert response.status_code == 503
    assert "TELEGRAM_BOT_TOKEN" in response.json()["message"]
