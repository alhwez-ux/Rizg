from app.services.correction_radar import (
    SIGNAL_APPROACH,
    SIGNAL_REBOUND,
    classify_correction,
    scan_correction_radar,
)


def _history(closes: list[float], volumes: list[float]) -> list[dict]:
    return [
        {"date": f"2026-08-{index + 1:02d}", "close": close, "volume": volume}
        for index, (close, volume) in enumerate(zip(closes, volumes))
    ]


def test_approach_needs_fading_volume_and_negative_institutional_flow() -> None:
    row = classify_correction(
        {
            "symbol": "1120",
            "last_price": 13,
            "history": _history([10, 11, 12, 13], [120_000, 100_000, 80_000, 60_000]),
            "institutional_inflow": 20_000,
            "institutional_outflow": 90_000,
        }
    )
    assert row is not None
    assert row["signal"] == SIGNAL_APPROACH
    assert row["signal_kind"] == "approach"
    assert row["pillars"] >= 2
    assert "حجم متناقص على 3 جلسات صاعدة" in row["reasons"]
    assert "صافي تدفق مؤسسي سلبي" in row["reasons"]


def test_volume_fade_alone_stays_off_the_board() -> None:
    assert (
        classify_correction(
            {
                "symbol": "1120",
                "last_price": 13,
                "history": _history([10, 11, 12, 13], [120_000, 100_000, 80_000, 60_000]),
            }
        )
        is None
    )


def test_stored_net_flow_is_not_treated_as_institutional() -> None:
    assert (
        classify_correction(
            {
                "symbol": "1120",
                "last_price": 13,
                "net_flow": -5_000_000,
                "history": _history([10, 11, 12, 13], [120_000, 100_000, 80_000, 60_000]),
            }
        )
        is None
    )


def test_missing_mfi_does_not_count_as_divergence() -> None:
    row = classify_correction(
        {
            "symbol": "2222",
            "last_price": 10.0,
            "history": _history(
                [9.0, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 10.0],
                [200_000, 180_000, 160_000, 140_000, 120_000, 100_000, 90_000, 80_000, 70_000, 60_000],
            ),
        }
    )
    assert row is not None
    assert row["signal_kind"] == "approach"
    assert "مؤشر السيولة المؤسسية ضعيف والسعر صاعد" not in row["reasons"]
    assert "السعر عند أعلى إغلاق يومي حديث" in row["reasons"]


def test_print_sized_volume_does_not_fake_a_fade() -> None:
    assert (
        classify_correction(
            {
                "symbol": "2222",
                "last_price": 25.8,
                "history": _history([24, 25, 25.5, 25.8], [13_000_000, 12_000_000, 11_000_000, 200]),
                "institutional_inflow": 1,
                "institutional_outflow": 9,
            }
        )
        is None
    )


def test_rebound_from_support_and_buy_blocks() -> None:
    closes = [12, 11.5, 11, 10.8, 10.5, 10.4, 10.3, 10.2, 10.1, 10.05]
    volumes = [80_000] * 10
    row = classify_correction(
        {
            "symbol": "2010",
            "last_price": 10.05,
            "history": _history(closes, volumes),
            "block_trades": 2,
            "block_volume": 25_000,
            "block_side": "buy",
        }
    )
    assert row is not None
    assert row["signal"] == SIGNAL_REBOUND
    assert "كتل شرائية عند مستويات منخفضة" in row["reasons"]
    assert "السعر عند أدنى إغلاق يومي حديث" in row["reasons"]


def test_buy_blocks_at_the_high_are_not_a_rebound() -> None:
    closes = [10, 10.2, 10.4, 10.6, 10.8, 11, 11.2, 11.4, 11.6, 12]
    assert (
        classify_correction(
            {
                "symbol": "2010",
                "last_price": 12,
                "history": _history(closes, [50_000] * 10),
                "block_trades": 3,
                "block_volume": 40_000,
                "block_side": "buy",
            }
        )
        is None
    )


def test_block_without_volume_does_not_count() -> None:
    closes = [12, 11.5, 11, 10.8, 10.5, 10.4, 10.3, 10.2, 10.1, 10.05]
    assert (
        classify_correction(
            {
                "symbol": "2010",
                "last_price": 10.05,
                "history": _history(closes, [80_000] * 10),
                "block_trades": 4,
                "block_volume": 0,
                "block_side": "buy",
            }
        )
        is None
    )


def test_atr_touch_and_volume_surge_mark_the_rebound() -> None:
    closes = [8.0, 10.0, 10.05, 10.0, 10.05, 10.0, 10.05, 10.0, 10.05, 10.0, 9.9, 9.91]
    volumes = [100_000] * 11 + [180_000]
    row = classify_correction(
        {
            "symbol": "4030",
            "last_price": 9.91,
            "history": _history(closes, volumes),
        }
    )
    assert row is not None
    assert row["signal_kind"] == "rebound"
    assert "ملامسة الحد السفلي لتذبذب الإغلاق" in row["reasons"]
    assert "حجم أعلى من متوسط 10 جلسات وإغلاق إيجابي" in row["reasons"]


def test_equal_opposite_alerts_are_withheld() -> None:
    closes = [10, 10, 10, 10, 10, 10, 10, 10, 11, 12, 14]
    volumes = [50_000, 50_000, 50_000, 50_000, 50_000, 50_000, 50_000, 50_000, 300_000, 200_000, 150_000]
    row = classify_correction(
        {
            "symbol": "1120",
            "last_price": 14,
            "history": _history(closes, volumes),
            "institutional_inflow": 5,
            "institutional_outflow": 20,
            "session_vwap": 13.85,
            "session_low": 12,
        }
    )
    assert row is None


def test_scan_sorts_richer_alerts_first() -> None:
    payload = scan_correction_radar(
        snapshots=[
            {
                "symbol": "2010",
                "last_price": 10.05,
                "history": _history(
                    [12, 11.5, 11, 10.8, 10.5, 10.4, 10.3, 10.2, 10.1, 10.05],
                    [80_000] * 10,
                ),
                "block_trades": 1,
                "block_volume": 12_000,
                "block_side": "buy",
            },
            {
                "symbol": "1120",
                "last_price": 13,
                "history": _history([10, 11, 12, 13], [120_000, 100_000, 80_000, 60_000]),
                "institutional_inflow": 1,
                "institutional_outflow": 8,
                "block_trades": 2,
                "block_volume": 9_000,
                "block_side": "sell",
            },
        ]
    )
    assert payload["approach_count"] == 1
    assert payload["rebound_count"] == 1
    assert payload["data"][0]["symbol"] == "1120"
    assert payload["data"][0]["pillars"] >= payload["data"][1]["pillars"]
