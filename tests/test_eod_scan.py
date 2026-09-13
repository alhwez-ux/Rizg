from __future__ import annotations

from app.services.eod_scan import KIND_BOUNCE, KIND_MOMENTUM, evaluate_close_setup, scan_end_of_day


def test_eod_scan_detects_close_bounce_and_momentum() -> None:
    rows = scan_end_of_day(
        [
            {
                "symbol": "2222",
                "name": "أرامكو السعودية",
                "last_price": 28.4,
                "session_low": 26.9,
                "session_high": 28.5,
                "change_percent": 0.8,
                "volume_ratio": 1.6,
                "mfi": 38,
                "net_flow": 12_000,
            },
            {
                "symbol": "1120",
                "name": "الراجحي",
                "last_price": 96.4,
                "session_low": 95.8,
                "session_high": 96.4,
                "change_percent": 1.4,
                "volume_ratio": 2.1,
                "institutional_mfi": 64,
                "net_flow": 80_000,
            },
            {
                "symbol": "4030",
                "name": "البحري",
                "last_price": 24.9,
                "volume": 1000,
                "volume_ratio": 0.8,
                "change_percent": -0.4,
            },
        ]
    )
    kinds = {row["symbol"]: row["signal_kind"] for row in rows}
    assert kinds["2222"] == KIND_BOUNCE
    assert kinds["1120"] == KIND_MOMENTUM
    assert "4030" not in kinds
    assert all(row["scan_mode"] == "end_of_day" for row in rows)
    assert all(row["horizon"] == "next_session" for row in rows)
    assert all("ارتقاب" in row["reason"] or "الغد" in row["reason"] for row in rows)


def test_eod_scan_uses_closing_volume_when_ticks_are_absent() -> None:
    rows = scan_end_of_day(
        [
            {"symbol": "1120", "last_price": 96.4, "volume": 8_200_000},
            {"symbol": "1180", "last_price": 38.1, "volume": 900_000},
            {"symbol": "1010", "last_price": 27.4, "volume": 800_000},
        ]
    )
    assert rows
    assert rows[0]["symbol"] == "1120"
    assert rows[0]["close_price"] == 96.4
    assert rows[0]["signal_kind"] == KIND_MOMENTUM


def test_eod_scan_skips_symbols_without_a_recorded_close() -> None:
    assert evaluate_close_setup({"symbol": "2010", "volume": 5_000_000}, typical_volume=1_000_000) is None
    assert scan_end_of_day([{"symbol": "2010", "volume": 5_000_000}]) == []
