from datetime import date, timedelta
from decimal import Decimal

from app.core.config import Settings
from app.models.trade import TradeSide
from app.services.explosive_momentum import (
    EXPLOSIVE_FLAG,
    HIDDEN_ACCUM_FLAG,
    WATCH_FLAG,
    ExplosiveInputs,
    evaluate_explosive,
    inputs_from_snapshot,
)
from app.services.last_quotes import LastQuoteBook
from app.services.liquidity_engine import LiquidityRadarEngine
from app.services.tickchart_integration import TickChartFeed
from app.services.under_watch import UnderWatchService


def _window(volume: float = 1_000_000) -> tuple[float, ...]:
    return tuple([volume] * 10)


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def step(self, seconds: float) -> None:
        self.t += seconds


def test_volume_spike_with_compressed_range_flags_under_watch() -> None:
    decision = evaluate_explosive(
        ExplosiveInputs(
            symbol="4030",
            price=Decimal("24.50"),
            volume=Decimal("2_600_000"),
            window_volumes=_window(),
            session_high=Decimal("24.62"),
            session_low=Decimal("24.38"),
            prev_close=Decimal("24.45"),
            change_percent=Decimal("0.20"),
            net_flow=Decimal("8000"),
        )
    )
    assert decision.watch is True
    assert decision.explosive is False
    assert decision.hidden_accumulation is True
    assert decision.flag == HIDDEN_ACCUM_FLAG
    assert decision.volume_ratio is not None
    assert decision.volume_ratio >= Decimal("1.5")
    assert decision.compressed is True


def test_minute_volume_ratio_can_flag_when_session_history_is_thin() -> None:
    decision = evaluate_explosive(
        ExplosiveInputs(
            symbol="2222",
            price=Decimal("27.10"),
            minute_volume_ratio=Decimal("1.8"),
            change_percent=Decimal("0.40"),
            prev_close=Decimal("27.00"),
        )
    )
    assert decision.watch is True
    assert decision.upward is True
    assert decision.hidden_accumulation is True
    assert decision.flag == HIDDEN_ACCUM_FLAG


def test_volume_dump_is_not_accumulation() -> None:
    decision = evaluate_explosive(
        ExplosiveInputs(
            symbol="1120",
            price=Decimal("90.00"),
            volume=Decimal("3_000_000"),
            window_volumes=_window(),
            session_high=Decimal("94.50"),
            session_low=Decimal("89.40"),
            change_percent=Decimal("-2.4"),
            net_flow=Decimal("-40000"),
            buy_volume=Decimal("200"),
            sell_volume=Decimal("900"),
        )
    )
    assert decision.watch is False
    assert decision.explosive is False
    assert decision.flag is None


def test_expanding_up_tape_is_generic_watch_not_iceberg() -> None:
    decision = evaluate_explosive(
        ExplosiveInputs(
            symbol="4030",
            price=Decimal("26.00"),
            volume=Decimal("2_600_000"),
            window_volumes=_window(),
            session_high=Decimal("26.20"),
            session_low=Decimal("24.80"),
            prev_close=Decimal("25.00"),
            change_percent=Decimal("4.0"),
            net_flow=Decimal("8000"),
        )
    )
    assert decision.watch is True
    assert decision.hidden_accumulation is False
    assert decision.flag == WATCH_FLAG


def test_volume_held_at_session_low_is_hidden_accumulation() -> None:
    decision = evaluate_explosive(
        ExplosiveInputs(
            symbol="1120",
            price=Decimal("90.10"),
            volume=Decimal("2_400_000"),
            window_volumes=_window(),
            session_high=Decimal("93.00"),
            session_low=Decimal("90.00"),
            change_percent=Decimal("2.5"),
            net_flow=Decimal("12000"),
            near_bid_wall=True,
        )
    )
    assert decision.watch is True
    assert decision.hidden_accumulation is True
    assert decision.supported is True
    assert decision.flag == HIDDEN_ACCUM_FLAG
    assert HIDDEN_ACCUM_FLAG in decision.reasons


def test_quiet_volume_stays_off_the_watchlist() -> None:
    decision = evaluate_explosive(
        ExplosiveInputs(
            symbol="2010",
            price=Decimal("70.00"),
            volume=Decimal("1_100_000"),
            window_volumes=_window(),
            change_percent=Decimal("0.30"),
        )
    )
    assert decision.watch is False


def test_ask_side_flow_and_resistance_break_trigger_explosive_flag() -> None:
    prior = tuple(20.0 + index * 0.05 for index in range(10))
    decision = evaluate_explosive(
        ExplosiveInputs(
            symbol="7010",
            price=Decimal("21.20"),
            volume=Decimal("2_400_000"),
            window_volumes=_window(),
            session_high=Decimal("21.22"),
            session_low=Decimal("20.95"),
            prev_close=Decimal("20.80"),
            change_percent=Decimal("1.90"),
            net_flow=Decimal("180000"),
            inflow=Decimal("260000"),
            outflow=Decimal("80000"),
            buy_volume=Decimal("9000"),
            sell_volume=Decimal("2500"),
            last_side=TradeSide.BUY.value,
            ask=Decimal("21.18"),
            prior_closes=prior,
        )
    )
    assert decision.watch is True
    assert decision.explosive is True
    assert decision.flag == EXPLOSIVE_FLAG
    assert decision.aggressive_buy is True
    assert decision.flow_spike is True
    assert decision.resistance_break is True
    assert EXPLOSIVE_FLAG in decision.reasons


def test_inputs_from_snapshot_drops_today_close_from_resistance() -> None:
    inputs = inputs_from_snapshot(
        {
            "symbol": "2222",
            "last_price": 28.4,
            "closes": [26.0, 26.4, 26.8, 27.1, 27.4, 27.6, 27.8, 27.9, 28.0, 28.1, 28.4],
            "volumes": [1_000_000] * 10 + [2_800_000],
            "session_volume": 2_800_000,
        }
    )
    assert inputs is not None
    assert inputs.price == Decimal("28.4")
    assert Decimal(str(inputs.prior_closes[-1])) < inputs.price


def test_under_watch_store_upserts_and_retains(tmp_path) -> None:
    store = UnderWatchService(path=tmp_path / "under_watch.json")
    inputs = ExplosiveInputs(
        symbol="4030",
        name="البحري",
        price=Decimal("24.80"),
        volume=Decimal("2_200_000"),
        window_volumes=_window(),
        change_percent=Decimal("0.50"),
        net_flow=Decimal("12000"),
    )
    row = store.observe(inputs)
    assert row is not None
    assert row["symbol"] == "4030"
    assert row["flag"] == HIDDEN_ACCUM_FLAG
    assert row["hidden_accumulation"] is True
    assert store.contains("4030")
    kept = store.retain(["4030"])
    assert [item["symbol"] for item in kept] == ["4030"]
    assert store.contains("4030")


def test_under_watch_confirms_hidden_accumulation_after_multi_hit_window(tmp_path) -> None:
    clock = _Clock()
    store = UnderWatchService(
        path=tmp_path / "under_watch.json",
        confirm_hits=3,
        miss_hits=3,
        sample_seconds=20,
        cooldown_seconds=180,
        clock=clock,
    )
    inputs = ExplosiveInputs(
        symbol="1120",
        price=Decimal("90.10"),
        volume=Decimal("2_400_000"),
        window_volumes=_window(),
        session_high=Decimal("90.25"),
        session_low=Decimal("90.00"),
        change_percent=Decimal("0.10"),
        near_bid_wall=True,
    )
    quiet = ExplosiveInputs(
        symbol="1120",
        price=Decimal("90.10"),
        volume=Decimal("800_000"),
        window_volumes=_window(),
        change_percent=Decimal("0.10"),
    )
    assert store.observe(inputs) is None
    clock.step(25)
    assert store.observe(inputs) is None
    clock.step(25)
    row = store.observe(inputs)
    assert row is not None
    assert row["hidden_accumulation"] is True
    assert row["flag"] == HIDDEN_ACCUM_FLAG
    clock.step(25)
    assert store.observe(quiet) is not None
    clock.step(25)
    assert store.observe(quiet) is not None
    assert store.contains("1120")
    clock.step(25)
    assert store.observe(quiet) is None
    assert store.contains("1120") is False
    clock.step(25)
    assert store.observe(inputs) is None
    clock.step(200)
    assert store.observe(inputs) is None
    clock.step(25)
    assert store.observe(inputs) is None
    clock.step(25)
    revived = store.observe(inputs)
    assert revived is not None
    assert revived["hidden_accumulation"] is True


def test_tickchart_scan_flags_volume_breakout_into_under_watch(tmp_path) -> None:
    settings = Settings(
        _env_file=None,
        tickchart_api_key="test-key",
        sahmk_api_key="test-key",
        enable_mock_feed=False,
    )
    quotes = LastQuoteBook(path=tmp_path / "quotes.json")
    today = date(2026, 9, 21)
    prior_day = today - timedelta(days=1)
    bars = []
    for index in range(10):
        bars.append(
            {
                "symbol": "2222",
                "date": (prior_day - timedelta(days=10 - index)).isoformat(),
                "close": 26.0 + index * 0.08,
                "volume": 1_000_000,
            }
        )
    quotes.merge_history(bars, keep_today=True)
    quotes.apply_closes(
        [
            {
                "symbol": "2222",
                "last_price": 27.40,
                "volume": 2_700_000,
                "change_percent": 1.6,
                "net_flow": 95_000,
                "prev_close": 26.96,
                "high": 27.45,
                "low": 27.10,
                "open": 27.05,
            }
        ]
    )
    engine = LiquidityRadarEngine()
    for qty in (800, 900, 1200, 1500):
        engine.process_trade("2222", Decimal("27.40"), Decimal(qty))
    feed = TickChartFeed(
        engine,
        _DummyBroadcaster(),
        settings,
        quotes=quotes,
        under_watch=UnderWatchService(path=tmp_path / "under_watch.json"),
    )
    rows = feed.scan_explosive_watch()
    assert any(row["symbol"] == "2222" for row in rows)
    flagged = next(row for row in rows if row["symbol"] == "2222")
    assert flagged["flag"] in {WATCH_FLAG, EXPLOSIVE_FLAG, HIDDEN_ACCUM_FLAG}
    report = feed.radar_report("2222")
    assert report["under_watch"] is True
    assert report["watch_flag"]


class _DummyBroadcaster:
    async def broadcast(self, symbol: str, message: dict) -> None:
        return None

    def subscribed_symbols(self) -> set[str]:
        return set()
