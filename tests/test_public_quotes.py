from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx

from app.core.config import Settings
from app.services.last_quotes import LastQuoteBook
from app.services.liquidity_engine import LiquidityRadarEngine
from app.services.tickchart_integration import TickChartFeed


class _Broadcaster:
    async def broadcast(self, symbol: str, message: dict) -> None:
        del symbol, message

    def subscribed_symbols(self) -> set[str]:
        return set()


def _feed(tmp_path: Path) -> TickChartFeed:
    settings = Settings(
        _env_file=None,
        tickchart_api_key="test-key",
        sahmk_api_key="test-key",
        enable_mock_feed=False,
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={})))
    return TickChartFeed(
        LiquidityRadarEngine(),
        _Broadcaster(),
        settings,
        client=client,
        quotes=LastQuoteBook(tmp_path / "quotes.json"),
    )


def test_public_quotes_fill_price_and_session_value(tmp_path: Path) -> None:
    feed = _feed(tmp_path)

    def fetcher(symbols, sessions=10):
        del symbols, sessions
        return (
            [{"symbol": "1120", "date": "2026-09-28", "close": 90.0, "volume": 800_000}],
            [
                {
                    "symbol": "1120",
                    "last_price": 96.5,
                    "volume": 1_000_000,
                    "change_percent": 1.5,
                    "net_flow": 1_500_000,
                    "session_date": date(2026, 9, 29),
                }
            ],
        )

    applied = feed.ensure_public_quotes(fetcher=fetcher)
    assert applied == 1
    assert feed._quotes.price("1120") == 96.5
    row = next(item for item in feed.market_rows() if item["symbol"] == "1120")
    assert row["last_price"] == 96.5
    assert row["value_traded"] == 96.5 * 1_000_000
    assert row["net_flow"] == 1_500_000
    tape = next(item for item in feed.quote_tape() if item["symbol"] == "1120")
    assert tape["last_price"] == 96.5
    assert tape["value_traded"] > 0


def test_newer_daily_bar_replaces_a_stale_print(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("app.services.tickchart_integration.session_phase", lambda moment=None: "closed")
    feed = _feed(tmp_path)
    feed._quotes.apply_closes(
        [{"symbol": "4263", "last_price": 171.5, "session_date": date(2026, 9, 14), "volume": 100}]
    )
    feed._quotes.merge_history(
        [{"symbol": "4263", "date": "2026-10-01", "close": 167.4, "volume": 50_000}],
        keep_today=False,
    )
    feed._engine.process_trade("4263", Decimal("171.50"), Decimal("10"))
    assert feed._quotes.official_close("4263") == 167.4
    report = feed.radar_report("4263")
    assert report["last_price"] == 167.4
    assert report["quote_mode"] == "last_close"
    assert report["entry"] is False


def test_dated_session_close_survives_a_later_print(tmp_path: Path, monkeypatch) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    tuesday = datetime(2026, 10, 6, 0, 31, tzinfo=ZoneInfo("Asia/Riyadh"))
    monkeypatch.setattr("app.services.last_quotes.now_riyadh", lambda moment=None: tuesday)
    monkeypatch.setattr("app.services.tasi_clock.now_riyadh", lambda moment=None: tuesday)
    feed = _feed(tmp_path)
    feed._quotes.apply_closes(
        [{"symbol": "4263", "last_price": 173.0, "session_date": date(2026, 10, 5), "volume": 269_236}]
    )
    feed._quotes.apply_closes([{"symbol": "4263", "last_price": 169.0, "volume": 10}])
    assert feed._quotes.price("4263") == 173.0
    feed._quotes.apply_closes(
        [{"symbol": "4263", "last_price": 169.0, "session_date": date(2026, 10, 6), "volume": 10}]
    )
    assert feed._quotes.official_close("4263") == 173.0
    monkeypatch.setattr("app.services.tickchart_integration.session_phase", lambda moment=None: "closed")
    feed._engine.process_trade("4263", Decimal("169"), Decimal("10"))
    assert feed.radar_report("4263")["last_price"] == 173.0


def test_open_session_uses_todays_price_not_the_prior_close(tmp_path: Path, monkeypatch) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    tuesday = datetime(2026, 10, 6, 12, 48, tzinfo=ZoneInfo("Asia/Riyadh"))
    monkeypatch.setattr("app.services.last_quotes.now_riyadh", lambda moment=None: tuesday)
    monkeypatch.setattr("app.services.tasi_clock.now_riyadh", lambda moment=None: tuesday)
    monkeypatch.setattr("app.services.tickchart_integration.session_phase", lambda moment=None: "open")
    feed = _feed(tmp_path)
    feed._quotes.apply_closes(
        [{"symbol": "1140", "last_price": 23.42, "session_date": date(2026, 10, 5), "volume": 1_000}]
    )
    feed._quotes.apply_closes(
        [{"symbol": "1140", "last_price": 23.60, "session_date": date(2026, 10, 6), "volume": 2_000}]
    )
    feed._quotes.apply_closes(
        [{"symbol": "1831", "last_price": 4.03, "session_date": date(2026, 10, 5), "volume": 1_000}]
    )
    feed._quotes.apply_closes(
        [{"symbol": "1831", "last_price": 4.07, "session_date": date(2026, 10, 6), "volume": 2_000}]
    )
    bilad = feed.radar_report("1140")
    maharah = feed.radar_report("1831")
    assert bilad["last_price"] == 23.60
    assert maharah["last_price"] == 4.07
    tape = {row["symbol"]: row["last_price"] for row in feed.quote_tape()}
    assert tape["1140"] == 23.60
    assert tape["1831"] == 4.07
    assert feed._stored_market_row("1140")["last_price"] == 23.60
    assert feed._quotes.official_close("1140") == 23.42
    assert feed._quotes.official_close("1831") == 4.03
    monkeypatch.setattr("app.services.last_quotes.session_phase", lambda moment=None: "closed")
    assert feed._quotes.display_price("1140") == 23.42


def test_public_quote_refresh_reaches_later_symbols(tmp_path: Path) -> None:
    feed = _feed(tmp_path)
    seen: list[list[str]] = []

    def fetcher(symbols, sessions=10):
        del sessions
        seen.append(list(symbols))
        return [], []

    for _ in range(12):
        feed.ensure_public_quotes(fetcher=fetcher)
    assert any("4263" in batch for batch in seen)
    assert seen[0] != seen[1]
