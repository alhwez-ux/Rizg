from datetime import datetime, timedelta, timezone
from decimal import Decimal
import asyncio
from unittest.mock import MagicMock

from app.core.config import Settings
from app.models.alert import AlertKind
from app.models.trade import SessionFlow, TickType, TradeResult, TradeSide
from app.services.alerts import AlertService


def _settings(**overrides: object) -> Settings:
    payload: dict[str, object] = {
        "alert_window_seconds": 60,
        "alert_inflow_threshold": Decimal("1000"),
        "alert_volume_threshold": Decimal("50"),
        "alert_net_flow_threshold": Decimal("800"),
        "alert_cooldown_seconds": 30,
        "alert_history_limit": 20,
        "telegram_bot_token": "",
        "telegram_chat_id": "",
    }
    payload.update(overrides)
    return Settings(**payload)


def _buy(*, timestamp: datetime, money_flow: str, volume: str, symbol: str = "4030") -> TradeResult:
    flow = Decimal(money_flow)
    qty = Decimal(volume)
    return TradeResult(
        symbol=symbol,
        side=TradeSide.BUY,
        tick=TickType.UPTICK,
        price=Decimal("10.00"),
        volume=qty,
        money_flow=flow,
        timestamp=timestamp,
        session=SessionFlow(
            symbol=symbol,
            inflow=flow,
            outflow=Decimal("0"),
            net_flow=flow,
            last_price=Decimal("10.00"),
            last_different_price=None,
            last_side=TradeSide.BUY,
            trade_count=1,
            classified_count=1,
            buy_volume=qty,
            sell_volume=Decimal("0"),
        ),
    )


def _sell(*, timestamp: datetime, money_flow: str, volume: str, symbol: str = "4030") -> TradeResult:
    flow = Decimal(money_flow)
    qty = Decimal(volume)
    return TradeResult(
        symbol=symbol,
        side=TradeSide.SELL,
        tick=TickType.DOWNTICK,
        price=Decimal("10.00"),
        volume=qty,
        money_flow=-abs(flow),
        timestamp=timestamp,
        session=SessionFlow(
            symbol=symbol,
            inflow=Decimal("0"),
            outflow=abs(flow),
            net_flow=-abs(flow),
            last_price=Decimal("10.00"),
            last_different_price=None,
            last_side=TradeSide.SELL,
            trade_count=1,
            classified_count=1,
            buy_volume=Decimal("0"),
            sell_volume=qty,
        ),
    )


def test_inflow_within_one_minute_triggers_alert() -> None:
    service = AlertService(
        _settings(
            alert_net_flow_threshold=Decimal("999999"),
            alert_volume_threshold=Decimal("999999"),
        )
    )
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    first = service._evaluate(_buy(timestamp=now, money_flow="400", volume="10"))
    second = service._evaluate(
        _buy(timestamp=now + timedelta(seconds=20), money_flow="700", volume="20")
    )

    assert first is None
    assert second is not None
    assert second.kind is AlertKind.INFLOW_SURGE
    assert second.symbol == "4030"
    assert second.window_inflow == Decimal("1100")


def test_volume_surge_within_window() -> None:
    service = AlertService(
        _settings(
            alert_inflow_threshold=Decimal("999999"),
            alert_net_flow_threshold=Decimal("999999"),
        )
    )
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    service._evaluate(_buy(timestamp=now, volume="20", money_flow="10"))
    alert = service._evaluate(
        _buy(timestamp=now + timedelta(seconds=10), volume="40", money_flow="10")
    )
    assert alert is not None
    assert alert.kind is AlertKind.VOLUME_SURGE
    assert alert.window_volume == Decimal("60")


def test_samples_older_than_one_minute_are_ignored() -> None:
    service = AlertService(_settings())
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    service._evaluate(
        _buy(timestamp=now - timedelta(seconds=90), money_flow="900", volume="40")
    )
    alert = service._evaluate(_buy(timestamp=now, money_flow="200", volume="5"))
    assert alert is None


def test_cooldown_suppresses_duplicate_alerts() -> None:
    service = AlertService(_settings(alert_cooldown_seconds=30))
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    first = service._evaluate(_buy(timestamp=now, money_flow="1200", volume="80"))
    second = service._evaluate(
        _buy(timestamp=now + timedelta(seconds=5), money_flow="1200", volume="80")
    )
    assert first is not None
    assert second is None
    assert service.recent("4030")[0].id == first.id


def test_outflow_within_one_minute_triggers_distribution_alert() -> None:
    service = AlertService(
        _settings(
            alert_inflow_threshold=Decimal("1000"),
            alert_net_flow_threshold=Decimal("999999"),
            alert_volume_threshold=Decimal("999999"),
        )
    )
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    first = service._evaluate(_sell(timestamp=now, money_flow="400", volume="10"))
    second = service._evaluate(
        _sell(timestamp=now + timedelta(seconds=20), money_flow="700", volume="20")
    )

    assert first is None
    assert second is not None
    assert second.kind is AlertKind.OUTFLOW_SURGE
    assert second.window_outflow == Decimal("1100")


def test_handle_trade_queues_telegram_without_instant_send() -> None:
    telegram = MagicMock()
    service = AlertService(_settings(), telegram=telegram)
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    asyncio.run(service.handle_trade(_buy(timestamp=now, money_flow="100", volume="1")))
    telegram.record_trade.assert_called_once()
    telegram.send_liquidity_alert.assert_not_called()
