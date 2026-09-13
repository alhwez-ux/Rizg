from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.routers.tickchart import router as tickchart_router
from app.services.liquidity_engine import LiquidityRadarEngine
from app.services.tickchart_autosync import TickChartAutoSync, parse_export_file
from app.services.tickchart_integration import TickChartFeed


class _Broadcaster:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict]] = []

    async def broadcast(self, symbol: str, message: dict) -> None:
        self.messages.append((symbol, message))

    def subscribed_symbols(self) -> set[str]:
        return set()


def _feed() -> TickChartFeed:
    settings = Settings(
        _env_file=None,
        tickchart_enabled=True,
        tickchart_autosync_enabled=True,
        tickchart_api_key="",
        sahmk_api_key="",
        enable_mock_feed=False,
    )
    return TickChartFeed(LiquidityRadarEngine(), _Broadcaster(), settings)


def test_parse_tick_csv_from_named_file(tmp_path: Path) -> None:
    path = tmp_path / "2222_ticks.csv"
    path.write_text(
        "Time,Price,Volume,Side\n10:00:01,25.70,200,BUY\n10:00:02,25.72,800,BUY\n",
        encoding="utf-8",
    )
    payloads = parse_export_file(path)
    assert len(payloads) == 2
    assert payloads[0]["symbol"] == "2222"
    assert payloads[0]["price"] == "25.70"
    assert payloads[1]["quantity"] == "800"


def test_parse_depth_csv(tmp_path: Path) -> None:
    path = tmp_path / "1120_depth.csv"
    path.write_text(
        "Bid,BidSize,Ask,AskSize\n90.10,4000,90.20,1200\n90.00,800,90.30,600\n",
        encoding="utf-8",
    )
    payloads = parse_export_file(path)
    assert payloads[0]["type"] == "depth_snapshot"
    assert payloads[0]["symbol"] == "1120"
    assert payloads[0]["bids"][0]["price"] == "90.10"
    assert payloads[0]["asks"][0]["price"] == "90.20"


def test_autosync_ingests_export_into_radar(tmp_path: Path) -> None:
    feed = _feed()
    sync = TickChartAutoSync(feed, feed._settings, watch_dirs=[tmp_path])
    path = tmp_path / "4030.csv"
    path.write_text("price,quantity,time\n24.90,1500,2026-09-14T10:01:00\n", encoding="utf-8")
    ingested = asyncio.run(sync.ingest_path(path))
    report = feed.radar_report("4030")
    assert ingested == 1
    assert report["last_price"] == 24.9
    assert report["source"] == "TickChart"


def test_autosync_status_on_tickchart_endpoint(tmp_path: Path) -> None:
    feed = _feed()
    sync = TickChartAutoSync(feed, feed._settings, watch_dirs=[tmp_path])
    feed.bind_autosync(sync)
    app = FastAPI()
    app.state.tickchart = feed
    app.include_router(tickchart_router)
    response = TestClient(app).get("/api/v1/tickchart/status")
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["source"] == "TickChart"
    assert body["mode"] == "cloud"


def test_browser_upload_ingests_csv_without_local_folder() -> None:
    feed = _feed()
    app = FastAPI()
    app.state.tickchart = feed
    app.include_router(tickchart_router)
    response = TestClient(app).post(
        "/api/v1/tickchart/upload",
        files={"file": ("2222.csv", "Time,Price,Volume\n10:00:01,25.70,200\n", "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["ingested"] == 1
    assert feed.radar_report("2222")["last_price"] == 25.7


def test_follow_and_refresh_are_cloud_endpoints() -> None:
    feed = _feed()
    app = FastAPI()
    app.state.tickchart = feed
    app.include_router(tickchart_router)
    followed = TestClient(app).post("/api/v1/tickchart/follow", json={"symbol": "1120"})
    assert followed.status_code == 200
    assert followed.json()["symbol"] == "1120"
    refreshed = TestClient(app).post("/api/v1/tickchart/refresh", json={})
    assert refreshed.status_code == 200
    assert refreshed.json()["success"] is True
