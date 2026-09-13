from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.routers.market import router as market_router
from app.services.financial_sync_service import FinancialSyncService
from app.services.ranking_store import RankingStore


def _settings(**overrides: object) -> Settings:
    payload: dict[str, object] = {
        "financial_sync_enabled": False,
        "financial_sync_run_on_startup": False,
        "telegram_bot_token": "",
        "telegram_chat_id": "",
    }
    payload.update(overrides)
    return Settings(_env_file=None, **payload)


def test_sync_persists_ranked_matrix(tmp_path) -> None:
    store = RankingStore(tmp_path / "company_rankings.json")
    service = FinancialSyncService(
        _settings(),
        store=store,
        enable_scheduler=False,
        provider=lambda: [
            {
                "symbol": "1120",
                "name": "الراجحي",
                "profit_growth": 14.1,
                "dividend_yield": 3.4,
                "roe": 19.0,
                "pe_ratio": 15.8,
                "net_income": 16500,
            },
            {
                "symbol": "2010",
                "name": "سابك",
                "profit_growth": -15.0,
                "dividend_yield": 2.5,
                "roe": 3.2,
                "pe_ratio": 35.0,
                "net_income": -500,
            },
        ],
    )
    result = service.sync_market_financials()
    assert result["updated"] == 2
    rows = store.snapshot()
    assert rows[0]["symbol"] == "1120"
    assert rows[0]["profit_growth"] == 14.1
    assert rows[-1]["symbol"] == "2010"
    assert store.synced_at()


def test_empty_provider_leaves_store_unchanged(tmp_path) -> None:
    store = RankingStore(tmp_path / "company_rankings.json")
    service = FinancialSyncService(_settings(), store=store, enable_scheduler=False, provider=list)
    result = service.sync_market_financials()
    assert result["updated"] == 0
    assert store.snapshot() == []


def test_ranking_endpoint_serves_synced_store(tmp_path) -> None:
    store = RankingStore(tmp_path / "company_rankings.json")
    service = FinancialSyncService(
        _settings(),
        store=store,
        enable_scheduler=False,
        provider=lambda: [
            {
                "symbol": "2222",
                "name": "أرامكو السعودية",
                "profit_growth": 1.2,
                "dividend_yield": 7.0,
                "roe": 26.0,
                "pe_ratio": 15.0,
                "net_income": 410000,
            }
        ],
    )
    service.sync_market_financials()
    app = FastAPI()
    app.state.ranking_store = store
    app.state.market_financial_sync = service
    app.include_router(market_router)
    response = TestClient(app).get("/api/v1/market/ranking-matrix")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_companies"] == 1
    assert payload["data"][0]["symbol"] == "2222"
    assert payload["data"][0]["dividend_yield"] == 7.0
    assert payload["synced_at"]


def test_live_rankings_reads_persisted_store(tmp_path) -> None:
    store = RankingStore(tmp_path / "company_rankings.json")
    service = FinancialSyncService(
        _settings(),
        store=store,
        enable_scheduler=False,
        provider=lambda: [
            {
                "symbol": "1120",
                "name": "الراجحي",
                "profit_growth": 14.1,
                "dividend_yield": 3.4,
                "roe": 19.0,
                "pe_ratio": 15.8,
                "net_income": 16500,
            }
        ],
    )
    service.sync_market_financials()
    app = FastAPI()
    app.state.ranking_store = store
    app.state.sync_service = service
    app.state.market_financial_sync = service
    app.include_router(market_router)
    response = TestClient(app).get("/api/v1/market/live-rankings")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["message"]
    assert payload["total_companies"] == 1
    assert payload["data"][0]["symbol"] == "1120"
    assert payload["data"][0]["profit_growth"] == 14.1


def test_manual_sync_endpoint_recalculates_matrix(tmp_path) -> None:
    store = RankingStore(tmp_path / "company_rankings.json")
    service = FinancialSyncService(
        _settings(),
        store=store,
        enable_scheduler=False,
        provider=lambda: [
            {
                "symbol": "1120",
                "name": "الراجحي",
                "profit_growth": 14.1,
                "dividend_yield": 3.4,
                "roe": 19.0,
                "pe_ratio": 15.8,
                "net_income": 16500,
            },
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
                "symbol": "2222",
                "name": "أرامكو السعودية",
                "profit_growth": 1.2,
                "dividend_yield": 7.0,
                "roe": 26.0,
                "pe_ratio": 15.0,
                "net_income": 410000,
            },
            {
                "symbol": "1180",
                "name": "الأهلي",
                "profit_growth": 9.8,
                "dividend_yield": 3.5,
                "roe": 14.2,
                "pe_ratio": 12.1,
                "net_income": 14000,
            },
        ],
    )
    service.sync_market_financials()
    app = FastAPI()
    app.state.ranking_store = store
    app.state.market_financial_sync = service
    app.include_router(market_router)
    response = TestClient(app).post("/api/v1/market/ranking-matrix/sync")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["total_companies"] >= 4
    symbols = [row["symbol"] for row in payload["data"]]
    assert "1120" in symbols
    rajhi = next(row for row in payload["data"] if row["symbol"] == "1120")
    assert rajhi["profit_growth"] == 14.1


def test_first_sync_does_not_email_when_store_is_empty(tmp_path) -> None:
    email = MagicMock()
    service = FinancialSyncService(
        _settings(),
        store=RankingStore(tmp_path / "company_rankings.json"),
        enable_scheduler=False,
        email_service=email,
        provider=lambda: [
            {
                "symbol": "1120",
                "name": "الراجحي",
                "profit_growth": 14.1,
                "dividend_yield": 3.4,
                "roe": 19.0,
                "pe_ratio": 15.8,
                "net_income": 16500,
            }
        ],
    )
    result = service.sync_market_financials()
    assert result["updated"] >= 1
    assert result["alerts"] == 0
    email.send_alert.assert_not_called()


def test_structural_ranking_change_sends_email(tmp_path) -> None:
    store = RankingStore(tmp_path / "company_rankings.json")
    store.replace(
        [
            {
                "symbol": "1120",
                "name": "الراجحي",
                "category": "الشركات الخاسرة وعالية المخاطر 🔴",
                "profit_growth": -20,
                "net_income": -1,
            }
        ],
        "2026-01-01T00:00:00+00:00",
    )
    email = MagicMock()
    email.send_alert.return_value = True
    service = FinancialSyncService(
        _settings(),
        store=store,
        enable_scheduler=False,
        email_service=email,
        provider=lambda: [
            {
                "symbol": "1120",
                "name": "الراجحي",
                "profit_growth": 18.0,
                "dividend_yield": 5.0,
                "roe": 22.0,
                "roa": 12.0,
                "pe_ratio": 12.0,
                "net_income": 18000,
            }
        ],
    )
    result = service.sync_market_financials()
    assert result["alerts"] == 1
    email.send_alert.assert_called_once()
    args = email.send_alert.call_args.args
    assert args[0] == "الراجحي"
    assert args[1] == "1120"
    assert "خاسرة" in args[2]
    assert args[3] != args[2]
