from decimal import Decimal

from app.core.config import Settings
from app.core.exceptions import ProhibitedSymbolError
from app.services.screener import ScreenerService
from app.services.signals import SignalEngine, SignalInputs
from app.services.watchlist import WatchlistService


def test_entry_requires_net_inflow_and_aggressive_buying() -> None:
    engine = SignalEngine(net_flow_threshold=Decimal("15000"), aggressive_ratio=Decimal("0.58"))
    decision = engine.evaluate(
        SignalInputs(
            inflow=Decimal("80000"),
            outflow=Decimal("20000"),
            buy_volume=Decimal("9000"),
            sell_volume=Decimal("3000"),
        )
    )
    assert decision.entry is True
    assert decision.exit is False
    assert decision.flow_verified is True
    assert decision.reasons[0] == "إشارة دخول 🚀"


def test_price_rally_without_flow_does_not_fire_entry() -> None:
    engine = SignalEngine()
    decision = engine.evaluate(
        SignalInputs(
            change_percent=Decimal("4.8"),
            volume=Decimal("500000"),
            in_gainers=True,
            in_volume_leaders=True,
        )
    )
    assert decision.entry is False
    assert decision.exit is False
    assert decision.flow_verified is False


def test_value_ratio_used_when_aggressive_volume_is_missing() -> None:
    engine = SignalEngine(net_flow_threshold=Decimal("15000"), aggressive_ratio=Decimal("0.58"))
    decision = engine.evaluate(
        SignalInputs(inflow=Decimal("80000"), outflow=Decimal("20000"))
    )
    assert decision.entry is True
    assert decision.buy_ratio == Decimal("0.8000")


def test_sell_volume_blocks_entry_even_with_positive_net_value() -> None:
    engine = SignalEngine(net_flow_threshold=Decimal("15000"), aggressive_ratio=Decimal("0.58"))
    decision = engine.evaluate(
        SignalInputs(
            inflow=Decimal("80000"),
            outflow=Decimal("20000"),
            buy_volume=Decimal("2000"),
            sell_volume=Decimal("8000"),
        )
    )
    assert decision.entry is False
    assert decision.exit is False


def test_net_inflow_without_buy_pressure_does_not_fire() -> None:
    engine = SignalEngine(net_flow_threshold=Decimal("15000"), aggressive_ratio=Decimal("0.58"))
    decision = engine.evaluate(
        SignalInputs(
            inflow=Decimal("52000"),
            outflow=Decimal("48000"),
            buy_volume=Decimal("5100"),
            sell_volume=Decimal("4900"),
        )
    )
    assert decision.entry is False
    assert decision.exit is False


def test_agile_entry_on_modest_net_flow_and_buy_pressure() -> None:
    engine = SignalEngine()
    decision = engine.evaluate(
        SignalInputs(
            inflow=Decimal("8000"),
            outflow=Decimal("4000"),
            buy_volume=Decimal("520"),
            sell_volume=Decimal("480"),
        )
    )
    assert decision.entry is True
    assert decision.exit is False
    assert decision.reasons[0] == "إشارة دخول 🚀"


def test_agile_exit_when_net_flow_turns_flat_or_negative() -> None:
    engine = SignalEngine()
    flat = engine.evaluate(
        SignalInputs(
            inflow=Decimal("5000"),
            outflow=Decimal("5000"),
            buy_volume=Decimal("400"),
            sell_volume=Decimal("400"),
        )
    )
    assert flat.entry is False
    assert flat.exit is True

    fade = engine.evaluate(
        SignalInputs(
            inflow=Decimal("4800"),
            outflow=Decimal("5200"),
            buy_volume=Decimal("490"),
            sell_volume=Decimal("510"),
        )
    )
    assert fade.entry is False
    assert fade.exit is True
    assert fade.reasons[0] == "إشارة خروج / تصريف ⚠️"


def test_exit_requires_net_outflow_and_heavy_selling() -> None:
    engine = SignalEngine(net_flow_threshold=Decimal("15000"), aggressive_ratio=Decimal("0.58"))
    decision = engine.evaluate(
        SignalInputs(
            inflow=Decimal("18000"),
            outflow=Decimal("82000"),
            buy_volume=Decimal("2000"),
            sell_volume=Decimal("8000"),
        )
    )
    assert decision.entry is False
    assert decision.exit is True
    assert decision.reasons[0] == "إشارة خروج / تصريف ⚠️"


def test_untracked_entry_is_unexpected_radar_candidate() -> None:
    engine = SignalEngine()
    decision = engine.evaluate(
        SignalInputs(
            inflow=Decimal("90000"),
            outflow=Decimal("10000"),
            buy_volume=Decimal("12000"),
            sell_volume=Decimal("2000"),
            tracked=False,
        )
    )
    assert decision.entry is True
    assert decision.unexpected is True


def test_watchlist_and_radar_share_the_same_flow_rules(tmp_path) -> None:
    watchlist = WatchlistService(path=tmp_path / "watchlist.json", initial=["4030"])
    screener = ScreenerService(Settings(signal_net_flow_threshold=Decimal("15000")), watchlist)
    screener.observe_quote(
        {
            "symbol": "4030",
            "price": "24.50",
            "volume": "1000",
            "change_percent": "-0.4",
            "liquidity": {
                "inflow_value": "90000",
                "outflow_value": "12000",
                "net_value": "78000",
                "inflow_volume": "8000",
                "outflow_volume": "1500",
            },
        },
        tracked=True,
    )
    screener.observe_quote(
        {
            "symbol": "2222",
            "name": "أرامكو",
            "price": "27.10",
            "volume": "9000",
            "change_percent": "1.2",
            "liquidity": {
                "inflow_value": "10000",
                "outflow_value": "85000",
                "net_value": "-75000",
                "inflow_volume": "1100",
                "outflow_volume": "7400",
            },
        },
        tracked=False,
    )
    snapshot = screener.snapshot()
    watched = snapshot.watchlist[0]
    radar = snapshot.radar[0]
    assert watched.symbol == "4030"
    assert watched.entry_signal is True
    assert watched.exit_signal is False
    assert radar.symbol == "2222"
    assert radar.exit_signal is True
    assert radar.entry_signal is False
    assert radar.unexpected is True


def test_watchlist_add_and_remove_roundtrip(tmp_path) -> None:
    service = WatchlistService(path=tmp_path / "watchlist.json", initial=["4030"])
    assert service.add("2222") == ["4030", "2222"]
    assert service.remove("2222") == ["4030"]
    assert service.remove("4030") == ["4030"]


def test_prohibited_symbol_never_reaches_radar(tmp_path) -> None:
    watchlist = WatchlistService(path=tmp_path / "watchlist.json", initial=["4030"])
    screener = ScreenerService(Settings(signal_net_flow_threshold=Decimal("15000")), watchlist)
    payload = {
        "symbol": "1010",
        "name": "بنك الرياض",
        "price": "28.10",
        "volume": "9000",
        "change_percent": "1.2",
        "liquidity": {
            "inflow_value": "10000",
            "outflow_value": "85000",
            "net_value": "-75000",
            "inflow_volume": "1100",
            "outflow_volume": "7400",
        },
    }
    assert screener.observe_quote(payload, tracked=False) is None
    snapshot = screener.snapshot()
    assert all(row.symbol != "1010" for row in snapshot.radar)
    try:
        watchlist.add("1010")
    except ProhibitedSymbolError:
        return
    raise AssertionError("prohibited symbol was accepted")


def test_entry_suggests_bid_or_vwap_with_atr_target_and_stop() -> None:
    engine = SignalEngine(
        net_flow_threshold=Decimal("15000"),
        aggressive_ratio=Decimal("0.58"),
        atr_target_mult=Decimal("1.5"),
        atr_stop_mult=Decimal("1.0"),
    )
    decision = engine.evaluate(
        SignalInputs(
            inflow=Decimal("80000"),
            outflow=Decimal("20000"),
            buy_volume=Decimal("9000"),
            sell_volume=Decimal("3000"),
            price=Decimal("24.80"),
            vwap=Decimal("24.50"),
            atr=Decimal("0.40"),
            bid=Decimal("24.48"),
            ask=Decimal("24.82"),
            bid_size=Decimal("12000"),
            ask_size=Decimal("4000"),
        )
    )
    assert decision.entry is True
    assert decision.suggested_entry == Decimal("24.50")
    assert decision.target_price == Decimal("25.10")
    assert decision.stop_loss == Decimal("24.10")
    assert "إشارة دخول بسعر مقترح: 24.50" in decision.reasons


def test_exit_recommends_ask_or_vwap() -> None:
    engine = SignalEngine(net_flow_threshold=Decimal("15000"), aggressive_ratio=Decimal("0.58"))
    decision = engine.evaluate(
        SignalInputs(
            inflow=Decimal("18000"),
            outflow=Decimal("82000"),
            buy_volume=Decimal("2000"),
            sell_volume=Decimal("8000"),
            price=Decimal("24.10"),
            vwap=Decimal("24.50"),
            ask=Decimal("24.12"),
        )
    )
    assert decision.exit is True
    assert decision.suggested_exit == Decimal("24.50")
    assert decision.suggested_entry is None
