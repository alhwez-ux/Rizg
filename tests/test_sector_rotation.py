from fastapi import FastAPI
from fastapi.testclient import TestClient
import asyncio
import pytest

from app.routers.market import router as market_router
from app.services.sector_rotation import (
    DEMO_TASI_SECTOR_TAPE,
    SAMPLE_SECTOR_TAPE,
    STATUS_LEADER,
    STATUS_OUTFLOW,
    SectorRotationEngine,
)


@pytest.fixture(autouse=True)
def _fast_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def instant(_delay: float = 0) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", instant)


def test_empty_tape_returns_no_sectors() -> None:
    assert SectorRotationEngine([]).analyze_sectors() == []


def test_demo_tasi_tape_ranks_banks_and_energy() -> None:
    ranked = SectorRotationEngine(DEMO_TASI_SECTOR_TAPE).analyze_sectors()
    assert {row["sector"] for row in ranked} == {"البنوك", "الطاقة"}
    assert ranked[0]["rank"] == 1
    scores = [row["sector_momentum_score"] for row in ranked]
    assert scores == sorted(scores, reverse=True)


def test_sectors_rank_by_momentum_and_net_flow() -> None:
    ranked = SectorRotationEngine(SAMPLE_SECTOR_TAPE).analyze_sectors()
    names = [row["sector"] for row in ranked]
    assert names[0] in {"المصارف", "الطاقة", "المواد الأساسية"}
    assert ranked[0]["rank"] == 1
    scores = [row["sector_momentum_score"] for row in ranked]
    assert scores == sorted(scores, reverse=True)
    energy = next(row for row in ranked if row["sector"] == "الطاقة")
    materials = next(row for row in ranked if row["sector"] == "المواد الأساسية")
    assert energy["net_flow"] > materials["net_flow"] or energy["sector_momentum_score"] >= materials["sector_momentum_score"]
    assert any(row["status"] in {STATUS_LEADER, STATUS_OUTFLOW} or "تجميع" in row["status"] for row in ranked)


def test_ranked_payload_includes_ascending_and_descending() -> None:
    payload = SectorRotationEngine(SAMPLE_SECTOR_TAPE).ranked_payload()
    assert payload["success"] is True
    assert payload["total_sectors"] == len(payload["leaders"])
    assert payload["leaders"][0]["sector"] == payload["laggards"][-1]["sector"]
    assert payload["laggards"][0]["rank_asc"] == 1
    assert payload["sectors"] == payload["data"]


def test_rows_from_screener_maps_tape() -> None:
    from types import SimpleNamespace

    from app.services.sector_rotation import rows_from_screener

    screener = SimpleNamespace(
        all_rows=lambda: [
            SimpleNamespace(
                symbol="1120",
                name="الراجحي",
                change_percent=1.2,
                volume=1000,
                value=50_000,
                net_flow=12_000,
            )
        ]
    )
    rows = rows_from_screener(screener)
    assert rows[0]["symbol"] == "1120"
    assert rows[0]["value_traded"] == 50_000
    assert rows[0]["sector"]


def test_sector_rotation_endpoint_returns_leaders() -> None:
    import httpx

    from app.core.config import Settings
    from app.services.sahm_data_provider import SahmDataProvider

    def handler(request: httpx.Request) -> httpx.Response:
        path = str(request.url)
        if "/companies/" in path:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"symbol": "1120", "name": "الراجحي", "sector": "المصارف", "status": "active"},
                        {"symbol": "2010", "name": "سابك", "sector": "المواد الأساسية", "status": "active"},
                        {"symbol": "2222", "name": "أرامكو السعودية", "sector": "الطاقة", "status": "active"},
                    ],
                    "total": 3,
                    "limit": 500,
                    "offset": 0,
                },
            )
        if "/market/gainers/" in path:
            return httpx.Response(
                200,
                json={"gainers": [{"symbol": "1120", "name": "الراجحي", "change_percent": 1.8, "volume": 8200000, "value": 640000000}]},
            )
        if "/market/volume/" in path:
            return httpx.Response(
                200,
                json={"stocks": [{"symbol": "2222", "name": "أرامكو السعودية", "change_percent": 0.4, "volume": 12400000, "value": 1150000000}]},
            )
        if "/market/value/" in path:
            return httpx.Response(
                200,
                json={"stocks": [{"symbol": "2010", "name": "سابك", "change_percent": -1.4, "volume": 4800000, "value": 210000000}]},
            )
        if "/market/summary/" in path:
            return httpx.Response(200, json={"index": "TASI", "index_value": 12000})
        if "/quote/" in path:
            return httpx.Response(200, json={"symbol": "1180", "data": {"price": 38.0, "change_percent": 0.9, "volume": 6100000, "value": 410000000}})
        return httpx.Response(404, json={"error": "missing"})

    settings = Settings(_env_file=None, sahmk_api_key="test-key", sahmk_request_gap_seconds=0.05, sahmk_max_backoff_seconds=15, telegram_bot_token="", telegram_chat_id="")
    provider = SahmDataProvider(settings, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    app = FastAPI()
    app.state.sahm = provider
    app.include_router(market_router)
    response = TestClient(app).get("/api/v1/market/sector-rotation")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["source"] == "Sahm API"
    assert payload["total_sectors"] >= 3
    assert payload["data"][0]["rank"] == 1
    assert payload["sectors"][0]["sector"] == payload["data"][0]["sector"]
    assert "net_flow" in payload["data"][0]


def test_sector_companies_endpoint_lists_banks() -> None:
    from app.services.sector_rotation import companies_for_sector

    payload = companies_for_sector("البنوك")
    symbols = {row["symbol"] for row in payload["companies"]}
    assert payload["success"] is True
    assert payload["sector"] == "البنوك"
    assert {"1120", "1180", "1010"} <= symbols
    assert all("net_flow" in row and "flow_status" in row for row in payload["companies"])

    app = FastAPI()
    app.include_router(market_router)
    banks = TestClient(app).get("/api/v1/market/sector-companies/البنوك")
    assert banks.status_code == 200
    body = banks.json()
    assert body["success"] is True
    assert body["sector"] == "البنوك"
    assert body["total_companies"] >= 3
    assert {row["symbol"] for row in body["companies"]} >= {"1120", "1180", "1010"}

    energy = TestClient(app).get("/api/v1/market/sector-companies/الطاقة")
    assert energy.status_code == 200
    energy_symbols = {row["symbol"] for row in energy.json()["companies"]}
    assert {"2222", "2380"} <= energy_symbols

    unknown = companies_for_sector("قطاع غير موجود")
    assert unknown["success"] is True
    assert unknown["companies"] == []
