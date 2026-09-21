from decimal import Decimal

from app.services.institutional_strategy import (
    hidden_accumulation_from_candles,
    volume_confirms_entry,
)
from app.services.signals import (
    SignalEngine,
    SignalInputs,
    is_valid_long_plan,
    keep_long_recommendations,
    long_trade_levels,
)


def test_long_trade_levels_never_invert_buy_geometry() -> None:
    for entry, atr, swing in (
        (Decimal("25.70"), Decimal("0.40"), Decimal("25.10")),
        (10.0, 0.05, 9.4),
        ("96.40", "1.20", "94.80"),
        (0.51, 0.02, 0.48),
    ):
        target, stop = long_trade_levels(entry, atr=atr, swing_low=swing)
        assert is_valid_long_plan(entry, target, stop)
        assert target > Decimal(str(entry)) > stop > 0


def test_long_trade_levels_rejects_inverted_operators() -> None:
    target, stop = long_trade_levels(25.70, atr=0.31, target_mult=-1.4, stop_mult=-1.0)
    assert target > Decimal("25.70") > stop


def test_keep_long_recommendations_drops_inverted_buy_plan() -> None:
    kept = keep_long_recommendations(
        [
            {"symbol": "2222", "entry_price": "25.70", "target_price": "25.45", "stop_loss": "26.01"},
            {"symbol": "1120", "entry_price": "96.40", "target_price": "98.10", "stop_loss": "95.20"},
        ]
    )
    assert [row["symbol"] for row in kept] == ["1120"]


def test_volume_profile_blocks_fake_breakout() -> None:
    window = [1_000_000] * 10
    assert volume_confirms_entry(1_800_000, window, buy_volume=1200, sell_volume=400) is True
    assert volume_confirms_entry(1_100_000, window, buy_volume=1200, sell_volume=400) is False
    assert volume_confirms_entry(2_000_000, window, buy_volume=300, sell_volume=900) is False


def test_hidden_accumulation_near_support_before_break() -> None:
    lows = [10.0, 9.6, 9.55, 9.58, 9.62, 9.7, 9.8, 9.85, 9.9, 9.95, 9.72]
    volumes = [100, 250, 260, 80, 90, 95, 100, 110, 105, 108, 140]
    closes = [10.1, 9.7, 9.66, 9.7, 9.75, 9.82, 9.88, 9.9, 9.92, 9.74, 9.78]
    assert hidden_accumulation_from_candles(lows, volumes, closes=closes) is True
    chase = list(closes)
    chase[-1] = 10.5
    assert hidden_accumulation_from_candles(lows, volumes, closes=chase) is False


def test_ten_session_volume_profile_required_when_present() -> None:
    engine = SignalEngine()
    blocked = engine.evaluate(
        SignalInputs(
            net_flow=Decimal("900"),
            buy_volume=Decimal("70"),
            sell_volume=Decimal("30"),
            volume=Decimal("1000"),
            avg_volume=Decimal("2000"),
            symbol="2222",
        )
    )
    allowed = engine.evaluate(
        SignalInputs(
            net_flow=Decimal("900"),
            buy_volume=Decimal("70"),
            sell_volume=Decimal("30"),
            volume=Decimal("4000"),
            avg_volume=Decimal("2000"),
            symbol="2222",
        )
    )
    assert blocked.entry is False
    assert allowed.entry is True
    assert any("10 جلسات" in reason for reason in allowed.reasons)
