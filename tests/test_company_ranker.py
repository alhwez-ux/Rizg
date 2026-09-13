from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.market import router as market_router
from app.services.ranking_store import RankingStore
from app.services.company_ranker import (
    CATEGORY_LOSER,
    SAMPLE_COMPANIES,
    CompanyRankingEngine,
    MAJOR_TASI_COMPANIES,
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


def test_ranking_matrix_endpoint_returns_sorted_payload(tmp_path) -> None:
    ranked = CompanyRankingEngine(SAMPLE_COMPANIES).get_ranked_payload()
    store = RankingStore(tmp_path / "rankings.json")
    store.replace(ranked, "2026-09-13T00:00:00+00:00")
    app = FastAPI()
    app.state.ranking_store = store
    app.include_router(market_router)
    response = TestClient(app).get("/api/v1/market/ranking-matrix")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["source"] == "cached"
    assert payload["total_companies"] == len(payload["data"])
    assert payload["total_companies"] >= 4
    scores = [row["matrix_score"] for row in payload["data"]]
    assert scores == sorted(scores, reverse=True)
    assert payload["data"][-1]["symbol"] == "2010"
    assert payload["data"][0]["rank"] == 1


def test_major_tasi_universe_covers_blue_chips() -> None:
    symbols = {row["symbol"] for row in MAJOR_TASI_COMPANIES}
    assert {"1120", "1180", "1010", "2222", "2010", "7010", "2082", "4013"} <= symbols
    assert len(MAJOR_TASI_COMPANIES) >= 40


def test_merge_keeps_fundamentals_when_quote_is_only_daily_change() -> None:
    from app.services.company_ranker import merge_ranking_financials

    row = merge_ranking_financials(
        "1120",
        "الراجحي",
        quote={"symbol": "1120", "change_percent": 1.4, "price": 96.4, "volume": 5000},
        stored={
            "symbol": "1120",
            "name": "الراجحي",
            "profit_growth": 12.5,
            "pe_ratio": 16.2,
            "roe": 18.4,
        },
    )
    assert row["profit_growth"] == 12.5
    assert row["pe_ratio"] == 16.2
    assert row["roe"] == 18.4
    assert row["last_price"] == 96.4


def test_merge_does_not_invent_fundamentals_from_daily_change() -> None:
    from app.services.company_ranker import merge_ranking_financials

    row = merge_ranking_financials(
        "1120",
        "الراجحي",
        quote={"symbol": "1120", "change_percent": 1.4, "price": 96.4, "volume": 5000},
    )
    assert row["profit_growth"] is None
    assert row["pe_ratio"] is None
    assert row["roe"] is None
    assert row["last_price"] == 96.4
