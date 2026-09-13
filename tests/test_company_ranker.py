from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.market import router as market_router
from app.services.company_ranker import (
    CATEGORY_LOSER,
    SAMPLE_COMPANIES,
    CompanyRankingEngine,
)


def test_empty_financials_return_empty_payload() -> None:
    engine = CompanyRankingEngine([])
    assert engine.get_ranked_payload() == []


def test_losing_company_is_ranked_last() -> None:
    engine = CompanyRankingEngine(
        [
            {
                "symbol": "2010",
                "name": "سابك",
                "profit_growth": -15.0,
                "dividend_yield": 2.5,
                "roe": 3.2,
                "pe_ratio": 35.0,
                "net_income": -500,
            },
            {
                "symbol": "1120",
                "name": "الراجحي",
                "profit_growth": 12.5,
                "dividend_yield": 3.2,
                "roe": 18.4,
                "pe_ratio": 16.2,
                "net_income": 16000,
            },
        ]
    )
    ranked = engine.get_ranked_payload()
    assert ranked[0]["symbol"] == "1120"
    assert ranked[0]["rank"] == 1
    assert ranked[-1]["symbol"] == "2010"
    assert ranked[-1]["category"] == CATEGORY_LOSER
    assert ranked[-1]["matrix_score"] == -1000


def test_sample_matrix_orders_profitability_and_dividends() -> None:
    ranked = CompanyRankingEngine(SAMPLE_COMPANIES).get_ranked_payload()
    symbols = [row["symbol"] for row in ranked]
    assert symbols[-1] == "2010"
    assert "1120" in symbols
    assert "2222" in symbols
    scores = {row["symbol"]: row["matrix_score"] for row in ranked}
    assert scores["2222"] > scores["1211"]
    assert scores["1120"] > scores["4030"]


def test_ranking_matrix_endpoint_returns_sorted_payload() -> None:
    app = FastAPI()
    app.include_router(market_router)
    response = TestClient(app).get("/api/v1/market/ranking-matrix")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["total_companies"] == len(payload["data"])
    assert payload["total_companies"] >= 4
    scores = [row["matrix_score"] for row in payload["data"]]
    assert scores == sorted(scores, reverse=True)
    assert payload["data"][-1]["symbol"] == "2010"
    assert payload["data"][0]["rank"] == 1
