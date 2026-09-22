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


def test_parse_uniticker_market_watch_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "tasi_watch.tsv"
    path.write_text(
        "\t".join(
            [
                "السوق",
                "الرمز",
                "الاسم",
                "آخر",
                "الطلب",
                "العرض",
                "الحجم",
                "القيمة",
                "الصفقات",
                "إفتتاح",
                "أعلى",
                "أدنى",
                "الإغلاق السابق",
                "تدفق السيولة",
                "صافي السيولة",
                "نسبة السيولة %",
            ]
        )
        + "\n"
        + "\t".join(
            [
                "السعودية",
                "TASI",
                "تاسي",
                "10,862.92",
                "-",
                "-",
                "73,872,604",
                "1,729,683,178",
                "173,899",
                "10,906.23",
                "10,838.78",
                "10,864.57",
                "10,864.57",
                "1.09",
                "73,581,069",
                "52.16",
            ]
        )
        + "\n"
        + "\t".join(
            [
                "السعودية",
                "2222",
                "أرامكو السعودية",
                "25.66",
                "25.64",
                "25.68",
                "9,156,271",
                "73,581,069",
                "151",
                "25.70",
                "25.72",
                "25.52",
                "25.70",
                "1.231",
                "20,734,487",
                "55.17",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    payloads = parse_export_file(path)
    quotes = [item for item in payloads if item.get("type") == "quote"]
    depth = [item for item in payloads if item.get("type") == "depth_snapshot"]
    assert [item["symbol"] for item in quotes] == ["2222"]
    assert quotes[0]["price"] == "25.66"
    assert quotes[0]["session_volume"] == "9156271"
    assert quotes[0]["net_flow"] == "20734487"
    assert quotes[0]["open"] == "25.70"
    assert depth[0]["symbol"] == "2222"
    assert depth[0]["best_bid"] == "25.64"
    assert depth[0]["best_ask"] == "25.68"


def test_parse_uniticker_headerless_clipboard_dump(tmp_path: Path) -> None:
    path = tmp_path / "tasi_watch.txt"
    path.write_text(
        "3\t0\t0\t4\tالسعودية\tTASI\tتاسي\t10,878.46\t-1\t13.89\t0.13\t-\t-\t-\t-\t175,930,585\t4,185,715,433\t397,489\t10,862.52\t10,906.23\t10,838.78\t10,864.57\t1.011\t22,835,876\t50.28\n"
        "3\t0\t0\t0\tالسعودية\t2030\tالمصافي\t58.95\t0\t5.35\t9.98\t224,094\t58.95\t59.00\t1,746\t721,081\t40,707,578\t4,515\t53.60\t58.95\t53.20\t53.60\t0.981\t-382,594\t49.53\n"
        "3\t0\t0\t0\tالسعودية\t2222\tأرامكو السعودية\t25.66\t0\t-0.06\t-0.23\t72,240\t25.66\t25.68\t205\t5,671,859\t145,606,258\t13,697\t25.70\t25.82\t25.52\t25.72\t0.784\t-17,624,308\t43.95\n",
        encoding="utf-8",
    )
    payloads = parse_export_file(path)
    quotes = {item["symbol"]: item for item in payloads if item.get("type") == "quote"}
    assert "TASI" not in quotes
    assert quotes["2222"]["price"] == "25.66"
    assert quotes["2030"]["price"] == "58.95"
    assert quotes["2222"]["session_volume"] == "5671859"
    assert quotes["2222"]["net_flow"] == "-17624308"


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


def test_local_discover_includes_project_export_folder(tmp_path: Path, monkeypatch) -> None:
    from app.services.tickchart_autosync import discover_export_dirs, folder_watch_allowed

    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("RENDER_SERVICE_ID", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "tickchart_live").mkdir(parents=True)
    settings = Settings(
        _env_file=None,
        environment="development",
        tickchart_enabled=True,
        tickchart_autosync_enabled=True,
        tickchart_export_dir="",
    )
    assert folder_watch_allowed(settings) is True
    dirs = {str(path) for path in discover_export_dirs(settings)}
    assert str((tmp_path / "data" / "tickchart_live").resolve()) in dirs


def test_discover_includes_uniticker_export_folder(tmp_path: Path, monkeypatch) -> None:
    from app.services.tickchart_autosync import discover_export_dirs

    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("RENDER_SERVICE_ID", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "pf86"))
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "pf"))
    tclive = tmp_path / "UniTicker" / "TCLive"
    tclive.mkdir(parents=True)
    settings = Settings(
        _env_file=None,
        environment="development",
        tickchart_enabled=True,
        tickchart_autosync_enabled=True,
        tickchart_export_dir="",
    )
    dirs = {str(path) for path in discover_export_dirs(settings)}
    assert str((tclive / "Export").resolve()) in dirs


def test_follow_and_refresh_are_cloud_endpoints(tmp_path: Path) -> None:
    from app.services.last_quotes import LastQuoteBook
    from app.services.under_watch import UnderWatchService

    settings = Settings(
        _env_file=None,
        tickchart_enabled=True,
        tickchart_autosync_enabled=True,
        tickchart_api_key="",
        sahmk_api_key="",
        enable_mock_feed=False,
    )
    feed = TickChartFeed(
        LiquidityRadarEngine(),
        _Broadcaster(),
        settings,
        quotes=LastQuoteBook(path=tmp_path / "quotes.json"),
        under_watch=UnderWatchService(path=tmp_path / "under_watch.json"),
    )
    app = FastAPI()
    app.state.tickchart = feed
    app.include_router(tickchart_router)
    followed = TestClient(app).post("/api/v1/tickchart/follow", json={"symbol": "1120"})
    assert followed.status_code == 200
    assert followed.json()["symbol"] == "1120"
    refreshed = TestClient(app).post("/api/v1/tickchart/refresh", json={})
    assert refreshed.status_code == 200
    assert refreshed.json()["success"] is True
