from __future__ import annotations

import asyncio
import random
from types import SimpleNamespace

from starlette.websockets import WebSocketState

from app.core.config import Settings
from app.services.broadcaster import ConnectionManager
from app.services.liquidity_engine import LiquidityEngine
from app.services.tick_feed import MockTickFeed


class FakeWebSocket:
    def __init__(self, *, fail_send: bool = False) -> None:
        self.client_state = WebSocketState.CONNECTING
        self.client = SimpleNamespace(host="127.0.0.1", port=9)
        self.messages: list[dict] = []
        self.fail_send = fail_send

    async def accept(self) -> None:
        self.client_state = WebSocketState.CONNECTED

    async def send_json(self, payload: dict) -> None:
        if self.fail_send:
            raise RuntimeError("broken pipe")
        if self.client_state != WebSocketState.CONNECTED:
            raise RuntimeError("socket is closed")
        self.messages.append(payload)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.client_state = WebSocketState.DISCONNECTED


def test_broadcast_reaches_all_subscribers_for_a_symbol() -> None:
    async def scenario() -> None:
        manager = ConnectionManager()
        first = FakeWebSocket()
        second = FakeWebSocket()
        other = FakeWebSocket()

        await manager.connect(first, "AAPL")
        await manager.connect(second, "AAPL")
        await manager.connect(other, "MSFT")

        payload = {"type": "liquidity", "symbol": "AAPL", "net_flow": "10"}
        await manager.broadcast("AAPL", payload)

        assert first.messages == [payload]
        assert second.messages == [payload]
        assert other.messages == []
        assert manager.subscriber_count("AAPL") == 2

    asyncio.run(scenario())


def test_failed_client_is_dropped_without_blocking_others() -> None:
    async def scenario() -> None:
        manager = ConnectionManager()
        healthy = FakeWebSocket()
        broken = FakeWebSocket(fail_send=True)

        await manager.connect(healthy, "AAPL")
        await manager.connect(broken, "AAPL")
        await manager.broadcast("AAPL", {"type": "liquidity", "symbol": "AAPL"})

        assert healthy.messages == [{"type": "liquidity", "symbol": "AAPL"}]
        assert manager.subscriber_count("AAPL") == 1
        assert manager.subscriber_count() == 1

    asyncio.run(scenario())


def test_disconnect_stops_further_broadcasts() -> None:
    async def scenario() -> None:
        manager = ConnectionManager()
        client = FakeWebSocket()
        await manager.connect(client, "TSLA")
        await manager.disconnect(client)
        await manager.broadcast("TSLA", {"type": "liquidity", "symbol": "TSLA"})

        assert client.messages == []
        assert manager.subscriber_count("TSLA") == 0

    asyncio.run(scenario())


def test_mock_feed_emits_net_flow_and_volumes() -> None:
    async def scenario() -> None:
        manager = ConnectionManager()
        engine = LiquidityEngine()
        client = FakeWebSocket()
        settings = Settings(mock_feed_symbols=["AAPL"], mock_feed_interval_seconds=0.05)
        feed = MockTickFeed(engine, manager, settings, rng=random.Random(7))

        await manager.connect(client, "AAPL")
        first = await feed.emit_symbol("AAPL")
        second = await feed.emit_symbol("AAPL")

        assert first is not None
        assert second is not None
        assert second.symbol == "AAPL"
        assert "net_flow" in client.messages[-1]
        assert "buy_volume" in client.messages[-1]
        assert "sell_volume" in client.messages[-1]
        session = engine.get_session("AAPL")
        assert session.trade_count == 2
        assert session.net_flow == second.net_flow

    asyncio.run(scenario())
