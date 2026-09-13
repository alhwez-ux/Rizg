from decimal import Decimal

from app.models.trade import TradeSide
from app.services.tickchart_tape import BookLevel, SymbolTape


def test_silent_accumulation_from_quiet_prints_and_bid_wall() -> None:
    tape = SymbolTape(symbol="2222")
    for index in range(16):
        tape.observe_print(Decimal("25.00") + Decimal(index) * Decimal("0.01"), Decimal("800"), side=TradeSide.BUY, block_floor=Decimal("1"))
    for _ in range(8):
        tape.observe_print(Decimal("25.20"), Decimal("20"), side=TradeSide.BUY, block_floor=Decimal("1"))
    tape.observe_book(
        [
            BookLevel(Decimal("25.18"), Decimal("12000")),
            BookLevel(Decimal("25.16"), Decimal("400")),
            BookLevel(Decimal("25.14"), Decimal("350")),
        ],
        [
            BookLevel(Decimal("25.22"), Decimal("300")),
            BookLevel(Decimal("25.24"), Decimal("280")),
            BookLevel(Decimal("25.26"), Decimal("260")),
        ],
    )
    trap = tape.detect_trap()
    assert trap is not None
    assert trap["kind"] == "silent_accumulation"
    assert tape.institutional_mfi() is not None
    assert tape.institutional_mfi() >= Decimal("55")


def test_bull_trap_when_volume_doubles_into_ask_wall() -> None:
    tape = SymbolTape(symbol="1120")
    for _ in range(20):
        tape.observe_print(Decimal("64.00"), Decimal("100"), side=TradeSide.BUY, block_floor=Decimal("1"))
    for _ in range(5):
        tape.observe_print(Decimal("64.40"), Decimal("800"), side=TradeSide.BUY, block_floor=Decimal("1"))
    tape.observe_book(
        [
            BookLevel(Decimal("64.30"), Decimal("200")),
            BookLevel(Decimal("64.28"), Decimal("180")),
            BookLevel(Decimal("64.26"), Decimal("160")),
        ],
        [
            BookLevel(Decimal("64.42"), Decimal("9000")),
            BookLevel(Decimal("64.44"), Decimal("400")),
            BookLevel(Decimal("64.46"), Decimal("350")),
        ],
    )
    trap = tape.detect_trap()
    assert trap is not None
    assert trap["kind"] == "bull_trap"
