from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.schemas import SmartMoneyScanResponse
from app.routers.smart_money import router as smart_money_router
from app.services.smart_money import (
    BADGE_PORTFOLIO,
    KIND_ACCUMULATION,
    KIND_DISTRIBUTION,
    SIGNAL_ACCUMULATION,
    classify_smart_money,
    scan_smart_money,
    score_institutional_flow,
)
from app.services.signals import is_valid_long_plan


def _accum_snapshot(**overrides):
    row = {
        "symbol": "1120",
        "name": "مصرف الراجحي",
        "sector": "البنوك",
        "last_price": 90.0,
        "atr": 1.1,
        "session_low": 89.4,
        "support": 89.6,
        "block_trades": 5,
        "last_block_value": 2_400_000,
        "institutional_inflow": 8_000_000,
        "institutional_outflow": 400_000,
        "retail_inflow": 900_000,
        "retail_outflow": 1_200_000,
        "institutional_mfi": 95,
        "retail_mfi": 43,
        "clustered": 5,
        "clustered_buys": 5,
        "clustered_sells": 0,
        "cluster_run": 4,
        "near_bid_wall": True,
        "bid_wall": {"price": 89.6, "quantity": 80_000},
        "ask_wall": {"price": 90.2, "quantity": 8_000},
    }
    row.update(overrides)
    return row


def _dist_snapshot(**overrides):
    row = {
        "symbol": "2010",
        "name": "سابك",
        "last_price": 64.0,
        "block_trades": 4,
        "last_block_value": 900_000,
        "institutional_inflow": 200_000,
        "institutional_outflow": 5_500_000,
        "retail_inflow": 800_000,
        "retail_outflow": 700_000,
        "institutional_mfi": 8,
        "retail_mfi": 53,
        "clustered": 4,
        "clustered_buys": 0,
        "clustered_sells": 4,
        "cluster_run": 3,
        "near_bid_wall": False,
        "bid_wall": {"price": 63.8, "quantity": 6_000},
        "ask_wall": {"price": 64.2, "quantity": 40_000},
    }
    row.update(overrides)
    return row


def test_flow_score_favors_institutional_blocks_near_bid_wall() -> None:
    metrics = score_institutional_flow(_accum_snapshot())
    assert metrics["score"] >= 70
    assert metrics["inst_share"] > metrics["retail_share"]
    assert metrics["inst_mfi"] >= 90


def test_retail_tape_has_no_smart_money_row() -> None:
    row = classify_smart_money(
        {
            "symbol": "1120",
            "last_price": 90.0,
            "block_trades": 0,
            "institutional_inflow": 0,
            "institutional_outflow": 0,
            "retail_inflow": 2_000_000,
            "retail_outflow": 1_800_000,
            "retail_mfi": 52,
            "clustered": 0,
        }
    )
    assert row is None


def test_accumulation_row_carries_verified_long_plan() -> None:
    row = classify_smart_money(_accum_snapshot())
    assert row is not None
    assert row["signal_kind"] == KIND_ACCUMULATION
    assert row["signal"] == SIGNAL_ACCUMULATION
    assert row["badge"] == BADGE_PORTFOLIO
    assert row["institutional_flow_score"] >= 70
    assert row["plan_ok"] is True
    assert is_valid_long_plan(row["entry"], row["target"], row["stop"])
    assert row["target"] > row["entry"] > row["stop"] > 0


def test_distribution_row_does_not_offer_a_long_plan() -> None:
    row = classify_smart_money(_dist_snapshot())
    assert row is not None
    assert row["signal_kind"] == KIND_DISTRIBUTION
    assert row["plan_ok"] is False
    assert row["target"] is None
    assert row["stop"] is None


def test_scan_ranks_fund_accumulation_ahead_of_distribution() -> None:
    payload = scan_smart_money(
        snapshots=[_dist_snapshot(), _accum_snapshot(), {"symbol": "9999"}],
        moment=None,
    )
    assert payload["accumulation_count"] == 1
    assert payload["distribution_count"] == 1
    assert payload["data"][0]["symbol"] == "1120"
    assert payload["data"][0]["signal_kind"] == KIND_ACCUMULATION


def test_smart_money_scan_endpoint() -> None:
    class _Feed:
        def smart_money_snapshots(self):
            return [_accum_snapshot()]

    app = FastAPI()
    app.include_router(smart_money_router)
    app.state.tickchart = _Feed()
    client = TestClient(app)
    response = client.get("/api/v1/smart-money/scan")
    assert response.status_code == 200
    body = SmartMoneyScanResponse.model_validate(response.json())
    assert body.count == 1
    assert body.accumulation_count == 1
    assert body.data[0].badge == BADGE_PORTFOLIO
    assert body.data[0].target is not None
    assert body.data[0].stop is not None
    assert body.data[0].target > body.data[0].entry > body.data[0].stop
