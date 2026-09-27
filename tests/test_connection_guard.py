from __future__ import annotations

import asyncio

import pytest

from app.core.config import Settings
from app.services.broadcaster import ConnectionManager
from app.services.connection_guard import ConnectionGuard, is_terminal_feed_error
from app.services.liquidity_engine import LiquidityRadarEngine
from app.services.tickchart_integration import TickChartFeed


class _AuthError(Exception):
    status_code = 403


def test_guard_stays_disconnected_without_a_client() -> None:
    guard = ConnectionGuard(plan_active=True)
    assert guard.healthy is True
    assert guard.plan_active is True
    assert guard.is_connected is False
    assert guard.snapshot()["clients"] == 0


def test_heartbeat_marks_connected_until_plan_is_inactive() -> None:
    guard = ConnectionGuard(plan_active=True)
    guard.beat("browser-1")
    guard.beat("another-tab")
    assert guard.is_connected is True
    assert guard.client_count() == 1
    assert guard.snapshot()["owner"] == "owner"
    guard.mark_plan_inactive("Plan is inactive")
    assert guard.plan_active is False
    assert guard.is_connected is False
    guard.beat("browser-1")
    assert guard.client_count() == 0


def test_terminal_errors_cover_plan_and_auth() -> None:
    assert is_terminal_feed_error(RuntimeError("Plan is inactive"))
    assert is_terminal_feed_error(_AuthError("rejected"))
    assert is_terminal_feed_error(ConnectionError("temporary network")) is False


def test_websocket_stops_after_inactive_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def connect(*_args, **_kwargs):
        calls["n"] += 1
        raise RuntimeError("Plan is inactive")

    monkeypatch.setattr("app.services.tickchart_integration.websockets.connect", connect)
    feed = _feed()
    guard = ConnectionGuard(plan_active=True)
    guard.beat("browser-1")
    feed.bind_connection_guard(guard)
    feed._running = True

    asyncio.run(feed._run_ws("wss://api.sahmk.sa/ws/v1/market/trades/", "trades"))

    assert calls["n"] == 1
    assert guard.plan_active is False
    assert feed._ws_pause_reason
    assert "inactive" in feed._ws_pause_reason.lower()


def test_websocket_stops_after_five_transient_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def connect(*_args, **_kwargs):
        calls["n"] += 1
        raise ConnectionError("reset")

    async def fast_sleep(_delay: float = 0) -> None:
        return None

    monkeypatch.setattr("app.services.tickchart_integration.websockets.connect", connect)
    monkeypatch.setattr("app.services.tickchart_integration.asyncio.sleep", fast_sleep)
    feed = _feed()
    guard = ConnectionGuard(plan_active=True)
    guard.beat("browser-1")
    feed.bind_connection_guard(guard)
    feed._running = True

    asyncio.run(feed._run_ws("wss://api.sahmk.sa/ws/v1/market/trades/", "trades"))

    assert calls["n"] == 5
    assert guard.plan_active is True
    assert feed._ws_pause_reason == "retries_exhausted"
    assert feed._feed_mode == "cache"


def test_pull_session_uses_cache_when_disconnected(tmp_path) -> None:
    from app.services.last_quotes import LastQuoteBook

    quotes = LastQuoteBook(path=tmp_path / "quotes.json")
    quotes.apply_closes([{"symbol": "2222", "last_price": 25.5}])
    feed = _feed(quotes=quotes)
    guard = ConnectionGuard(plan_active=True)
    feed.bind_connection_guard(guard)

    payload = asyncio.run(feed.pull_session())

    assert payload["skipped"] == "disconnected"
    assert payload["delayed_closes"] == 0
    assert payload["feed_mode"] == "cache"
    assert payload["quote_mode"] == "last_close"


def test_scheduler_skips_scan_when_disconnected() -> None:
    from app.services.tasi_scheduler import TasiMarketScheduler

    scheduler = TasiMarketScheduler(Settings(_env_file=None, tasi_scheduler_enabled=False), enable_scheduler=False)
    scheduler.bind_connection_guard(ConnectionGuard(plan_active=True))
    payload = asyncio.run(scheduler.scan_session())
    assert payload["skipped"] is True
    assert payload["reason"] == "disconnected"


def test_presence_tracks_websocket_clients() -> None:
    guard = ConnectionGuard(plan_active=True)
    manager = ConnectionManager()
    manager.bind_presence(guard)

    class _Socket:
        pass

    socket = _Socket()
    manager._subscriptions[socket] = {"2222"}
    guard.note_websocket(1)
    assert guard.is_connected is True
    asyncio.run(manager.disconnect(socket))  # type: ignore[arg-type]
    assert guard.client_count() == 0
    assert guard.is_connected is False


def _feed(**kwargs) -> TickChartFeed:
    settings = Settings(
        _env_file=None,
        tickchart_api_key="test-key",
        sahmk_api_key="test-key",
        enable_mock_feed=False,
    )
    return TickChartFeed(LiquidityRadarEngine(), ConnectionManager(), settings, **kwargs)
