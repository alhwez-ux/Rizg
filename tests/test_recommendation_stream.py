from datetime import datetime, timezone
from decimal import Decimal

from app.models.trade import (
    LiquidityStreamMessage,
    SessionFlow,
    TickType,
    TradeResult,
    TradeSide,
    recommendation_label,
)
from app.services.liquidity_engine import LiquidityEngine


def _buy(net_flow: str) -> TradeResult:
    flow = Decimal(net_flow)
    return TradeResult(
        symbol="4030",
        side=TradeSide.BUY,
        tick=TickType.UPTICK,
        price=Decimal("10.00"),
        volume=Decimal("100"),
        money_flow=flow,
        timestamp=datetime.now(timezone.utc),
        session=SessionFlow(
            symbol="4030",
            inflow=flow,
            outflow=Decimal("0"),
            net_flow=flow,
            last_price=Decimal("10.00"),
            last_different_price=None,
            last_side=TradeSide.BUY,
            trade_count=1,
            classified_count=1,
            buy_volume=Decimal("100"),
            sell_volume=Decimal("0"),
        ),
    )


def test_recommendation_label_entry_and_exit() -> None:
    assert recommendation_label(entry=True) == "دخول"
    assert recommendation_label(exit_signal=True) == "خروج"
    assert recommendation_label() is None


def test_stream_message_includes_recommendation() -> None:
    message = LiquidityStreamMessage.from_trade(_buy("25000"), recommendation="دخول")
    payload = message.as_json()
    assert payload["recommendation"] == "دخول"
    assert payload["symbol"] == "4030"


def test_engine_emits_entry_recommendation() -> None:
    engine = LiquidityEngine()
    engine.process_trade("4030", Decimal("10"), Decimal("100"))
    result = engine.process_trade("4030", Decimal("11"), Decimal("2000"))
    assert engine.recommendation_flag("4030") == "دخول"
    assert engine.stream_message(result).as_json()["recommendation"] == "دخول"


def test_engine_emits_exit_recommendation() -> None:
    engine = LiquidityEngine()
    engine.process_trade("4030", Decimal("11"), Decimal("100"))
    result = engine.process_trade("4030", Decimal("10"), Decimal("2000"))
    assert engine.recommendation_flag("4030") == "خروج"
    assert engine.stream_message(result).as_json()["recommendation"] == "خروج"
