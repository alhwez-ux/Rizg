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


def test_recommendations_endpoint_returns_scanned_opportunities(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_live(_provider: object, *, use_cache: bool = True) -> list[dict[str, object]]:
        return MarketRecommendationsEngine(
            {"1120": _momentum_frame(), "2222": _bounce_frame()},
            names={"1120": "مصرف الراجحي", "2222": "أرامكو السعودية"},
        ).scan_for_opportunities()

    from app.core.config import Settings
    from app.services.sahm_data_provider import SahmDataProvider

    monkeypatch.setattr("app.routers.market.live_market_recommendations", fake_live)
    app = FastAPI()
    app.state.sahm = SahmDataProvider(
        Settings(_env_file=None, sahmk_api_key="test-key", telegram_bot_token="", telegram_chat_id=""),
        api_key="test-key",
    )
    app.include_router(market_router)
    response = TestClient(app).get("/api/v1/market/recommendations")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["count"] == len(payload["data"])
    assert payload["count"] >= 2
    symbols = {row["symbol"] for row in payload["data"]}
    assert {"1120", "2222"} <= symbols
    assert all(row["entry_price"] and row["reason"] for row in payload["data"])


def test_recommendations_endpoint_falls_back_without_sahm() -> None:
    app = FastAPI()
    app.include_router(market_router)
    response = TestClient(app).get("/api/v1/market/recommendations")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["count"] == 0
    assert payload["data"] == []
