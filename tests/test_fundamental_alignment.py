from decimal import Decimal

from app.services.fundamental_alignment import judge, load_paper
from app.services.signals import SignalEngine, SignalInputs
from app.services.smart_money import KIND_ACCUMULATION, KIND_DISTRIBUTION, classify_smart_money
from tests.test_smart_money import _accum_snapshot


def _entry(**overrides: object) -> SignalInputs:
    payload: dict[str, object] = {
        "inflow": Decimal("80000"),
        "outflow": Decimal("20000"),
        "buy_volume": Decimal("9000"),
        "sell_volume": Decimal("3000"),
        "price": Decimal("25"),
        "vwap_15m": Decimal("24.4"),
        "block_trades": 2,
        "block_volume": Decimal("180000"),
        "block_side": "buy",
    }
    payload.update(overrides)
    return SignalInputs(**payload)  # type: ignore[arg-type]


def test_stored_paper_reads_pe_debt_and_income() -> None:
    rajhi = load_paper("1120")
    sabic = load_paper("2010")
    assert rajhi.pe_ratio == 15.56
    assert rajhi.debt_ratio == 0.04
    assert rajhi.net_income == 24980
    assert judge(rajhi).healthy is True
    assert sabic.pe_ratio is None
    assert sabic.net_income == -21320
    assert judge(sabic).weak is True
    assert judge(sabic).healthy is False


def test_healthy_paper_keeps_entry() -> None:
    decision = SignalEngine().evaluate(_entry(symbol="1120"))
    assert decision.entry is True
    assert decision.exit is False
    assert any("الورقة المالية سليمة" in reason for reason in decision.reasons)


def test_loss_making_pump_is_exit_not_entry() -> None:
    decision = SignalEngine().evaluate(_entry(symbol="2010", change_percent=Decimal("6.2")))
    assert decision.entry is False
    assert decision.exit is True
    assert any("لا تتبع الورقة" in reason for reason in decision.reasons)


def test_loss_making_without_pump_cannot_enter() -> None:
    decision = SignalEngine().evaluate(_entry(symbol="2010", change_percent=Decimal("0.4")))
    assert decision.entry is False
    assert decision.exit is False
    assert any("لا دخول قبل سلامة الورقة" in reason for reason in decision.reasons)


def test_incomplete_paper_blocks_entry() -> None:
    decision = SignalEngine().evaluate(_entry(symbol="1320"))
    assert decision.entry is False
    assert decision.exit is False


def test_stretched_multiple_pump_is_exit() -> None:
    decision = SignalEngine().evaluate(_entry(symbol="2082", change_percent=Decimal("5.4")))
    assert decision.entry is False
    assert decision.exit is True


def test_weak_accumulation_tape_becomes_distribution() -> None:
    row = classify_smart_money(_accum_snapshot(symbol="2010", name="سابك"))
    assert row is not None
    assert row["signal_kind"] == KIND_DISTRIBUTION
    assert row["plan_ok"] is False
    assert "لا تتبع الورقة" in row["reason"]


def test_healthy_accumulation_stays_accumulation() -> None:
    row = classify_smart_money(_accum_snapshot())
    assert row is not None
    assert row["signal_kind"] == KIND_ACCUMULATION
    assert row["plan_ok"] is True
    assert "الورقة المالية سليمة" in row["reason"]
