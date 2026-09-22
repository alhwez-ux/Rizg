from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.schemas import RecoveryPlanResponse
from app.routers.recovery import router as recovery_router
from app.services.recovery import build_recovery_plan, snapshot_position


def test_loss_amount_and_percent_versus_live_price() -> None:
    position = snapshot_position(
        symbol="1120",
        name="مصرف الراجحي",
        quantity=200,
        avg_price=100.0,
        last_price=88.0,
    )
    assert position["in_loss"] is True
    assert position["loss_amount"] == 2400.0
    assert position["cost_basis"] == 20_000.0
    assert position["market_value"] == 17_600.0
    assert position["pnl_pct"] == -12.0


def test_profit_needs_no_recovery_rotation() -> None:
    plan = build_recovery_plan(
        symbol="1120",
        quantity=50,
        avg_price=80.0,
        last_price=92.0,
        candidates=[
            {
                "symbol": "2222",
                "last_price": 27.0,
                "hidden_accumulation": True,
                "institutional_mfi": 70,
                "net_flow": 90_000,
            }
        ],
    )
    assert plan["stance"] == "hold"
    assert plan["position"]["in_loss"] is False
    assert plan["rotation_budget"] == 0
    assert plan["data"] == []


def test_dumping_loser_rotates_into_hidden_and_breakout_names() -> None:
    plan = build_recovery_plan(
        symbol="1120",
        quantity=150,
        avg_price=100.0,
        last_price=86.0,
        owned={"institutional_mfi": 38, "net_flow": -80_000, "signal_kind": "distribution"},
        candidates=[
            {
                "symbol": "2222",
                "name": "أرامكو السعودية",
                "last_price": 27.2,
                "hidden_accumulation": True,
                "institutional_mfi": 72,
                "net_flow": 120_000,
                "volume_ratio": 1.8,
                "atr": 0.32,
            },
            {
                "symbol": "2010",
                "name": "سابك",
                "last_price": 64.5,
                "explosive": True,
                "resistance_break": True,
                "under_watch": True,
                "institutional_mfi": 61,
                "net_flow": 55_000,
                "volume_ratio": 1.7,
                "atr": 0.7,
            },
            {
                "symbol": "1120",
                "last_price": 86.0,
                "hidden_accumulation": True,
                "institutional_mfi": 80,
                "net_flow": 10_000,
            },
        ],
    )
    assert plan["stance"] == "rotate"
    assert plan["averaging"] is None
    assert plan["rotation_budget"] > 0
    symbols = [row["symbol"] for row in plan["data"]]
    assert "1120" not in symbols
    assert "2222" in symbols
    assert plan["count"] >= 1
    for row in plan["data"]:
        assert row["target"] > row["entry"] > row["stop"] > 0
        assert row["shares"] >= 1
        assert row["allocation"] > 0
        assert row["expected_gain"] > 0


def test_constructive_loser_gets_same_stock_averaging() -> None:
    plan = build_recovery_plan(
        symbol="2222",
        quantity=100,
        avg_price=28.0,
        last_price=26.4,
        owned={
            "hidden_accumulation": True,
            "institutional_mfi": 64,
            "net_flow": 40_000,
            "atr": 0.28,
            "session_low": 26.2,
        },
        candidates=[],
    )
    assert plan["averaging"] is not None
    assert plan["averaging"]["new_avg_price"] < 28.0
    assert plan["averaging"]["extra_quantity"] >= 1
    assert plan["averaging"]["target"] > plan["averaging"]["entry"] > plan["averaging"]["stop"]


def test_recovery_plan_endpoint() -> None:
    class _Feed:
        def radar_report(self, symbol: str):
            if symbol == "1120":
                return {
                    "symbol": "1120",
                    "name": "مصرف الراجحي",
                    "last_price": 88.0,
                    "institutional_mfi": 40,
                    "net_flow": -20_000,
                }
            return {"symbol": symbol, "last_price": 27.4, "hidden_accumulation": True, "institutional_mfi": 68, "net_flow": 70_000}

        def market_rows(self):
            return [
                {
                    "symbol": "2222",
                    "name": "أرامكو السعودية",
                    "last_price": 27.4,
                    "hidden_accumulation": True,
                    "institutional_mfi": 68,
                    "net_flow": 70_000,
                    "volume_ratio": 1.9,
                }
            ]

        def under_watch_rows(self):
            return []

    app = FastAPI()
    app.include_router(recovery_router)
    app.state.tickchart = _Feed()
    client = TestClient(app)
    response = client.post(
        "/api/v1/recovery/plan",
        json={"symbol": "1120", "quantity": 100, "avg_price": 96.5},
    )
    assert response.status_code == 200
    body = RecoveryPlanResponse.model_validate(response.json())
    assert body.position.in_loss is True
    assert body.position.loss_amount > 0
    assert body.position.pnl_pct < 0
    assert body.data
    assert body.data[0].target > body.data[0].entry > body.data[0].stop
