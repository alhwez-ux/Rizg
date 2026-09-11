from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from starlette.websockets import WebSocketState

from app.core.config import Settings
from app.services.broadcaster import ConnectionManager
from app.services.liquidity_engine import LiquidityEngine
from app.services.sahmk_feed import SahmkTradeFeed, parse_trade_event


class FakeWebSocket:
    def __init__(self) -> None:
        self.client_state = WebSocketState.CONNECTING
        self.client = SimpleNamespace(host="127.0.0.1", port=9)
        self.messages: list[dict] = []

    async def accept(self) -> None:
        self.client_state = WebSocketState.CONNECTED

    async def send_json(self, payload: dict) -> None:
        self.messages.append(payload)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.client_state = WebSocketState.DISCONNECTED


def _feed() -> tuple[SahmkTradeFeed, LiquidityEngine, FakeWebSocket]:
    engine = LiquidityEngine()
    manager = ConnectionManager()
    client = FakeWebSocket()
    settings = Settings(
        _env_file=None,
        sahmk_api_key="test-key",
        sahmk_symbols=["4030"],
        telegram_bot_token="",
        telegram_chat_id="",
        enable_mock_feed=False,
    )
    feed = SahmkTradeFeed(engine, manager, settings)

    async def connect() -> None:
        await manager.connect(client, "4030")

    asyncio.run(connect())
    return feed, engine, client


def test_parse_trade_event_reads_price_and_quantity() -> None:
    parsed = parse_trade_event(
        {
            "type": "trade",
            "symbol": "4030",
            "event_time": "2026-09-11T08:00:00+00:00",
            "price": 28.5,
            "quantity": 1000,
            "value": 28500.0,
        }
    )
    assert parsed is not None
    symbol, price, volume, timestamp, _key = parsed
    assert symbol == "4030"
    assert price == 28.5
    assert volume == 1000
    assert timestamp == datetime(2026, 9, 11, 8, 0, tzinfo=timezone.utc)


def test_live_trade_goes_through_liquidity_engine() -> None:
    feed, engine, client = _feed()

    async def run() -> None:
        await feed.ingest_message(
            {
                "type": "trade",
                "symbol": "4030",
                "event_time": "2026-09-11T08:00:01+00:00",
                "price": 24.80,
                "quantity": 100,
            }
        )
        await feed.ingest_message(
            {
                "type": "trade",
                "symbol": "4030",
                "event_time": "2026-09-11T08:00:02+00:00",
                "price": 24.82,
                "quantity": 50,
            }
        )

    asyncio.run(run())
    session = engine.get_session("4030")
    assert session.trade_count == 2
    assert session.buy_volume == 50
    assert client.messages[-1]["symbol"] == "4030"
    assert "net_flow" in client.messages[-1]


def test_snapshot_is_ingested_oldest_first_and_duplicates_are_skipped() -> None:
    feed, engine, _client = _feed()

    async def run() -> int:
        count = await feed.ingest_message(
            {
                "type": "trades_snapshot",
                "symbol": "4030",
                "events": [
                    {
                        "event_time": "2026-09-11T08:00:02+00:00",
                        "price": 24.84,
                        "quantity": 10,
                    },
                    {
                        "event_time": "2026-09-11T08:00:01+00:00",
                        "price": 24.80,
                        "quantity": 20,
                    },
                ],
            }
        )
        duplicate = await feed.ingest_message(
            {
                "type": "trade",
                "symbol": "4030",
                "event_time": "2026-09-11T08:00:02+00:00",
                "price": 24.84,
                "quantity": 10,
            }
        )
        return count + duplicate

    ingested = asyncio.run(run())
    assert ingested == 2
    assert engine.get_session("4030").trade_count == 2


def test_delayed_quote_volume_increase_becomes_a_print() -> None:
    feed, engine, client = _feed()

    async def run() -> None:
        first = await feed.ingest_message(
            {
                "symbol": "4030",
                "price": 24.80,
                "volume": 1000,
                "updated_at": "2026-09-11T08:00:00+00:00",
                "is_delayed": True,
            }
        )
        second = await feed.ingest_message(
            {
                "symbol": "4030",
                "price": 24.85,
                "volume": 1300,
                "updated_at": "2026-09-11T08:15:00+00:00",
                "is_delayed": True,
            }
        )
        assert first == 0
        assert second == 1

    asyncio.run(run())
    session = engine.get_session("4030")
    assert session.trade_count == 1
    assert session.last_price == Decimal("24.85")
    assert Decimal(str(client.messages[-1]["volume"])) == Decimal("300")
