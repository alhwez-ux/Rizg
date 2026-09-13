from __future__ import annotations

import asyncio
from decimal import Decimal

from app.core.config import Settings
from app.services.liquidity_engine import LiquidityRadarEngine
from app.services.tickchart_integration import TickChartFeed, parse_depth, parse_tick


class _Broadcaster:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict]] = []

    async def broadcast(self, symbol: str, message: dict) -> None:
        self.messages.append((symbol, message))

    def subscribed_symbols(self) -> set[str]:
        return set()


def test_parse_tick_from_sahmk_trade() -> None:
    parsed = parse_tick(
        {
            "type": "trade",
            "symbol": "2222",
            "event_time": "2026-09-13T10:01:00+03:00",
            "price": 25.72,
            "quantity": 1000,
            "value": 25720.0,
        }
    )
    assert parsed is not None
    symbol, price, volume, _timestamp, _key = parsed
    assert symbol == "2222"
    assert price == Decimal("25.72")
    assert volume == Decimal("1000")


def test_parse_depth_from_sahmk_snapshot() -> None:
    parsed = parse_depth(
        {
            "type": "depth_snapshot",
            "symbol": "2222",
            "best_bid": 25.70,
            "best_ask": 25.74,
            "bids": [{"price": 25.70, "quantity": 5000}],
            "asks": [{"price": 25.74, "quantity": 12000}],
        }
    )
    assert parsed is not None
    assert parsed["symbol"] == "2222"
    assert parsed["bid"] == Decimal("25.70")
    assert parsed["ask"] == Decimal("25.74")
    assert parsed["bid_size"] == Decimal("5000")
    assert parsed["ask_size"] == Decimal("12000")


def test_tickchart_feed_builds_radar_from_ticks_and_book() -> None:
    settings = Settings(
        _env_file=None,
        tickchart_api_key="test-key",
        sahmk_api_key="test-key",
        enable_mock_feed=False,
    )
    engine = LiquidityRadarEngine()
    feed = TickChartFeed(engine, _Broadcaster(), settings)
    ingested = asyncio.run(
        feed.ingest_message(
            {
                "ticks": [
                    {"symbol": "2222", "price": 25.70, "quantity": 200, "event_time": "2026-09-13T10:00:01+03:00"},
                    {"symbol": "2222", "price": 25.72, "quantity": 800, "event_time": "2026-09-13T10:00:02+03:00"},
                ]
            }
        )
    )
    asyncio.run(
        feed.ingest_message(
            {
                "type": "depth_snapshot",
                "symbol": "2222",
                "best_bid": 25.70,
                "best_ask": 25.74,
                "bids": [{"price": 25.70, "quantity": 400}],
                "asks": [{"price": 25.74, "quantity": 9000}],
            }
        )
    )
    report = feed.radar_report("2222")
    assert ingested == 2
    assert report["last_price"] == 25.72
    assert report["bid"] == 25.7
    assert report["ask"] == 25.74
    assert report["source"] == "TickChart"
    assert "institutional_mfi" in report or report["last_price"] == 25.72
