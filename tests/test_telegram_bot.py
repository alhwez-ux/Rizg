from datetime import datetime, timezone
from decimal import Decimal
import asyncio

from app.core.config import Settings
from app.models.alert import AlertKind, LiquidityAlert
from app.models.trade import SessionFlow, TickType, TradeResult, TradeSide
from app.services.telegram_bot import TelegramBot


def _bot(**overrides: object) -> TelegramBot:
    payload: dict[str, object] = {
        "telegram_bot_token": "123:abc",
        "telegram_chat_id": "123456789",
        "telegram_report_interval_minutes": 30,
        "telegram_report_symbols": ["4030"],
    }
    payload.update(overrides)
    return TelegramBot(Settings(**payload))


def _trade(
    *,
    side: TradeSide,
    money_flow: str,
    volume: str = "100",
    symbol: str = "4030",
) -> TradeResult:
    flow = Decimal(money_flow)
    qty = Decimal(volume)
    signed = flow if side is TradeSide.BUY else -abs(flow)
    return TradeResult(
        symbol=symbol,
        side=side,
        tick=TickType.UPTICK if side is TradeSide.BUY else TickType.DOWNTICK,
        price=Decimal("24.85"),
        volume=qty,
        money_flow=signed,
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        session=SessionFlow(
            symbol=symbol,
            inflow=flow if side is TradeSide.BUY else Decimal("0"),
            outflow=abs(flow) if side is TradeSide.SELL else Decimal("0"),
            net_flow=signed,
            last_price=Decimal("24.85"),
            last_different_price=None,
            last_side=side,
            trade_count=1,
            classified_count=1,
            buy_volume=qty if side is TradeSide.BUY else Decimal("0"),
            sell_volume=qty if side is TradeSide.SELL else Decimal("0"),
        ),
    )


def _alert(*, kind: AlertKind, net: str = "1250000") -> LiquidityAlert:
    return LiquidityAlert(
        id="alert-1",
        symbol="4030",
        kind=kind,
        title="test",
        message="test",
        window_seconds=60,
        window_inflow=Decimal("1250000"),
        window_outflow=Decimal("100000"),
        window_volume=Decimal("50000"),
        window_net_flow=Decimal(net),
        session_inflow=Decimal("3200000"),
        session_outflow=Decimal("1900000"),
        last_price=Decimal("24.85"),
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_placeholder_chat_id_disables_bot() -> None:
    bot = _bot(telegram_chat_id="رقم_الايد_ الخاص_بك")
    assert bot.enabled is False


def test_numeric_chat_id_enables_bot() -> None:
    assert _bot().enabled is True


def test_default_interval_is_thirty_minutes() -> None:
    settings = Settings(
        _env_file=None,
        telegram_bot_token="123:abc",
        telegram_chat_id="123456789",
    )
    bot = TelegramBot(settings)
    assert settings.telegram_report_interval_minutes == 30
    assert bot.interval_minutes == 30


def test_arabic_interval_report_accumulation() -> None:
    bot = _bot()
    bot.record_trade(_trade(side=TradeSide.BUY, money_flow="3200000", volume="200"))
    bot.record_trade(_trade(side=TradeSide.SELL, money_flow="1900000", volume="80"))
    pending = bot.pending_reports()
    assert len(pending) == 1
    text = bot.format_interval_report(pending[0])
    assert "فترة التقرير: ملخص آخر 30 دقيقة" in text
    assert "اسم السهم: <code>4030</code>" in text
    assert "كمية الشراء: 200" in text
    assert "كمية البيع: 80" in text
    assert "إجمالي سيولة الشراء: +3,200,000.00 ر.س" in text
    assert "إجمالي سيولة البيع: +1,900,000.00 ر.س" in text
    assert "صافي التدفق النهائي: <b>+1,300,000.00 ر.س</b>" in text
    assert "حالة السهم: 🚀 تراكم" in text


def test_arabic_interval_report_distribution() -> None:
    bot = _bot()
    bot.record_trade(_trade(side=TradeSide.SELL, money_flow="1500000"))
    text = bot.format_interval_report(bot.pending_reports()[0])
    assert "⚠️ تصريف" in text
    assert "صافي التدفق النهائي: <b>-1,500,000.00 ر.س</b>" in text


def test_other_symbols_are_ignored_by_default() -> None:
    bot = _bot()
    bot.record_trade(_trade(side=TradeSide.BUY, money_flow="1000", symbol="AAPL"))
    assert bot.pending_reports() == []


def test_flush_sends_one_summary_then_cooldown_blocks_another() -> None:
    bot = _bot()
    sent: list[str] = []

    async def fake_send(text: str) -> bool:
        sent.append(text)
        return True

    bot.send_message = fake_send  # type: ignore[method-assign]
    bot.record_trade(_trade(side=TradeSide.BUY, money_flow="5000"))

    async def run() -> None:
        assert await bot.flush_reports(force=True) == 1
        bot.record_trade(_trade(side=TradeSide.BUY, money_flow="1000"))
        assert await bot.flush_reports() == 0
        assert len(bot.pending_reports()) == 1
        assert await bot.flush_reports(force=True) == 1

    asyncio.run(run())
    assert len(sent) == 2
    assert "ملخص آخر 30 دقيقة" in sent[0]


def test_send_skipped_when_chat_id_missing() -> None:
    bot = _bot(telegram_chat_id="")
    assert asyncio.run(bot.send_message("hello")) is False


def test_instant_alert_formatter_still_available() -> None:
    bot = _bot()
    text = bot.format_liquidity_alert(_alert(kind=AlertKind.NET_FLOW_SPIKE))
    assert "🚀 دخول سيولة قوي (تراكم)" in text
