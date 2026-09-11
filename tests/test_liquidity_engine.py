"""QA suite for LiquidityEngine tick-rule classification and money-flow accounting."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal, ROUND_HALF_EVEN
from threading import Barrier, Event

import pytest

from app.core.exceptions import InvalidTradeError, SymbolNotFoundError
from app.models.trade import TickType, TradeSide
from app.services.liquidity_engine import MONEY_QUANTUM, LiquidityEngine

MONEY_PLACES = Decimal("0.00000001")


@pytest.fixture
def engine() -> LiquidityEngine:
    return LiquidityEngine()


def money(value: str | int | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(MONEY_PLACES, rounding=ROUND_HALF_EVEN)


def notional(price: str | int | Decimal, volume: str | int | Decimal) -> Decimal:
    return (Decimal(str(price)) * Decimal(str(volume))).quantize(
        MONEY_PLACES, rounding=ROUND_HALF_EVEN
    )


class TestTickRuleRisingPrices:
    """Scenario 1: rising prints are aggressive BUY / inflow."""

    def test_uptick_classifies_as_buy_inflow(self, engine: LiquidityEngine) -> None:
        seed = engine.process_trade("AAPL", "100.00", "10")
        result = engine.process_trade("AAPL", "100.25", "10")

        assert seed.tick is TickType.UNCLASSIFIED
        assert result.side is TradeSide.BUY
        assert result.tick is TickType.UPTICK
        assert result.money_flow == notional("100.25", "10")
        assert result.session.inflow == notional("100.25", "10")
        assert result.session.outflow == money("0")
        assert result.session.net_flow == notional("100.25", "10")
        assert result.session.buy_volume == money("10")
        assert result.session.sell_volume == money("0")
        assert result.session.last_side is TradeSide.BUY

    def test_monotonic_uptick_series_accumulates_inflow_only(
        self, engine: LiquidityEngine
    ) -> None:
        engine.process_trade("4030", "24.00", "1")
        prints = [
            engine.process_trade("4030", "24.10", "100"),
            engine.process_trade("4030", "24.25", "50"),
            engine.process_trade("4030", "24.40", "25"),
        ]

        expected_inflow = (
            notional("24.10", "100") + notional("24.25", "50") + notional("24.40", "25")
        )
        session = prints[-1].session
        assert all(item.side is TradeSide.BUY and item.tick is TickType.UPTICK for item in prints)
        assert session.inflow == expected_inflow
        assert session.outflow == money("0")
        assert session.net_flow == expected_inflow
        assert session.buy_volume == money("175")
        assert session.classified_count == 3


class TestTickRuleFallingPrices:
    """Scenario 2: falling prints are aggressive SELL / outflow."""

    def test_downtick_classifies_as_sell_outflow(self, engine: LiquidityEngine) -> None:
        engine.process_trade("MSFT", "420.50", "10")
        result = engine.process_trade("MSFT", "419.75", "8")

        assert result.side is TradeSide.SELL
        assert result.tick is TickType.DOWNTICK
        assert result.money_flow == -notional("419.75", "8")
        assert result.session.outflow == notional("419.75", "8")
        assert result.session.inflow == money("0")
        assert result.session.net_flow == -notional("419.75", "8")
        assert result.session.sell_volume == money("8")
        assert result.session.buy_volume == money("0")
        assert result.session.last_side is TradeSide.SELL

    def test_monotonic_downtick_series_accumulates_outflow_only(
        self, engine: LiquidityEngine
    ) -> None:
        engine.process_trade("TSLA", "250.00", "1")
        prints = [
            engine.process_trade("TSLA", "249.50", "40"),
            engine.process_trade("TSLA", "248.00", "10"),
            engine.process_trade("TSLA", "247.25", "5"),
        ]

        expected_outflow = (
            notional("249.50", "40") + notional("248.00", "10") + notional("247.25", "5")
        )
        session = prints[-1].session
        assert all(item.side is TradeSide.SELL and item.tick is TickType.DOWNTICK for item in prints)
        assert session.outflow == expected_outflow
        assert session.inflow == money("0")
        assert session.net_flow == -expected_outflow
        assert session.sell_volume == money("55")


class TestTickRuleEqualPrices:
    """Scenario 3: unchanged price follows the last different price (zero-tick)."""

    def test_equal_price_after_uptick_is_zero_tick_buy(self, engine: LiquidityEngine) -> None:
        engine.process_trade("NVDA", "100.00", "1")
        uptick = engine.process_trade("NVDA", "101.00", "2")
        zero_tick = engine.process_trade("NVDA", "101.00", "5")

        assert uptick.tick is TickType.UPTICK
        assert zero_tick.side is TradeSide.BUY
        assert zero_tick.tick is TickType.ZERO_TICK
        assert zero_tick.session.last_different_price == money("100")
        assert zero_tick.money_flow == notional("101.00", "5")
        assert zero_tick.session.inflow == notional("101.00", "2") + notional("101.00", "5")

    def test_equal_price_after_downtick_is_zero_tick_sell(self, engine: LiquidityEngine) -> None:
        engine.process_trade("NVDA", "100.00", "1")
        downtick = engine.process_trade("NVDA", "99.00", "3")
        zero_tick = engine.process_trade("NVDA", "99.00", "4")

        assert downtick.tick is TickType.DOWNTICK
        assert zero_tick.side is TradeSide.SELL
        assert zero_tick.tick is TickType.ZERO_TICK
        assert zero_tick.session.last_different_price == money("100")
        assert zero_tick.money_flow == -notional("99.00", "4")
        assert zero_tick.session.outflow == notional("99.00", "3") + notional("99.00", "4")

    def test_run_of_equal_prices_keeps_following_last_different_price(
        self, engine: LiquidityEngine
    ) -> None:
        engine.process_trade("IBM", "50.00", "1")
        engine.process_trade("IBM", "51.00", "1")
        repeats = [
            engine.process_trade("IBM", "51.00", "10"),
            engine.process_trade("IBM", "51.00", "20"),
            engine.process_trade("IBM", "51.00", "30"),
        ]

        assert all(item.tick is TickType.ZERO_TICK and item.side is TradeSide.BUY for item in repeats)
        assert repeats[-1].session.last_different_price == money("50.00")
        assert repeats[-1].session.buy_volume == money("61")

    def test_flat_tape_stays_unclassified_until_a_price_change(
        self, engine: LiquidityEngine
    ) -> None:
        results = [
            engine.process_trade("F", "10.10", "1"),
            engine.process_trade("F", "10.10", "2"),
            engine.process_trade("F", "10.10", "3"),
        ]

        assert all(item.tick is TickType.UNCLASSIFIED and item.side is None for item in results)
        assert results[-1].session.net_flow == money("0")
        assert results[-1].session.last_different_price is None
        assert results[-1].session.classified_count == 0


class TestEdgeCases:
    """Scenario 4: zero volume, extreme prices, and Decimal money-flow precision."""

    def test_zero_volume_does_not_move_cash_but_updates_tick_memory(
        self, engine: LiquidityEngine
    ) -> None:
        engine.process_trade("AAPL", "10.00", "5")
        zero_uptick = engine.process_trade("AAPL", "10.50", "0")
        later = engine.process_trade("AAPL", "10.50", "4")

        assert zero_uptick.side is TradeSide.BUY
        assert zero_uptick.tick is TickType.UPTICK
        assert zero_uptick.money_flow == money("0")
        assert zero_uptick.session.net_flow == money("0")
        assert zero_uptick.session.buy_volume == money("0")
        assert later.tick is TickType.ZERO_TICK
        assert later.money_flow == notional("10.50", "4")
        assert later.session.inflow == notional("10.50", "4")

    def test_zero_volume_downtick_still_sets_last_different_price(
        self, engine: LiquidityEngine
    ) -> None:
        engine.process_trade("AAPL", "20.00", "1")
        zero_down = engine.process_trade("AAPL", "19.00", "0")
        follow = engine.process_trade("AAPL", "19.00", "10")

        assert zero_down.side is TradeSide.SELL
        assert zero_down.money_flow == money("0")
        assert follow.tick is TickType.ZERO_TICK
        assert follow.side is TradeSide.SELL
        assert follow.session.last_different_price == money("20.00")
        assert follow.session.outflow == notional("19.00", "10")

    def test_extreme_low_price_at_price_quantum(self, engine: LiquidityEngine) -> None:
        engine.process_trade("PENNY", "0.00000001", "1")
        result = engine.process_trade("PENNY", "0.00000002", "1_000_000")

        assert result.side is TradeSide.BUY
        assert result.money_flow == money("0.02000000")
        assert result.session.inflow == money("0.02000000")

    def test_extreme_high_price_and_size_use_decimal_notional(
        self, engine: LiquidityEngine
    ) -> None:
        engine.process_trade("BRK", "999999.99", "1")
        result = engine.process_trade("BRK", "1000000.00", "10000")

        expected = notional("1000000.00", "10000")
        assert result.side is TradeSide.BUY
        assert result.money_flow == expected
        assert result.session.inflow == expected
        assert result.session.net_flow == expected
        assert isinstance(result.money_flow, Decimal)

    def test_sub_quantum_price_is_rejected_as_non_positive(
        self, engine: LiquidityEngine
    ) -> None:
        with pytest.raises(InvalidTradeError, match="greater than zero"):
            engine.process_trade("DUST", "0.000000001", "10")

    def test_decimal_money_flow_matches_exact_product_not_binary_float(
        self, engine: LiquidityEngine
    ) -> None:
        engine.process_trade("F", "10.00", "1")
        result = engine.process_trade("F", "10.10", "3")

        exact = (Decimal("10.10") * Decimal("3")).quantize(
            MONEY_QUANTUM, rounding=ROUND_HALF_EVEN
        )
        binary_product = 10.10 * 3

        assert result.money_flow == money("30.30")
        assert result.money_flow == exact
        assert result.session.inflow == exact
        assert binary_product != 30.3
        assert Decimal(str(binary_product)) != Decimal("30.30")

    def test_classic_binary_float_sum_is_normalized_before_tick_compare(
        self, engine: LiquidityEngine
    ) -> None:
        engine.process_trade("X", 0.1, 10)
        engine.process_trade("X", 0.3, 10)
        equal_to_sum = engine.process_trade("X", 0.1 + 0.2, 10)

        assert equal_to_sum.price == money("0.3")
        assert equal_to_sum.tick is TickType.ZERO_TICK
        assert equal_to_sum.side is TradeSide.BUY
        assert equal_to_sum.money_flow == notional("0.3", "10")

    def test_repeated_decimal_cents_do_not_drift(self, engine: LiquidityEngine) -> None:
        engine.process_trade("CENTS", "1.00", "1")
        for _ in range(100):
            engine.process_trade("CENTS", "1.01", "1")

        session = engine.get_session("CENTS")
        expected = notional("1.01", "1") * 100
        assert session.inflow == expected
        assert session.net_flow == expected
        assert session.buy_volume == money("100")
        assert session.inflow == session.outflow + session.net_flow

    def test_mixed_buy_and_sell_net_flow_identity(self, engine: LiquidityEngine) -> None:
        results = engine.process_trades(
            [
                ("NVDA", "100.00", "10"),
                ("NVDA", "101.00", "10"),
                ("NVDA", "101.00", "5"),
                ("NVDA", "99.00", "8"),
            ]
        )
        session = results[-1].session
        assert session.inflow == notional("101.00", "10") + notional("101.00", "5")
        assert session.outflow == notional("99.00", "8")
        assert session.net_flow == session.inflow - session.outflow
        assert session.buy_volume == money("15")
        assert session.sell_volume == money("8")

    def test_rejects_invalid_numeric_inputs(self, engine: LiquidityEngine) -> None:
        with pytest.raises(InvalidTradeError, match="greater than zero"):
            engine.process_trade("AAPL", "0", "10")
        with pytest.raises(InvalidTradeError, match="greater than zero"):
            engine.process_trade("AAPL", "-1.5", "10")
        with pytest.raises(InvalidTradeError, match="negative"):
            engine.process_trade("AAPL", "10", "-1")
        with pytest.raises(InvalidTradeError, match="finite"):
            engine.process_trade("AAPL", float("nan"), 1)
        with pytest.raises(InvalidTradeError, match="finite"):
            engine.process_trade("AAPL", float("inf"), 1)
        with pytest.raises(InvalidTradeError, match="valid number"):
            engine.process_trade("AAPL", "10.2.3", 1)
        with pytest.raises(InvalidTradeError, match="symbol is required"):
            engine.process_trade("   ", "10", "1")


class TestConcurrentUpdates:
    """Scenario 5: concurrent writers must not corrupt session totals."""

    def test_parallel_prints_on_one_symbol_preserve_invariants(
        self, engine: LiquidityEngine
    ) -> None:
        engine.process_trade("AAPL", "100.00", "1")
        workers = 8
        prints_per_worker = 50

        def worker(index: int) -> None:
            price = "101.00" if index % 2 == 0 else "99.00"
            for _ in range(prints_per_worker):
                engine.process_trade("AAPL", price, "1")

        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(worker, range(workers)))

        session = engine.get_session("AAPL")
        total_prints = 1 + workers * prints_per_worker
        assert session.trade_count == total_prints
        assert session.classified_count == workers * prints_per_worker
        assert session.net_flow == session.inflow - session.outflow
        assert session.buy_volume + session.sell_volume == money(str(workers * prints_per_worker))
        assert session.inflow == notional("101.00", "1") * (workers // 2) * prints_per_worker
        assert session.outflow == notional("99.00", "1") * (workers // 2) * prints_per_worker

    def test_parallel_prints_across_symbols_stay_isolated(
        self, engine: LiquidityEngine
    ) -> None:
        symbols = ["AAA", "BBB", "CCC", "DDD"]
        prints_each = 80

        def worker(symbol: str) -> None:
            engine.process_trade(symbol, "10.00", "1")
            for _ in range(prints_each):
                engine.process_trade(symbol, "11.00", "2")

        with ThreadPoolExecutor(max_workers=len(symbols)) as pool:
            list(pool.map(worker, symbols))

        for symbol in symbols:
            session = engine.get_session(symbol)
            assert session.trade_count == prints_each + 1
            assert session.buy_volume == money(str(prints_each * 2))
            assert session.inflow == notional("11.00", "2") * prints_each
            assert session.outflow == money("0")
        assert engine.active_symbols() == sorted(symbols)

    def test_barrier_burst_does_not_lose_or_double_count_trades(
        self, engine: LiquidityEngine
    ) -> None:
        ready = Barrier(16)
        failed = Event()

        def burst(index: int) -> int:
            try:
                ready.wait(timeout=5)
                result = engine.process_trade("BURST", str(50 + index), "1")
                return result.session.trade_count
            except Exception:
                failed.set()
                raise

        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = [pool.submit(burst, index) for index in range(16)]
            counts = [future.result() for future in as_completed(futures)]

        assert not failed.is_set()
        session = engine.get_session("BURST")
        assert session.trade_count == 16
        assert max(counts) == 16
        assert session.classified_count == 15
        assert session.net_flow == session.inflow - session.outflow

    def test_unknown_ticker_and_reset_remain_consistent_after_contention(
        self, engine: LiquidityEngine
    ) -> None:
        def writer() -> None:
            engine.process_trade("LOCK", "10.00", "1")
            engine.process_trade("LOCK", "10.50", "1")

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: writer(), range(20)))

        assert engine.get_session("LOCK").trade_count == 40
        engine.reset("LOCK")
        with pytest.raises(SymbolNotFoundError):
            engine.get_session("LOCK")
        engine.reset()
        assert engine.snapshot_all() == {}


class TestVwapAndOrderBook:
    def test_vwap_is_volume_weighted_across_classified_and_seed_prints(
        self, engine: LiquidityEngine
    ) -> None:
        engine.process_trade("4030", "24.00", "100")
        engine.process_trade("4030", "25.00", "300")
        levels = engine.levels_snapshot("4030")
        assert levels.vwap == Decimal("24.75")

    def test_order_book_pressure_and_atr_from_quote(self, engine: LiquidityEngine) -> None:
        engine.process_trade("4030", "24.00", "50")
        engine.process_trade("4030", "24.40", "50")
        levels = engine.observe_market(
            "4030",
            {
                "price": "24.40",
                "high": "24.80",
                "low": "23.90",
                "previous_close": "24.00",
                "bid": "24.38",
                "ask": "24.42",
                "bid_size": "8000",
                "ask_size": "2000",
            },
        )
        assert levels.book_pressure == Decimal("0.8000")
        assert levels.bid == Decimal("24.38")
        assert levels.ask == Decimal("24.42")
        assert levels.atr is not None
        assert levels.atr > Decimal("0")
