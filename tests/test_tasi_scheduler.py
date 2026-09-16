import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.routers.market import router as market_router
from app.services.tasi_clock import TASI_TZ, is_intraday_window, session_phase
from app.services.tasi_scheduler import TasiMarketScheduler


def _settings() -> Settings:
    return Settings(_env_file=None, tasi_scheduler_enabled=False, financial_sync_enabled=False)


def test_preopen_and_session_and_close_phases() -> None:
    sunday_open = datetime(2026, 9, 13, 10, 15, tzinfo=TASI_TZ)
    assert session_phase(sunday_open) == "open"
    assert is_intraday_window(sunday_open)

    preopen = datetime(2026, 9, 13, 9, 30, tzinfo=TASI_TZ)
    assert session_phase(preopen) == "preopen"
    assert not is_intraday_window(preopen)

    close_bell = datetime(2026, 9, 13, 15, 30, tzinfo=TASI_TZ)
    assert session_phase(close_bell) == "closed"

    friday = datetime(2026, 9, 18, 11, 0, tzinfo=TASI_TZ)
    assert session_phase(friday) == "weekend"
    assert not is_intraday_window(friday)


def test_scan_skips_outside_session(monkeypatch) -> None:
    monkeypatch.setattr("app.services.tasi_scheduler.is_intraday_window", lambda moment=None: False)
    scheduler = TasiMarketScheduler(_settings(), enable_scheduler=False)
    result = asyncio.run(scheduler.scan_session())
    assert result["skipped"] is True
    assert result["reason"] == "outside_session"


def test_open_prep_lists_major_symbols_without_sahm() -> None:
    scheduler = TasiMarketScheduler(_settings(), sahm=None, enable_scheduler=False)
    result = asyncio.run(scheduler.prepare_open())
    assert result["job"] == "open"
    assert result["symbols"] >= 4
    assert result["quotes"][0]["symbol"]


def test_close_uses_tickchart_opportunities() -> None:
    class _Feed:
        def opportunities(self):
            return [{"symbol": "2222"}, {"symbol": "1120"}]

    scheduler = TasiMarketScheduler(_settings(), sahm=None, tickchart=_Feed(), enable_scheduler=False)
    result = asyncio.run(scheduler.close_market())
    assert result["job"] == "close"
    assert result["ranking_updated"] == 0
    assert result["recommendations"] == 2


def test_forced_scan_sends_trap_alert(monkeypatch) -> None:
    monkeypatch.setattr("app.services.tasi_scheduler.is_intraday_window", lambda moment=None: True)

    class _Feed:
        enabled = True

        def radar_report(self, symbol):
            return {
                "symbol": symbol,
                "signal": "trap",
                "trap": {"kind": "bull_trap", "label": "فخ"},
                "score": 81,
                "last_price": 36.6,
            }

    telegram = MagicMock()
    telegram.send_radar_event = AsyncMock(return_value=True)
    scheduler = TasiMarketScheduler(
        _settings(),
        sahm=None,
        tickchart=_Feed(),
        telegram=telegram,
        enable_scheduler=False,
    )
    result = asyncio.run(scheduler.scan_session(force=True))
    assert result["scanned"] >= 1
    assert result["alerts"] >= 1
    telegram.send_radar_event.assert_called()


def test_close_notifies_telegram_for_each_recommendation() -> None:
    class _Feed:
        def close_recommendations(self):
            return [
                {
                    "symbol": "2222",
                    "name": "أرامكو",
                    "entry": True,
                    "reason": "كسر إغلاق اليوم",
                    "entry_price": "27.10",
                }
            ]

    telegram = MagicMock()
    telegram.send_radar_event = AsyncMock(return_value=True)
    telegram.enabled = True
    telegram.send_message = AsyncMock(return_value=True)
    scheduler = TasiMarketScheduler(
        _settings(),
        sahm=None,
        tickchart=_Feed(),
        telegram=telegram,
        enable_scheduler=False,
    )
    result = asyncio.run(scheduler.close_market())
    assert result["recommendations"] == 1
    telegram.send_radar_event.assert_called()
    payload = telegram.send_radar_event.call_args.args[0]
    assert payload["symbol"] == "2222"
    assert payload["signal"] == "entry"


def test_scheduler_status_endpoint() -> None:
    app = FastAPI()
    app.include_router(market_router)
    app.state.tasi_scheduler = TasiMarketScheduler(_settings(), enable_scheduler=False)
    response = TestClient(app).get("/api/v1/market/scheduler")
    assert response.status_code == 200
    body = response.json()
    assert body["timezone"] == "Asia/Riyadh"
    assert body["phase_label"]
    assert body["success"] is True
