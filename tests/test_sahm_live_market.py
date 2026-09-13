from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.market import router as market_router
from app.services.ranking_store import RankingStore


def test_ranking_matrix_overlays_tickchart_prices(tmp_path) -> None:
    store = RankingStore(tmp_path / "rankings.json")
    store.replace(
        [
            {
                "symbol": "1120",
                "name": "الراجحي",
                "profit_growth": None,
                "pe_ratio": 15.8,
                "roe": 19.0,
                "last_price": 1,
                "rank": 1,
            },
            {
                "symbol": "2222",
                "name": "أرامكو السعودية",
                "profit_growth": 2.0,
                "pe_ratio": 16.0,
                "roe": 20.0,
                "last_price": 1,
                "rank": 2,
            },
        ],
        "2026-09-14T00:00:00+00:00",
        source="stored",
    )

    class _Feed:
        def market_rows(self):
            return [
                {"symbol": "1120", "last_price": 90.0, "volume": 1000},
                {"symbol": "2222", "last_price": 25.7, "volume": 2000},
            ]

    app = FastAPI()
    app.state.tickchart = _Feed()
    app.state.ranking_store = store
    app.include_router(market_router)
    response = TestClient(app).get("/api/v1/market/ranking-matrix")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "TickChart"
    symbols = {row["symbol"] for row in payload["data"]}
    assert {"1120", "2222"} <= symbols
    rajhi = next(row for row in payload["data"] if row["symbol"] == "1120")
    assert rajhi["profit_growth"] is None
    assert rajhi["pe_ratio"] == 15.8
    assert rajhi["roe"] == 19.0
    assert rajhi["last_price"] == 90.0
