from __future__ import annotations

import json
import struct
from datetime import datetime, timedelta
from pathlib import Path

from app.core.config import Settings
from app.services.tickchart_autosync import TickChartAutoSync
from app.services.uniticker_flatfiles import collect_live_quotes, discover_minute_dir, read_last_bar
from tests.test_tickchart_autosync import _feed

_OLE_EPOCH = datetime(1899, 12, 30)


def _pack(moment: datetime, close: float) -> bytes:
    ole = (moment - _OLE_EPOCH).total_seconds() / 86400.0
    return struct.pack("<d8f", ole, close, close, close, close, 0.0, 0.0, 0.0, 0.0)


def _layout(tmp_path: Path) -> Path:
    cache = tmp_path / "Cache"
    minute = tmp_path / "FlatFiles" / "one_minute" / "tad"
    daily = tmp_path / "FlatFiles" / "daily" / "tad"
    cache.mkdir(parents=True)
    minute.mkdir(parents=True)
    daily.mkdir(parents=True)
    companies = {
        "Companies": [
            {"TickerID": "1120", "ID": "197", "MarketAbrv": "TAD"},
            {"TickerID": "2222", "ID": "1843", "MarketAbrv": "TAD"},
            {"TickerID": "9500", "ID": "9", "MarketAbrv": "TAD"},
            {"TickerID": "1120", "ID": "1", "MarketAbrv": "DFM"},
        ]
    }
    (cache / "CategoriesAndCompaniesData.json").write_text(json.dumps(companies), encoding="utf-8")
    t0 = datetime(2026, 9, 15, 10, 0)
    t1 = datetime(2026, 9, 15, 10, 1)
    (minute / "197.dat").write_bytes(_pack(t0, 65.5) + _pack(t1, 66.05))
    (minute / "1843.dat").write_bytes(_pack(t0, 25.1) + _pack(t1, 25.2))
    day0 = datetime(2026, 9, 14)
    day1 = datetime(2026, 9, 15)
    (daily / "197.dat").write_bytes(_pack(day0, 64.0) + _pack(day1, 65.0))
    return tmp_path


def test_collects_main_market_one_minute_closes(tmp_path: Path, monkeypatch) -> None:
    root = _layout(tmp_path)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    quotes = {row["symbol"]: row for row in collect_live_quotes(root)}
    assert discover_minute_dir(root / "FlatFiles") == root / "FlatFiles" / "one_minute" / "tad"
    assert quotes["1120"]["price"] == 66.05
    assert quotes["2222"]["price"] == 25.2
    assert "9500" not in quotes
    moment, *_rest, close = read_last_bar(root / "FlatFiles" / "one_minute" / "tad" / "197.dat")
    assert round(close, 4) == 66.05
    assert moment.hour == 10 and moment.minute == 1


def test_autosync_ingests_uniticker_flatfiles(tmp_path: Path, monkeypatch) -> None:
    import asyncio

    from app.services import tickchart_autosync as module

    root = _layout(tmp_path)
    monkeypatch.setattr(module, "collect_live_quotes", lambda: collect_live_quotes(root))
    feed = _feed()
    sync = TickChartAutoSync(feed, feed._settings, watch_dirs=[tmp_path / "empty"])
    (tmp_path / "empty").mkdir()
    asyncio.run(sync._scan_flatfiles())
    assert feed.radar_report("1120")["last_price"] == 66.05
    assert sync.status()["last_file"] == "uniticker_1m"


def test_quote_snapshot_writes_last_quotes_once(tmp_path: Path) -> None:
    import asyncio

    from app.services.last_quotes import LastQuoteBook
    from app.services.tickchart_integration import TickChartFeed
    from app.services.liquidity_engine import LiquidityRadarEngine

    class _Broadcaster:
        def __init__(self) -> None:
            self.messages: list = []

        async def broadcast(self, symbol: str, message: dict) -> None:
            self.messages.append((symbol, message))

        def subscribed_symbols(self) -> set[str]:
            return set()

    book = LastQuoteBook(tmp_path / "quotes.json")
    saves = {"n": 0}
    original = book._save_locked

    def _counted() -> None:
        saves["n"] += 1
        original()

    book._save_locked = _counted  # type: ignore[method-assign]
    feed = TickChartFeed(
        LiquidityRadarEngine(),
        _Broadcaster(),
        Settings(_env_file=None, tickchart_enabled=True, tickchart_api_key="test-key", enable_mock_feed=False),
        quotes=book,
    )
    rows = [
        {"type": "quote", "symbol": "1120", "price": 66.0, "time": "2026-09-15T11:00:00"},
        {"type": "quote", "symbol": "2222", "price": 25.2, "time": "2026-09-15T11:00:00"},
        {"type": "quote", "symbol": "2010", "price": 12.4, "time": "2026-09-15T11:00:00"},
    ]
    ingested = asyncio.run(feed.ingest_quote_snapshot(rows))
    assert ingested == 3
    assert saves["n"] == 1
    assert feed.radar_report("1120")["last_price"] == 66.0
    assert feed.status()["quote_mode"] == "live"

