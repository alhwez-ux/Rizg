from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.middleware import register_exception_handlers
from app.routers.radar import router as radar_router
from app.routers.tickchart import router as tickchart_router
from app.services.liquidity_engine import LiquidityRadarEngine
from app.services.tickchart_integration import TickChartFeed


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


class _Broadcaster:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict]] = []

    async def broadcast(self, symbol: str, message: dict) -> None:
        self.messages.append((symbol, message))

    def subscribed_symbols(self) -> set[str]:
        return set()


def _tickchart_feed(**overrides: object) -> TickChartFeed:
    payload: dict[str, object] = {
        "tickchart_api_key": "test-key",
        "sahmk_api_key": "test-key",
        "enable_mock_feed": False,
    }
    payload.update(overrides)
    settings = _settings(**payload)
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"events": [], "bids": [], "asks": []}))
    )
    return TickChartFeed(LiquidityRadarEngine(), _Broadcaster(), settings, client=client)


def test_live_radar_route_uses_tickchart_ticks() -> None:
    feed = _tickchart_feed()
    app = FastAPI()
    register_exception_handlers(app)
    app.state.tickchart = feed
    app.include_router(radar_router)
    app.include_router(tickchart_router)
    with TestClient(app) as client:
        ingest = client.post(
            "/api/v1/tickchart/ingest",
            json={
                "type": "trade",
                "symbol": "4030",
                "price": 24.9,
                "quantity": 1500,
                "event_time": "2026-09-13T10:01:00+03:00",
            },
        )
        depth = client.post(
            "/api/v1/tickchart/ingest",
            json={
                "type": "depth_snapshot",
                "symbol": "4030",
                "best_bid": 24.88,
                "best_ask": 24.92,
                "bids": [{"price": 24.88, "quantity": 800}],
                "asks": [{"price": 24.92, "quantity": 600}],
            },
        )
        response = client.get("/api/v1/radar/live/4030")
    assert ingest.status_code == 200
    assert ingest.json()["ingested"] == 1
    assert depth.status_code == 200
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["source"] == "TickChart"
    assert payload["symbol"] == "4030"
    assert payload["analysis"]["last_price"] == 24.9
    assert payload["analysis"]["live_quote"] is True
    assert payload["analysis"]["bid"] == 24.88
    assert payload["analysis"]["ask"] == 24.92


def test_live_radar_route_sends_telegram_radar_event() -> None:
    class _Telegram:
        def __init__(self) -> None:
            self.reports: list[dict[str, object]] = []

        async def send_radar_event(self, report: dict[str, object]) -> bool:
            self.reports.append(report)
            return True

    feed = _tickchart_feed()
    telegram = _Telegram()
    app = FastAPI()
    register_exception_handlers(app)
    app.state.tickchart = feed
    app.state.telegram = telegram
    app.include_router(radar_router)
    app.include_router(tickchart_router)
    with TestClient(app) as client:
        client.post(
            "/api/v1/tickchart/ingest",
            json={
                "ticks": [
                    {"symbol": "4030", "price": 25.1, "quantity": 400, "event_time": "2026-09-13T10:00:01+03:00"},
                    {"symbol": "4030", "price": 25.35, "quantity": 2800, "event_time": "2026-09-13T10:00:02+03:00"},
                ]
            },
        )
        client.post(
            "/api/v1/tickchart/ingest",
            json={
                "type": "depth_snapshot",
                "symbol": "4030",
                "best_bid": 25.3,
                "best_ask": 25.36,
                "bids": [{"price": 25.3, "quantity": 200}],
                "asks": [{"price": 25.36, "quantity": 9000}],
            },
        )
        response = client.get("/api/v1/radar/live/4030")
    assert response.status_code == 200
    assert len(telegram.reports) == 1
    assert telegram.reports[0]["symbol"] == "4030"
    assert telegram.reports[0]["last_price"]


def test_live_radar_route_404_when_tickchart_has_no_ticks() -> None:
    feed = _tickchart_feed()
    app = FastAPI()
    register_exception_handlers(app)
    app.state.tickchart = feed
    app.include_router(radar_router)
    with TestClient(app) as client:
        response = client.get("/api/v1/radar/live/4030")
    assert response.status_code == 404
    assert "تكرتشارت" in response.json()["message"]


def test_live_radar_route_503_when_tickchart_disabled() -> None:
    app = FastAPI()
    register_exception_handlers(app)
    app.state.tickchart = _tickchart_feed(
        tickchart_api_key="",
        sahmk_api_key="",
        tickchart_enabled=False,
        tickchart_autosync_enabled=False,
    )
    app.include_router(radar_router)
    with TestClient(app) as client:
        response = client.get("/api/v1/radar/live/4030")
    assert response.status_code == 503
    assert "تكرتشارت" in response.json()["message"]


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
