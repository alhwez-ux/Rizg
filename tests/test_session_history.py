from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.models.screener import is_tasi_main_symbol
from app.routers.tickchart import router as tickchart_router
from app.services.last_quotes import LastQuoteBook
from app.services.liquidity_engine import LiquidityRadarEngine
from app.services.session_history import listed_main_market_symbols, main_market_symbols, parse_spark_bars, parse_spark_market
from app.services.tickchart_integration import TickChartFeed

_RIYADH = ZoneInfo("Asia/Riyadh")


class _Broadcaster:
    async def broadcast(self, symbol: str, message: dict) -> None:
        return None

    def subscribed_symbols(self) -> set[str]:
        return set()


def test_is_tasi_main_symbol_excludes_nomu_and_etfs() -> None:
    assert is_tasi_main_symbol("2222") is True
    assert is_tasi_main_symbol("4330") is True
    assert is_tasi_main_symbol("9510") is False
    assert is_tasi_main_symbol("9400") is False
    assert is_tasi_main_symbol("TASI") is False


def test_merge_history_keeps_today_quote_and_adds_ten_priors(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.last_quotes.now_riyadh",
        lambda: datetime(2026, 9, 14, 17, 0, tzinfo=_RIYADH),
    )
    book = LastQuoteBook(tmp_path / "quotes.json")
    today = date(2026, 9, 14)
    book.remember("2222", 25.66, volume=5_671_859, session_date=today)
    prior = [
        {
            "symbol": "2222",
            "close": 25.0 + index * 0.05,
            "volume": 1_000_000 + index,
            "date": (today - timedelta(days=14 - index)).isoformat(),
        }
        for index in range(10)
    ]
    prior.append({"symbol": "2222", "close": 99.0, "volume": 1, "date": today.isoformat()})
    prior.append({"symbol": "9510", "close": 10.0, "volume": 100, "date": (today - timedelta(days=1)).isoformat()})
    imported = book.merge_history(prior)
    assert imported == 10
    assert book.price("2222") == 25.66
    history = book.close_history("2222")
    assert len(history) == 11
    assert history[-1]["close"] == 25.66
    assert history[-1]["date"] == "2026-09-14"
    assert book.close_history("9510") == []


def test_parse_spark_bars_keeps_main_market_sessions_before_today() -> None:
    stamps = [
        int(datetime(2026, 9, day, 12, tzinfo=_RIYADH).timestamp())
        for day in (10, 11, 14)
    ]
    payload = {
        "spark": {
            "result": [
                {
                    "symbol": "2222.SR",
                    "response": [
                        {
                            "timestamp": stamps,
                            "indicators": {
                                "quote": [
                                    {
                                        "close": [25.4, 25.5, 25.66],
                                        "volume": [1_000_000, 1_100_000, 5_000_000],
                                    }
                                ]
                            },
                        }
                    ],
                },
                {
                    "symbol": "9510.SR",
                    "response": [
                        {
                            "timestamp": stamps[:1],
                            "indicators": {"quote": [{"close": [12.1], "volume": [50_000]}]},
                        }
                    ],
                },
            ]
        }
    }
    rows = parse_spark_bars(payload, today=date(2026, 9, 14), sessions=10)
    symbols = {row["symbol"] for row in rows}
    assert symbols == {"2222"}
    assert [row["date"] for row in rows] == ["2026-09-10", "2026-09-11"]
    bars, quotes = parse_spark_market(payload, today=date(2026, 9, 14), sessions=10)
    assert [row["date"] for row in bars] == ["2026-09-10", "2026-09-11"]
    assert quotes[0]["symbol"] == "2222"
    assert quotes[0]["last_price"] == 25.66
    assert quotes[0]["prev_close"] == 25.5
    assert all(row["symbol"] != "9510" for row in quotes)


def test_main_market_symbols_filters_nomu() -> None:
    assert main_market_symbols(["2222", "9510", "2222.SR", "TASI", "1120"]) == ["2222", "1120"]
    assert "2222" in listed_main_market_symbols()
    assert "9510" not in listed_main_market_symbols()


def test_history_endpoint_imports_main_market_bars_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.last_quotes.now_riyadh",
        lambda: datetime(2026, 9, 14, 17, 0, tzinfo=_RIYADH),
    )
    quotes = LastQuoteBook(tmp_path / "quotes.json")
    quotes.remember("2222", 25.66, volume=5_000_000, session_date=date(2026, 9, 14))
    settings = Settings(
        _env_file=None,
        tickchart_enabled=True,
        tickchart_autosync_enabled=False,
        tickchart_api_key="",
        sahmk_api_key="",
        enable_mock_feed=False,
    )
    feed = TickChartFeed(LiquidityRadarEngine(), _Broadcaster(), settings, quotes=quotes)
    app = FastAPI()
    app.state.tickchart = feed
    app.state.settings = settings
    app.include_router(tickchart_router)
    response = TestClient(app).post(
        "/api/v1/tickchart/history",
        json={
            "bars": [
                {"symbol": "2222", "date": "2026-09-13", "close": 25.72, "volume": 7_000_000},
                {"symbol": "9510", "date": "2026-09-13", "close": 11.2, "volume": 80_000},
            ]
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["market"] == "TASI_MAIN"
    assert payload["imported"] == 1
    history = quotes.close_history("2222")
    assert [row["date"] for row in history] == ["2026-09-13", "2026-09-14"]
    assert quotes.close_history("9510") == []
