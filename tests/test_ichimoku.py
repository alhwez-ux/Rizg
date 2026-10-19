from datetime import date, timedelta

from app.services.ichimoku import ichimoku_reading
from app.services.last_quotes import LastQuoteBook
from app.services.session_history import parse_chart_ohlc


def _bars(rows: list[tuple[float, float, float, float]]) -> list[dict]:
    start = date(2024, 1, 1)
    return [
        {
            "date": (start + timedelta(days=index)).isoformat(),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
        }
        for index, (open_, high, low, close) in enumerate(rows)
    ]


def test_flat_cloud_uses_the_nine_and_twenty_six_session_midpoint():
    rows = [(10.0, 12.0, 9.0, 10.5) for _ in range(90)]
    reading = ichimoku_reading(_bars(rows))
    assert reading is not None
    assert reading["tenkan"] == 10.5
    assert reading["kijun"] == 10.5
    assert reading["span_a"] == 10.5
    assert reading["span_b"] == 10.5
    assert reading["trend"] == "range"
    assert reading["position"] == "inside"
    assert reading["signal"] == "watch"
    assert reading["chikou"] == 10.5


def test_rising_sessions_are_an_uptrend_without_a_fresh_entry():
    rows = []
    for index in range(100):
        price = 40 + index * 0.5
        rows.append((price, price + 1.2, price - 0.8, price + 0.7))
    reading = ichimoku_reading(_bars(rows))
    assert reading is not None
    assert reading["trend"] == "up"
    assert reading["position"] == "above"
    assert reading["signal"] == "watch"
    assert reading["future_span_a"] > reading["future_span_b"]


def test_entry_needs_breakout_tenkan_cross_and_hammer_together():
    rows = [(20.0, 22.0, 18.0, 20.0) for _ in range(80)]
    rows.append((21.0, 24.0, 14.0, 20.0))
    rows.extend((19.0, 21.0, 18.0, 20.0) for _ in range(8))
    rows.append((24.0, 27.0, 18.0, 26.0))
    reading = ichimoku_reading(_bars(rows))
    assert reading is not None
    assert reading["pattern"] == "hammer"
    assert reading["signal"] == "entry"
    assert reading["trend"] == "up"
    assert reading["tenkan"] == 22.5
    assert reading["kijun"] == 20.5


def test_exit_needs_a_bearish_cross_and_a_shooting_star():
    rows = []
    for index in range(80):
        price = 90 - index * 0.15
        rows.append((price + 0.2, price + 0.8, price - 0.8, price - 0.2))
    rows.append((80.0, 110.0, 78.0, 82.0))
    for index in range(8):
        price = 78 - index * 0.4
        rows.append((price + 0.2, price + 0.5, price - 0.6, price - 0.2))
    rows.append((70.0, 77.5, 69.6, 71.5))
    reading = ichimoku_reading(_bars(rows))
    assert reading is not None
    assert reading["pattern"] == "shooting_star"
    assert reading["signal"] == "exit"
    assert reading["trend"] == "down"
    assert reading["position"] == "below"
    assert reading["future_span_a"] < reading["future_span_b"]


def test_bullish_engulfing_is_named_and_a_flat_future_cloud_stays_unlabeled():
    rows = [(20.0, 22.0, 18.0, 20.0) for _ in range(88)]
    rows.append((22.0, 22.4, 16.0, 17.0))
    rows.append((16.5, 23.0, 16.2, 22.5))
    reading = ichimoku_reading(_bars(rows))
    assert reading is not None
    assert reading["pattern"] == "bullish_engulfing"
    assert reading["signal"] == "watch"
    assert reading["trend"] is None


def test_bearish_engulfing_is_named():
    rows = [(20.0, 22.0, 18.0, 20.0) for _ in range(88)]
    rows.append((17.0, 23.0, 16.5, 22.0))
    rows.append((22.5, 23.0, 16.0, 16.5))
    reading = ichimoku_reading(_bars(rows))
    assert reading is not None
    assert reading["pattern"] == "bearish_engulfing"


def test_a_measured_session_bar_replaces_the_stored_close_for_that_day():
    bars = _bars([(20.0, 22.0, 18.0, 20.0) for _ in range(90)])
    reading = ichimoku_reading(
        bars,
        {"date": bars[-1]["date"], "open": 24.0, "high": 27.0, "low": 18.0, "close": 26.0},
    )
    assert reading is not None
    assert reading["chikou"] == 26.0


def test_short_or_close_only_history_stays_silent():
    full = [(20.0, 22.0, 18.0, 20.0) for _ in range(77)]
    assert ichimoku_reading(_bars(full)) is None
    closes = [{"date": f"2024-01-{(index % 28) + 1:02d}", "close": 20.0} for index in range(90)]
    assert ichimoku_reading(closes) is None


def test_merge_keeps_high_and_low_when_a_later_close_has_no_range(tmp_path):
    book = LastQuoteBook(tmp_path / "quotes.json")
    book.merge_history(
        [{"symbol": "1120", "date": "2026-10-01", "close": 60.0, "open": 59.0, "high": 62.0, "low": 58.0, "volume": 1000}]
    )
    book.merge_history([{"symbol": "1120", "date": "2026-10-01", "close": 61.0, "volume": 1100}])
    stored = book.close_history("1120")[0]
    assert stored["close"] == 61.0
    assert stored["high"] == 62.0
    assert stored["low"] == 58.0
    assert stored["open"] == 59.0


def test_chart_parser_keeps_open_high_low_and_skips_a_bar_without_them():
    payload = {
        "spark": {
            "result": [
                {
                    "symbol": "1120.SR",
                    "timestamp": [1_700_000_000, 1_700_086_400],
                    "indicators": {
                        "quote": [
                            {
                                "open": [10.0, None],
                                "high": [12.0, None],
                                "low": [9.0, None],
                                "close": [11.0, 11.5],
                                "volume": [1000, 800],
                            }
                        ]
                    },
                }
            ]
        }
    }
    rows = parse_chart_ohlc(payload)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "1120"
    assert rows[0]["open"] == 10.0
    assert rows[0]["high"] == 12.0
    assert rows[0]["low"] == 9.0
