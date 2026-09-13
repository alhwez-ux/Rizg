from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.market import router as market_router
from app.services.recommendations_engine import (
    KIND_BOUNCE,
    KIND_MOMENTUM,
    MarketRecommendationsEngine,
    SIGNAL_BOUNCE,
    SIGNAL_MOMENTUM,
    clear_recommendations_cache,
    live_market_recommendations,
)


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    clear_recommendations_cache()
    yield
    clear_recommendations_cache()


def _bars(
    symbol: str,
    closes: list[float],
    *,
    volumes: list[float] | None = None,
    lows: list[float] | None = None,
    highs: list[float] | None = None,
    opens: list[float] | None = None,
) -> pd.DataFrame:
    n = len(closes)
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    stamps = [start + timedelta(days=index) for index in range(n)]
    close = [float(value) for value in closes]
    volume = volumes if volumes is not None else [1_000.0] * n
    opened = opens if opens is not None else close
    high = highs if highs is not None else [price * 1.01 for price in close]
    low = lows if lows is not None else [price * 0.99 for price in close]
    return pd.DataFrame(
        {
            "timestamp": stamps,
            "symbol": [symbol] * n,
            "open": opened,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


def _momentum_frame() -> pd.DataFrame:
    closes = [80.0 + index * 0.35 for index in range(24)]
    volumes = [1_000.0] * 21 + [2_200.0, 2_400.0, 3_100.0]
    return _bars("1120", closes, volumes=volumes)


def _bounce_frame() -> pd.DataFrame:
    decline = [31.0 - index * 0.18 for index in range(24)]
    last_open = decline[-1]
    closes = decline[:-1] + [28.35]
    opens = decline[:-1] + [last_open]
    highs = [price * 1.004 for price in decline[:-1]] + [28.45]
    lows = [price * 0.992 for price in decline[:-1]] + [26.85]
    volumes = [900.0] * 23 + [2_800.0]
    return _bars("2222", closes, volumes=volumes, opens=opens, highs=highs, lows=lows)


def _flat_frame() -> pd.DataFrame:
    closes = [27.5 + ((index % 3) - 1) * 0.05 for index in range(24)]
    return _bars("4030", closes)


def test_engine_detects_momentum_and_bounce() -> None:
    engine = MarketRecommendationsEngine(
        {"1120": _momentum_frame(), "2222": _bounce_frame(), "4030": _flat_frame()},
        names={"1120": "مصرف الراجحي", "2222": "أرامكو السعودية", "4030": "البحري"},
    )
    rows = engine.scan_for_opportunities()
    kinds = {row["symbol"]: row["signal_kind"] for row in rows}
    assert kinds["1120"] == KIND_MOMENTUM
    assert kinds["2222"] == KIND_BOUNCE
    assert "4030" not in kinds
    rajhi = next(row for row in rows if row["symbol"] == "1120")
    aramco = next(row for row in rows if row["symbol"] == "2222")
    assert rajhi["signal_type"] == SIGNAL_MOMENTUM
    assert aramco["signal_type"] == SIGNAL_BOUNCE
    assert rajhi["confidence"].endswith("%")
    assert float(rajhi["target_price"]) > rajhi["close_price"] > float(rajhi["stop_loss"])
    assert float(aramco["target_price"]) > aramco["close_price"] > float(aramco["stop_loss"])
    assert rows[0]["confidence_score"] >= rows[-1]["confidence_score"]


def test_engine_skips_short_or_empty_frames() -> None:
    short = _bars("1180", [20.0, 20.2, 20.4])
    engine = MarketRecommendationsEngine({"1180": short, "1010": pd.DataFrame()})
    assert engine.scan_for_opportunities() == []


def test_live_recommendations_require_api_key() -> None:
    import asyncio

    from app.core.config import Settings
    from app.core.exceptions import SahmApiError
    from app.services.sahm_data_provider import SahmDataProvider

    provider = SahmDataProvider(Settings(_env_file=None, sahmk_api_key=""), api_key="")
    with pytest.raises(SahmApiError) as exc:
        asyncio.run(live_market_recommendations(provider, use_cache=False))
    assert exc.value.status_code == 503


def test_recommendations_endpoint_returns_scanned_opportunities() -> None:
    class _Feed:
        def opportunities(self):
            return MarketRecommendationsEngine(
                {"1120": _momentum_frame(), "2222": _bounce_frame()},
                names={"1120": "مصرف الراجحي", "2222": "أرامكو السعودية"},
            ).scan_for_opportunities()

    app = FastAPI()
    app.state.tickchart = _Feed()
    app.include_router(market_router)
    response = TestClient(app).get("/api/v1/market/recommendations")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["source"] == "TickChart"
    assert payload["scan_mode"] in {"live", "end_of_day"}
    assert payload["session_phase"]
    assert payload["count"] == len(payload["data"])
    assert payload["count"] >= 2
    symbols = {row["symbol"] for row in payload["data"]}
    assert {"1120", "2222"} <= symbols
    assert all(row["entry_price"] and row["reason"] for row in payload["data"])


def test_recommendations_endpoint_end_of_day_uses_last_close(monkeypatch, tmp_path) -> None:
    from pathlib import Path

    import httpx

    from app.core.config import Settings
    from app.services.last_quotes import LastQuoteBook
    from app.services.liquidity_engine import LiquidityRadarEngine
    from app.services.tickchart_integration import TickChartFeed

    monkeypatch.setattr("app.services.tickchart_integration.session_phase", lambda moment=None: "closed")
    monkeypatch.setattr("app.routers.market.session_phase", lambda moment=None: "closed")

    class _Store:
        def snapshot(self):
            return [
                {"symbol": "1120", "name": "الراجحي", "last_price": 96.4, "volume": 8_200_000},
                {"symbol": "1180", "name": "الأهلي", "last_price": 38.1, "volume": 900_000},
                {"symbol": "1010", "name": "الرياض", "last_price": 27.4, "volume": 800_000},
            ]

    class _Broadcaster:
        async def broadcast(self, symbol: str, message: dict) -> None:
            return None

        def subscribed_symbols(self) -> set[str]:
            return set()

    settings = Settings(_env_file=None, tickchart_api_key="test-key", sahmk_api_key="test-key", enable_mock_feed=False)
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"events": [], "bids": [], "asks": []}))
    )
    feed = TickChartFeed(
        LiquidityRadarEngine(),
        _Broadcaster(),
        settings,
        client=client,
        quotes=LastQuoteBook(Path(tmp_path) / "quotes.json"),
    )
    feed.bind_ranking_store(_Store())
    app = FastAPI()
    app.state.tickchart = feed
    app.include_router(market_router)
    response = TestClient(app).get("/api/v1/market/recommendations")
    assert response.status_code == 200
    payload = response.json()
    assert payload["scan_mode"] == "end_of_day"
    assert payload["session_label"] == "السوق مغلق"
    assert payload["count"] >= 1
    symbols = {row["symbol"] for row in payload["data"]}
    assert "1120" in symbols
    assert all(row.get("horizon") == "next_session" for row in payload["data"])
    assert all("إغلاق" in row["reason"] or "الغد" in row["reason"] for row in payload["data"])


def test_recommendations_endpoint_falls_back_without_sahm() -> None:
    app = FastAPI()
    app.include_router(market_router)
    response = TestClient(app).get("/api/v1/market/recommendations")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["count"] == 0
    assert payload["data"] == []
