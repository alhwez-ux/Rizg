from app.services.close_board import ACCUMULATION, LIQUIDITY, close_session_board
from app.services.signals import is_valid_long_plan


def test_close_board_names_accumulation_and_liquidity() -> None:
    rows = close_session_board(
        [
            {"symbol": "2090", "name": "2090", "last_price": 18.4, "net_flow": 2_500_000, "value_traded": 4_000_000, "change_percent": 1.2},
            {"symbol": "2210", "name": "", "last_price": 12.1, "net_flow": -80_000, "value_traded": 9_000_000, "change_percent": -0.6, "vwap": 12.4},
            {"symbol": "1120", "name": "1120", "last_price": 90, "net_flow": 0, "value_traded": 1_000, "change_percent": 0},
            {"symbol": "1180", "name": "1180", "last_price": 0, "net_flow": 5_000_000, "value_traded": 8_000_000},
        ]
    )
    by_symbol = {row["symbol"]: row for row in rows}
    assert "1180" not in by_symbol
    assert by_symbol["2090"]["name"] == "جبسكو"
    assert by_symbol["2090"]["signal_type"] == ACCUMULATION
    assert by_symbol["2210"]["name"] == "نماء للكيماويات"
    assert by_symbol["2210"]["signal_type"] == LIQUIDITY
    assert by_symbol["2210"]["session_vwap"] == 12.4
    assert by_symbol["2210"]["change_percent"] == -0.6
    assert all(is_valid_long_plan(row["entry_price"], row["target_price"], row["stop_loss"]) for row in rows)
    assert all(row["close_price"] > 0 for row in rows)
