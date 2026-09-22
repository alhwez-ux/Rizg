from __future__ import annotations

from decimal import Decimal

from app.services.signals import SignalEngine, SignalInputs


class _Clock:
    def __init__(self) -> None:
        self.t = 1_000.0

    def __call__(self) -> float:
        return self.t

    def step(self, seconds: float) -> None:
        self.t += seconds


def _buy(**overrides: object) -> SignalInputs:
    payload: dict[str, object] = {
        "inflow": Decimal("80000"),
        "outflow": Decimal("20000"),
        "buy_volume": Decimal("9000"),
        "sell_volume": Decimal("3000"),
        "symbol": "1120",
    }
    payload.update(overrides)
    return SignalInputs(**payload)  # type: ignore[arg-type]


def _sell(**overrides: object) -> SignalInputs:
    payload: dict[str, object] = {
        "inflow": Decimal("18000"),
        "outflow": Decimal("82000"),
        "buy_volume": Decimal("2000"),
        "sell_volume": Decimal("8000"),
        "symbol": "1120",
    }
    payload.update(overrides)
    return SignalInputs(**payload)  # type: ignore[arg-type]


def _engine(clock: _Clock) -> SignalEngine:
    return SignalEngine(
        net_flow_threshold=Decimal("15000"),
        aggressive_ratio=Decimal("0.51"),
        confirm_hits=3,
        exit_confirm_hits=3,
        sample_seconds=45,
        entry_cooldown_seconds=180,
        exit_cooldown_seconds=120,
        clock=clock,
    )


def test_entry_needs_three_spaced_confirmations() -> None:
    clock = _Clock()
    engine = _engine(clock)
    first = engine.evaluate(_buy())
    assert first.entry is False
    assert any("بانتظار تأكيد الدخول (1/3)" in reason for reason in first.reasons)

    clock.step(10)
    still = engine.evaluate(_buy())
    assert still.entry is False

    clock.step(45)
    second = engine.evaluate(_buy())
    assert second.entry is False
    clock.step(45)
    confirmed = engine.evaluate(_buy())
    assert confirmed.entry is True
    assert confirmed.exit is False
    assert confirmed.reasons[0] == "إشارة دخول 🚀"


def test_entry_cooldown_blocks_repeat_signal() -> None:
    clock = _Clock()
    engine = SignalEngine(
        net_flow_threshold=Decimal("15000"),
        aggressive_ratio=Decimal("0.51"),
        confirm_hits=3,
        exit_confirm_hits=3,
        sample_seconds=20,
        entry_cooldown_seconds=180,
        exit_cooldown_seconds=0,
        clock=clock,
    )
    decision = None
    for _ in range(3):
        decision = engine.evaluate(_buy())
        clock.step(20)
    assert decision is not None and decision.entry is True

    for _ in range(3):
        decision = engine.evaluate(_sell())
        clock.step(20)
    assert decision.exit is True

    for _ in range(3):
        rebound = engine.evaluate(_buy())
        clock.step(20)
    assert rebound.entry is False
    assert any("تهدئة بعد إشارة دخول" in reason for reason in rebound.reasons)

    clock.step(180)
    for _ in range(3):
        rebound = engine.evaluate(_buy())
        clock.step(20)
    assert rebound.entry is True


def test_exit_needs_confirmed_reversal_not_flat_tape() -> None:
    clock = _Clock()
    engine = _engine(clock)
    for _ in range(3):
        engine.evaluate(_buy())
        clock.step(45)
    assert engine.evaluate(_buy()).entry is True

    clock.step(45)
    noise = engine.evaluate(
        SignalInputs(
            inflow=Decimal("5000"),
            outflow=Decimal("5000"),
            buy_volume=Decimal("400"),
            sell_volume=Decimal("400"),
            symbol="1120",
        )
    )
    assert noise.exit is False
    assert noise.entry is True

    clock.step(45)
    first_fade = engine.evaluate(_sell())
    assert first_fade.exit is False
    clock.step(45)
    engine.evaluate(_sell())
    clock.step(45)
    confirmed = engine.evaluate(_sell())
    assert confirmed.entry is False
    assert confirmed.exit is True
    assert confirmed.reasons[0] == "إشارة خروج / تصريف ⚠️"
