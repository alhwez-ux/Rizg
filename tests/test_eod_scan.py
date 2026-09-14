from __future__ import annotations

from app.services.eod_scan import KIND_BOUNCE, KIND_MOMENTUM, evaluate_close_setup, scan_end_of_day


def _prior_closes(end: float, count: int = 10) -> list[float]:
    resistance = end * 0.993
    start = resistance * 0.97
    step = (resistance - start) / max(count - 1, 1)
    return [round(start + step * index, 4) for index in range(count)]


def _breakout_row(
    symbol: str,
    close: float,
    *,
    volume: float = 1_600_000,
    net_flow: float = 25_000,
    mfi: float = 60,
    session_low: float | None = None,
    session_high: float | None = None,
    change_percent: float | None = None,
    trap: dict | None = None,
    spread: float | None = None,
    ask_wall: dict | None = None,
    bid_wall: dict | None = None,
) -> dict:
    prior = _prior_closes(close)
    return {
        "symbol": symbol,
        "last_price": close,
        "closes": [*prior, close],
        "volumes": [1_000_000] * 10 + [volume],
        "session_volume": volume,
        "session_low": session_low if session_low is not None else close * 0.994,
        "session_high": session_high if session_high is not None else close * 1.002,
        "change_percent": change_percent if change_percent is not None else 1.8,
        "net_flow": net_flow,
        "mfi": mfi,
        "trap": trap,
        "spread": spread,
        "ask_wall": ask_wall,
        "bid_wall": bid_wall,
    }


def test_eod_scan_requires_ten_session_breakout_with_volume_and_flow() -> None:
    rows = scan_end_of_day(
        [
            _breakout_row("1120", 96.4, volume=2_100_000, net_flow=80_000, mfi=64),
            _breakout_row("2222", 28.4, volume=1_700_000, session_low=27.90, session_high=28.45),
            _breakout_row("4030", 24.9, volume=800_000, net_flow=-12_000, change_percent=-0.4),
        ]
    )
    symbols = {row["symbol"] for row in rows}
    assert "1120" in symbols
    assert "2222" in symbols
    assert "4030" not in symbols
    kinds = {row["symbol"]: row["signal_kind"] for row in rows}
    assert kinds["1120"] == KIND_MOMENTUM
    assert kinds["2222"] == KIND_BOUNCE
    assert all(row["entry"] is True for row in rows)
    assert all(row["scan_mode"] == "end_of_day" for row in rows)


def test_eod_scan_blocks_false_breakout_wicks_and_limit_chases() -> None:
    wick = _breakout_row("1180", 38.2, session_low=37.9, session_high=39.4)
    limit = _breakout_row("1010", 30.0, change_percent=9.8)
    dump = _breakout_row("1050", 40.0, net_flow=-50_000)
    exhaustion = _breakout_row("1150", 27.0, volume=1_550_000, mfi=88)
    wall = _breakout_row(
        "1060",
        33.0,
        ask_wall={"price": 33.1, "quantity": 90_000},
        bid_wall={"price": 32.9, "quantity": 8_000},
    )
    rows = scan_end_of_day([wick, limit, dump, exhaustion, wall])
    assert rows == []


def test_eod_scan_skips_symbols_without_history_or_close() -> None:
    assert evaluate_close_setup({"symbol": "2010", "volume": 5_000_000}) is None
    assert evaluate_close_setup({"symbol": "2010", "last_price": 90.0, "volume": 5_000_000}) is None
    assert evaluate_close_setup({"symbol": "9510", "last_price": 12.0, "prev_close": 11.0, "session_volume": 2_000_000}) is None
    assert scan_end_of_day([{"symbol": "2010", "volume": 5_000_000}]) == []


def test_eod_scan_uses_today_session_when_history_is_short() -> None:
    rows = scan_end_of_day(
        [
            {
                "symbol": "2380",
                "last_price": 18.29,
                "prev_close": 17.62,
                "session_open": 17.62,
                "session_high": 18.35,
                "session_low": 17.20,
                "session_volume": 13_238_697,
                "change_percent": 3.80,
                "net_flow": 59_092_631,
                "liquidity_flow": 1.69,
            },
            {
                "symbol": "2222",
                "last_price": 25.66,
                "prev_close": 25.72,
                "session_open": 25.70,
                "session_high": 25.82,
                "session_low": 25.52,
                "session_volume": 5_671_859,
                "change_percent": -0.23,
                "net_flow": -17_624_308,
            },
        ]
    )
    symbols = {row["symbol"] for row in rows}
    assert "2380" in symbols
    assert "2222" not in symbols
    assert rows[0]["scan_mode"] == "end_of_day"
