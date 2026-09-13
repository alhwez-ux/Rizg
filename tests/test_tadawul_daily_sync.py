import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.routers.market import router as market_router
from app.services.ranking_store import RankingStore
from app.services.tasi_clock import TASI_TZ
from app.services.tadawul_daily_sync import TadawulDailySync


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        tadawul_daily_sync_enabled=False,
        tadawul_daily_sync_on_startup=False,
        financial_sync_enabled=False,
        tasi_scheduler_enabled=False,
    )


def _reachable_tadawul() -> AsyncMock:
    return AsyncMock(return_value=200)


def test_should_catch_up_after_four_pm_on_a_session_day(tmp_path: Path) -> None:
    sync = TadawulDailySync(_settings(), tape_path=tmp_path / "tape.json", enable_scheduler=False)
    sunday_evening = datetime(2026, 9, 13, 16, 5, tzinfo=TASI_TZ)
    assert sync.should_catch_up(sunday_evening) is True
    friday = datetime(2026, 9, 18, 17, 0, tzinfo=TASI_TZ)
    assert sync.should_catch_up(friday) is False
    morning = datetime(2026, 9, 13, 11, 0, tzinfo=TASI_TZ)
    assert sync.should_catch_up(morning) is False


def test_save_tape_and_update_ranking(tmp_path: Path) -> None:
    store = RankingStore(path=tmp_path / "rankings.json")
    store.replace(
        [
            {
                "symbol": "2222",
                "name": "أرامكو السعودية",
                "profit_growth": 4.0,
                "dividend_yield": 5.1,
                "roe": 20.0,
                "roa": 12.0,
                "pe_ratio": 16.0,
                "net_income": 100000,
            }
        ],
        "2026-09-10T12:00:00+03:00",
    )
    sync = TadawulDailySync(
        _settings(),
        ranking_store=store,
        tape_path=tmp_path / "tape.json",
        enable_scheduler=False,
    )
    rows = [
        {
            "symbol": "2222",
            "name": "أرامكو السعودية",
            "sector": "الطاقة",
            "close": 26.14,
            "change_percent": 0.38,
            "volume": 4_536_304,
            "value_traded": 118_600_000,
            "as_of": "2026-09-13",
        }
    ]
    sync.save_to_database(rows, as_of="2026-09-13")
    updated = sync.update_ranking_matrix(rows)
    assert updated == 1
    tape = (tmp_path / "tape.json").read_text(encoding="utf-8")
    assert "26.14" in tape
    snapshot = store.snapshot()
    assert snapshot[0]["symbol"] == "2222"
    assert snapshot[0]["last_price"] == 26.14
    assert snapshot[0]["volume"] == 4_536_304


def test_fetch_merges_board_and_quotes() -> None:
    sahm = MagicMock()
    sahm.enabled = True
    sahm.fetch_company_directory = AsyncMock(
        return_value=[{"symbol": "2222", "name_ar": "أرامكو السعودية", "sector": "الطاقة", "status": "active"}]
    )
    sahm.fetch_market_board = AsyncMock(
        return_value={
            "gainers": [],
            "volume": [
                {
                    "symbol": "2222",
                    "price": 26.14,
                    "change_percent": 0.38,
                    "volume": 1000,
                    "value": 2000,
                    "name": "أرامكو السعودية",
                }
            ],
            "value": [],
        }
    )
    sahm.fetch_quotes_for = AsyncMock(return_value={})
    sync = TadawulDailySync(_settings(), sahm=sahm, enable_scheduler=False)
    rows = asyncio.run(sync.fetch_daily_market_data())
    by_symbol = {row["symbol"]: row for row in rows}
    assert "2222" in by_symbol
    assert by_symbol["2222"]["close"] == 26.14
    assert by_symbol["2222"]["change_percent"] == 0.38


def test_run_without_sahm_leaves_ranking_untouched(tmp_path: Path) -> None:
    store = RankingStore(path=tmp_path / "rankings.json")
    sync = TadawulDailySync(
        _settings(),
        sahm=None,
        ranking_store=store,
        tape_path=tmp_path / "tape.json",
        enable_scheduler=False,
        tadawul_get=_reachable_tadawul(),
    )
    result = asyncio.run(sync.run_daily_sync())
    assert result["symbols"] == 0
    assert result["ranking_updated"] == 0
    assert result["used_last_recorded"] is True
    assert store.snapshot() == []


def test_sync_market_closing_prices_updates_tape(tmp_path: Path) -> None:
    sahm = MagicMock()
    sahm.enabled = True
    sahm.fetch_company_directory = AsyncMock(return_value=[{"symbol": "2222", "name_ar": "أرامكو", "status": "active"}])
    sahm.fetch_market_board = AsyncMock(
        return_value={
            "gainers": [],
            "volume": [{"symbol": "2222", "price": 26.14, "change_percent": 0.38, "volume": 1000, "value": 2000}],
            "value": [],
        }
    )
    sahm.fetch_quotes_for = AsyncMock(return_value={})
    store = RankingStore(path=tmp_path / "rankings.json")
    sync = TadawulDailySync(
        _settings(),
        sahm=sahm,
        ranking_store=store,
        tape_path=tmp_path / "tape.json",
        enable_scheduler=False,
        tadawul_get=_reachable_tadawul(),
    )
    result = sync.sync_market_closing_prices()
    assert result["job"] == "daily_close"
    assert result["symbols"] >= 1
    assert result["used_last_recorded"] is False
    assert (tmp_path / "tape.json").exists()


def test_non_200_tadawul_keeps_last_tape(tmp_path: Path) -> None:
    store = RankingStore(path=tmp_path / "rankings.json")
    sync = TadawulDailySync(
        _settings(),
        ranking_store=store,
        tape_path=tmp_path / "tape.json",
        enable_scheduler=False,
        tadawul_get=AsyncMock(return_value=503),
    )
    sync.save_to_database(
        [
            {
                "symbol": "2222",
                "name": "أرامكو السعودية",
                "sector": "الطاقة",
                "close": 26.14,
                "change_percent": 0.38,
                "volume": 1000,
                "value_traded": 2000,
                "as_of": "2026-09-10",
            }
        ],
        as_of="2026-09-10",
    )
    result = sync.sync_market_closing_prices()
    assert result["used_last_recorded"] is True
    assert result["as_of"] == "2026-09-10"
    assert result["tadawul_status"] == 503
    assert store.snapshot() == []


def test_network_error_falls_back_to_last_tape(tmp_path: Path) -> None:
    sync = TadawulDailySync(
        _settings(),
        tape_path=tmp_path / "tape.json",
        enable_scheduler=False,
        tadawul_get=AsyncMock(side_effect=httpx.ConnectError("offline")),
    )
    result = sync.sync_market_closing_prices()
    assert result["used_last_recorded"] is True
    assert result["reason"] == "network"


def test_start_registers_16_00_cron() -> None:
    settings = Settings(
        _env_file=None,
        tadawul_daily_sync_enabled=True,
        tadawul_daily_sync_on_startup=False,
        financial_sync_enabled=False,
        tasi_scheduler_enabled=False,
    )
    sync = TadawulDailySync(settings, enable_scheduler=True)
    try:
        sync.start()
        job = sync.scheduler.get_job("tadawul_daily_close")
        assert job is not None
        trigger = str(job.trigger)
        assert "hour='16'" in trigger or "16" in trigger
    finally:
        sync.shutdown()


def test_daily_sync_status_endpoint() -> None:
    app = FastAPI()
    app.include_router(market_router)
    app.state.tadawul_daily_sync = TadawulDailySync(_settings(), enable_scheduler=False)
    response = TestClient(app).get("/api/v1/market/daily-sync")
    assert response.status_code == 200
    body = response.json()
    assert body["timezone"] == "Asia/Riyadh"
    assert body["hour"] == 16
    assert body["success"] is True
