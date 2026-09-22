from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.schemas import PreOpenScanResponse
from app.routers.preopen import router as preopen_router
from app.services.preopen import (
    SIGNAL_ACCUMULATION,
    SIGNAL_DISTRIBUTION,
    classify_preopen,
    expected_opening_price,
    scan_preopen,
)
from app.services.tasi_clock import TASI_TZ, is_preopen_window, session_phase


def test_preopen_window_matches_tasi_auction() -> None:
    inside = datetime(2026, 9, 22, 9, 45, tzinfo=TASI_TZ)
    before = datetime(2026, 9, 22, 9, 29, tzinfo=TASI_TZ)
    open_bell = datetime(2026, 9, 22, 10, 0, tzinfo=TASI_TZ)
    friday = datetime(2026, 9, 18, 9, 45, tzinfo=TASI_TZ)
    assert session_phase(inside) == "preopen"
    assert is_preopen_window(inside) is True
    assert is_preopen_window(before) is False
    assert is_preopen_window(open_bell) is False
    assert is_preopen_window(friday) is False


def test_expected_open_pulls_toward_ask_when_buy_book_dominates() -> None:
    price = expected_opening_price(bid=10.0, ask=10.4, last=None, buy_volume=8000, sell_volume=2000)
    assert price is not None
    assert 10.3 <= price <= 10.4


def test_expected_open_uses_indicative_last_inside_spread() -> None:
    price = expected_opening_price(bid=24.8, ask=25.0, last=24.9, buy_volume=1000, sell_volume=1000)
    assert price == 24.9


def test_early_accumulation_from_buy_book_and_gap_up() -> None:
    row = classify_preopen(
        {
            "symbol": "2222",
            "name": "أرامكو السعودية",
            "bid": 27.0,
            "ask": 27.2,
            "bid_size": 120_000,
            "ask_size": 30_000,
            "prev_close": 26.8,
            "block_trades": 4,
            "institutional_inflow": 2_500_000,
            "institutional_outflow": 200_000,
            "bid_wall": {"price": 27.0, "quantity": 80_000},
        }
    )
    assert row is not None
    assert row["signal"] == SIGNAL_ACCUMULATION
    assert row["signal_kind"] == "accumulation"
    assert row["liquidity_state"] == "تجميع"
    assert row["buy_volume"] > row["sell_volume"]
    assert row["expected_open"] is not None
    assert row["open_variation_pct"] is not None
    assert row["open_variation_pct"] > 0
    assert row["large_block_side"] == "buy"


def test_early_distribution_from_sell_book_and_gap_down() -> None:
    row = classify_preopen(
        {
            "symbol": "1120",
            "bid": 90.0,
            "ask": 90.4,
            "bid_size": 8_000,
            "ask_size": 40_000,
            "prev_close": 91.2,
            "block_trades": 3,
            "institutional_inflow": 50_000,
            "institutional_outflow": 900_000,
            "ask_wall": {"price": 90.4, "quantity": 35_000},
        }
    )
    assert row is not None
    assert row["signal"] == SIGNAL_DISTRIBUTION
    assert row["signal_kind"] == "distribution"
    assert row["liquidity_state"] == "تصريف"
    assert row["sell_volume"] > row["buy_volume"]
    assert row["large_block_side"] == "sell"


def test_order_book_outranks_leftover_session_prints() -> None:
    row = classify_preopen(
        {
            "symbol": "4030",
            "bid": 24.8,
            "ask": 25.0,
            "bid_size": 4_000,
            "ask_size": 40_000,
            "buy_volume": 90_000,
            "sell_volume": 100,
            "prev_close": 25.2,
        }
    )
    assert row is not None
    assert row["buy_volume"] == 4000
    assert row["sell_volume"] == 40000
    assert row["signal"] == SIGNAL_DISTRIBUTION


def test_scan_ranks_by_conviction_and_marks_window() -> None:
    moment = datetime(2026, 9, 22, 9, 40, tzinfo=TASI_TZ)
    payload = scan_preopen(
        snapshots=[
            {
                "symbol": "7010",
                "bid": 40.0,
                "ask": 40.2,
                "bid_size": 5_000,
                "ask_size": 4_800,
                "prev_close": 40.1,
            },
            {
                "symbol": "2222",
                "bid": 27.0,
                "ask": 27.3,
                "bid_size": 200_000,
                "ask_size": 20_000,
                "prev_close": 26.5,
                "institutional_inflow": 4_000_000,
                "institutional_outflow": 10_000,
            },
            {
                "symbol": "1120",
                "bid": 35.0,
                "ask": 35.4,
                "bid_size": 10_000,
                "ask_size": 90_000,
                "prev_close": 36.0,
                "institutional_inflow": 0,
                "institutional_outflow": 1_200_000,
            },
        ],
        moment=moment,
    )
    assert payload["in_window"] is True
    assert payload["session_phase"] == "preopen"
    assert payload["accumulation_count"] >= 1
    assert payload["distribution_count"] >= 1
    assert payload["data"][0]["symbol"] in {"2222", "1120"}
    kinds = {row["signal_kind"] for row in payload["data"]}
    assert "accumulation" in kinds
    assert "distribution" in kinds


def test_preopen_endpoint_uses_feed_snapshots() -> None:
    class _Feed:
        def preopen_snapshots(self):
            return [
                {
                    "symbol": "4030",
                    "name": "البحري",
                    "bid": 24.80,
                    "ask": 25.00,
                    "bid_size": 50_000,
                    "ask_size": 8_000,
                    "prev_close": 24.50,
                    "block_trades": 2,
                    "institutional_inflow": 800_000,
                    "institutional_outflow": 40_000,
                }
            ]

    app = FastAPI()
    app.state.tickchart = _Feed()
    app.include_router(preopen_router)
    with TestClient(app) as client:
        response = client.get("/api/v1/preopen/scan")
    assert response.status_code == 200
    payload = response.json()
    parsed = PreOpenScanResponse.model_validate(payload)
    assert parsed.success is True
    assert parsed.count == 1
    assert parsed.data[0].symbol == "4030"
    assert parsed.data[0].signal == SIGNAL_ACCUMULATION
    assert parsed.window_start == "09:30"
    assert parsed.window_end == "10:00"
