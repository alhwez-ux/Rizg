from datetime import datetime, timedelta, timezone

from app.services.tasi_correction import (
    STATE_APPROACH,
    STATE_CONFIRMED,
    STATE_ENDING,
    STATE_REBOUND,
    STATE_SAFE,
    classify_tasi_index,
    completed_sessions,
    parse_tasi_chart,
)


def _history(closes: list[float], volumes: list[float] | None = None) -> list[dict]:
    size = volumes or [1_000_000] * len(closes)
    return [
        {"date": f"2026-01-{index + 1:02d}", "close": close, "volume": volume}
        for index, (close, volume) in enumerate(zip(closes, size))
    ]


def _leaders(net: str) -> list[dict]:
    rows = []
    for symbol in ("2222", "1120", "1180"):
        if net == "out":
            flow = {"institutional_inflow": 10, "institutional_outflow": 80}
        else:
            flow = {"institutional_inflow": 80, "institutional_outflow": 10}
        rows.append({"symbol": symbol, "block_trades": 0, "block_side": None, **flow})
    return rows


def test_rising_peaks_with_fading_volume_are_an_approach() -> None:
    row = classify_tasi_index(
        {
            "history": _history([100, 101, 102, 103], [400_000, 300_000, 200_000, 100_000]),
        }
    )
    assert row is not None
    assert row["state"] == STATE_APPROACH
    assert row["alert"] is True
    assert "قمم صاعدة بأحجام متناقصة" in row["reasons"]


def test_fresh_break_of_ema20_is_an_approach() -> None:
    closes = [100.0] * 24 + [99.0]
    row = classify_tasi_index({"history": _history(closes)})
    assert row is not None
    assert row["state"] == STATE_APPROACH
    assert "كسر متوسط 20" in row["reasons"]


def test_two_down_closes_without_leader_flow_are_not_a_confirmed_correction() -> None:
    closes = [100.0] * 24 + [99.0, 98.0]
    row = classify_tasi_index({"history": _history(closes)})
    assert row is not None
    assert row["state"] != STATE_CONFIRMED


def test_support_break_and_leader_outflow_confirm_the_correction() -> None:
    closes = [100.0] * 24 + [99.0, 98.0]
    row = classify_tasi_index({"history": _history(closes), "leaders": _leaders("out")})
    assert row is not None
    assert row["state"] == STATE_CONFIRMED
    assert row["alert"] is True
    assert "تدفق خارج من الأسهم القيادية" in row["reasons"]


def test_drying_volume_near_the_slow_average_is_the_end_approaching() -> None:
    closes = [100.0] * 55
    closes[-4:] = [100.0, 99.6, 99.3, 99.2]
    volumes = [1_000_000] * 55
    volumes[-4:] = [800_000, 500_000, 300_000, 150_000]
    row = classify_tasi_index({"history": _history(closes, volumes)})
    assert row is not None
    assert row["state"] == STATE_ENDING
    assert row["alert"] is False


def test_up_candle_without_institutional_evidence_is_not_a_rebound() -> None:
    closes = [100.0] * 54 + [100.8]
    volumes = [100_000] * 54 + [220_000]
    row = classify_tasi_index({"history": _history(closes, volumes)})
    assert row is None or row["state"] != STATE_REBOUND


def test_strong_candle_and_buy_blocks_at_support_end_the_correction() -> None:
    closes = [120.0] * 20 + [100.0] * 34 + [100.6]
    volumes = [100_000] * 54 + [250_000]
    leaders = [
        {
            "symbol": "2222",
            "block_trades": 2,
            "block_volume": 20_000,
            "block_side": "buy",
        }
    ]
    row = classify_tasi_index({"history": _history(closes, volumes), "leaders": leaders})
    assert row is not None
    assert row["state"] == STATE_REBOUND
    assert row["alert"] is False
    assert row["label"] == "ارتداد ونهاية تصحيح ✅"


def test_quiet_history_stays_safe_and_the_lamp_is_off() -> None:
    row = classify_tasi_index({"history": _history([100.0] * 30)})
    assert row is not None
    assert row["state"] == STATE_SAFE
    assert row["alert"] is False


def test_hourly_candles_fold_into_one_riyadh_session() -> None:
    riyadh = timezone(timedelta(hours=3))
    morning = datetime(2026, 10, 8, 10, 0, tzinfo=riyadh).timestamp()
    close = datetime(2026, 10, 8, 15, 0, tzinfo=riyadh).timestamp()
    payload = {
        "chart": {
            "result": [
                {
                    "timestamp": [morning, close],
                    "indicators": {"quote": [{"close": [100.0, 101.5], "volume": [10.0, 15.0]}]},
                }
            ]
        }
    }
    assert parse_tasi_chart(payload) == [("2026-10-08", 101.5, 25.0)]


def test_an_open_session_is_left_out_of_the_volume_history() -> None:
    bars = [("2026-10-07", 100.0, 10.0), ("2026-10-08", 101.0, 1.0)]
    now = datetime(2026, 10, 8, 11, 0, tzinfo=timezone(timedelta(hours=3)))
    assert completed_sessions(bars, now) == [("2026-10-07", 100.0, 10.0)]


def test_stored_net_flow_does_not_count_as_leader_outflow() -> None:
    closes = [100.0] * 24 + [99.0, 98.0]
    leaders = [{"symbol": "2222", "net_flow": -5_000_000}, {"symbol": "1120", "net_flow": -1}]
    row = classify_tasi_index({"history": _history(closes), "leaders": leaders})
    assert row is not None
    assert row["state"] != STATE_CONFIRMED
