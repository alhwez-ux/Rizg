from datetime import date

from app.services.dividends import active_dividends
from app.services.shariah import classify_shariah, classified_status, screen_universe, shariah_label
from app.services.signals import is_valid_long_plan
from app.services.tasi_clock import add_tasi_calendar_days, next_tasi_session_date


def test_classify_shariah_ratio_thresholds() -> None:
    assert classify_shariah(core_prohibited=True) == "PROHIBITED"
    assert classify_shariah(impure_income_ratio=0.05, debt_ratio=0.10) == "MIXED"
    assert classify_shariah(impure_income_ratio=0.051, debt_ratio=0.10) == "PROHIBITED"
    assert classify_shariah(debt_ratio=0.33, impure_income_ratio=0.01) == "MIXED"
    assert classify_shariah(debt_ratio=0.34, impure_income_ratio=0.01) == "PROHIBITED"
    assert classify_shariah(debt_ratio=0.04, impure_income_ratio=0.0) == "PURE"
    assert classify_shariah(debt_ratio=0.19, impure_income_ratio=0.021) == "MIXED"


def test_tasi_universe_status_flags() -> None:
    assert classified_status("1120") == "PURE"
    assert shariah_label("1120") == "نقي"
    assert classified_status("2222") == "MIXED"
    assert shariah_label("2222") == "مختلط"
    assert classified_status("1010") == "PROHIBITED"
    assert shariah_label("1010") == "محرم"


def test_screen_universe_hides_prohibited_and_pure_only() -> None:
    all_rows = screen_universe(pure_only=False)
    symbols = {str(row["symbol"]) for row in all_rows}
    assert "1120" in symbols
    assert "2222" in symbols
    assert "1010" not in symbols
    assert all(row["status"] != "PROHIBITED" for row in all_rows)

    pure_rows = screen_universe(pure_only=True)
    assert pure_rows
    assert all(row["status"] == "PURE" for row in pure_rows)
    assert {str(row["symbol"]) for row in pure_rows} <= symbols


def test_active_dividends_drops_past_eligibility_and_haram() -> None:
    today = date(2026, 9, 22)  # Tuesday — TASI weekday
    rows = active_dividends(today=today, pure_only=False)
    assert rows
    assert all(row["eligibility_date"] >= today.isoformat() for row in rows)
    assert all(row["shariah_status"] != "PROHIBITED" for row in rows)
    assert "1010" not in {row["symbol"] for row in rows}

    expired = [row for row in rows if row["symbol"] == "2010"]
    assert expired == []

    pure = active_dividends(today=today, pure_only=True)
    assert all(row["shariah_status"] == "PURE" for row in pure)


def test_dividend_dates_land_on_tasi_weekdays() -> None:
    friday = date(2026, 9, 25)
    sunday = next_tasi_session_date(friday)
    assert sunday == date(2026, 9, 27)
    assert add_tasi_calendar_days(date(2026, 9, 24), 1) == date(2026, 9, 27)
    assert add_tasi_calendar_days(date(2026, 9, 27), -1) == date(2026, 9, 24)


def test_long_plan_geometry_stays_target_above_entry_above_stop() -> None:
    assert is_valid_long_plan("25.70", "26.80", "24.90") is True
    assert is_valid_long_plan("25.70", "25.45", "26.01") is False
    assert is_valid_long_plan("25.70", "26.80", None) is False
