"""TickChart live ticks, Level-2 depth, block trades, and institutional MFI."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
import websockets

from app.core.config import Settings
from app.models.trade import LiquidityStreamMessage
from app.services.alerts import AlertService
from app.services.broadcaster import ConnectionManager
from app.services.liquidity_engine import LiquidityRadarEngine
from app.services.screener import ScreenerService
from app.services.shariah import company_name_for, is_prohibited, sector_for
from app.services.tasi_clock import now_riyadh, phase_label, session_phase
from app.services.tickchart_tape import SymbolTape, parse_book_levels
from app.services.last_quotes import LastQuoteBook
from app.services.watchlist import WatchlistService

DEFAULT_TICKCHART_SYMBOLS = [
    "2222",
    "1120",
    "1180",
    "7010",
    "1150",
    "1211",
    "2010",
    "1010",
    "2082",
    "2280",
    "4190",
    "7203",
    "4030",
    "1140",
]

logger = logging.getLogger(__name__)

_SEEN_LIMIT = 4_000
_DEFAULT_TRADES_WS = "wss://api.sahmk.sa/ws/v1/market/trades/"
_DEFAULT_DEPTH_WS = "wss://api.sahmk.sa/ws/v1/market/depth/"
_PLACEHOLDER_KEYS = frozenset(
    {
        "",
        "your_api_key",
        "your_tickchart_api_key",
        "changeme",
        "ضع_مفتاح_تكرتشارت_هنا",
    }
)
_BLOCKED_REST_HOSTS = (
    "api.sahmk.sa",
    "api.sahmcapital.com",
    "sahmk.sa",
    "sahmcapital.com",
)


class TickChartFeed:
    """Live TickChart adapter: ticks + depth → liquidity engine → WebSocket clients."""

    def __init__(
        self,
        engine: LiquidityRadarEngine,
        manager: ConnectionManager,
        settings: Settings,
        *,
        alerts: AlertService | None = None,
        watchlist: WatchlistService | None = None,
        screener: ScreenerService | None = None,
        client: httpx.AsyncClient | None = None,
        quotes: LastQuoteBook | None = None,
    ) -> None:
        self._engine = engine
        self._manager = manager
        self._alerts = alerts
        self._watchlist = watchlist
        self._screener = screener
        self._settings = settings
        self._api_key = _resolve_tickchart_key(settings)
        self._rest_url = _sanitize_rest_url(settings.tickchart_rest_url)
        self._trades_ws = (settings.tickchart_trades_ws or "").strip() or _DEFAULT_TRADES_WS
        self._depth_ws = (settings.tickchart_depth_ws or "").strip() or _DEFAULT_DEPTH_WS
        self._ping_seconds = settings.tickchart_ping_seconds
        self._depth_levels = settings.tickchart_depth_levels
        self._poll_seconds = settings.tickchart_poll_seconds
        self._block_floor = Decimal(str(getattr(settings, "tickchart_block_value", 500000) or 500000))
        self._configured_symbols = _clean_symbols(settings.tickchart_symbols) or list(DEFAULT_TICKCHART_SYMBOLS)
        self._client = client
        self._owns_client = client is None
        self._running = False
        self._tasks: list[asyncio.Task[None]] = []
        self._seen: deque[str] = deque()
        self._seen_set: set[str] = set()
        self._last_trade_time: dict[str, str] = {}
        self._trades_live = False
        self._depth_live = False
        self._ws_lock = asyncio.Lock()
        self._trades_socket: Any = None
        self._depth_socket: Any = None
        self._subscribed: set[str] = set()
        self._tapes: dict[str, SymbolTape] = {}
        self._autosync: Any = None
        self._last_cloud_ingest: str | None = None
        self._last_cloud_count: int = 0
        self._quotes = quotes or LastQuoteBook()
        self._ranking: Any = None

    @property
    def enabled(self) -> bool:
        return bool(self._settings.tickchart_enabled)

    @property
    def connected(self) -> bool:
        autosync = getattr(self, "_autosync", None)
        return (
            self._trades_live
            or self._depth_live
            or bool(self._last_cloud_ingest)
            or bool(autosync and getattr(autosync, "connected", False))
        )

    def bind_ranking_store(self, store: Any) -> None:
        self._ranking = store
        self.seed_last_closes()

    def _ranking_price(self, symbol: str) -> float | None:
        store = self._ranking
        if store is None or not hasattr(store, "snapshot"):
            return None
        ticker = symbol.strip().upper()
        for row in store.snapshot() or []:
            if str(row.get("symbol") or "").strip().upper() != ticker:
                continue
            try:
                price = float(row.get("last_price"))
            except (TypeError, ValueError):
                return None
            return price if price > 0 else None
        return None

    def bind_autosync(self, autosync: Any) -> None:
        self._autosync = autosync

    def status(self) -> dict[str, Any]:
        last_quotes = self._quotes.snapshot()
        if self._trades_live or self._depth_live:
            quote_mode = "live"
        elif last_quotes:
            quote_mode = "last_close"
        else:
            quote_mode = "waiting"
        payload = {
            "enabled": self.enabled,
            "connected": self.connected,
            "trades_live": self._trades_live,
            "depth_live": self._depth_live,
            "symbols": self._active_symbols(),
            "source": "TickChart",
            "mode": "cloud",
            "last_ingested": self._last_cloud_count,
            "last_sync_at": self._last_cloud_ingest,
            "quote_mode": quote_mode,
            "last_quotes": len(last_quotes),
        }
        autosync = getattr(self, "_autosync", None)
        if autosync is not None and hasattr(autosync, "status"):
            extra = autosync.status()
            if extra.get("last_sync_at") and not payload.get("last_sync_at"):
                payload["last_sync_at"] = extra.get("last_sync_at")
            if extra.get("last_ingested"):
                payload["last_ingested"] = extra.get("last_ingested")
            payload["autosync_enabled"] = extra.get("autosync_enabled", False)
            payload["autosync_watching"] = extra.get("autosync_watching", False)
        return payload

    async def start(self) -> None:
        if self._running:
            return
        if not self._settings.tickchart_enabled:
            logger.warning("TickChart is disabled")
            return
        self._running = True
        if self._api_key:
            if self._client is None:
                self._client = httpx.AsyncClient(
                    timeout=20.0,
                    headers=_auth_headers(self._api_key),
                )
                self._owns_client = True
            self._tasks = [
                asyncio.create_task(self._run_ws(self._trades_ws, "trades"), name="tickchart-trades-ws"),
                asyncio.create_task(self._run_ws(self._depth_ws, "depth"), name="tickchart-depth-ws"),
            ]
            if self._rest_url:
                self._tasks.append(
                    asyncio.create_task(self._run_rest_fallback(), name="tickchart-rest-fallback"),
                )
            logger.info(
                "TickChart feed starting symbols=%s trades_ws=%s depth_ws=%s",
                self._active_symbols(),
                _redact_url(self._trades_ws),
                _redact_url(self._depth_ws),
            )
        else:
            logger.info("TickChart cloud ingest ready (browser upload / live stream)")
        self.seed_last_closes()
        self._tasks.append(
            asyncio.create_task(self._bootstrap_session(), name="tickchart-session-bootstrap"),
        )

    async def stop(self) -> None:
        self._running = False
        self._trades_live = False
        self._depth_live = False
        tasks = list(self._tasks)
        self._tasks = []
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None
        logger.info("TickChart feed stopped")

    async def ingest_message(self, payload: dict[str, Any] | list[Any] | None) -> int:
        """Accept a TickChart tick, snapshot, or depth payload."""

        if payload is None:
            return 0
        if isinstance(payload, list):
            ingested = 0
            for item in payload:
                if isinstance(item, dict):
                    ingested += await self.ingest_message(item)
            return ingested
        if not isinstance(payload, dict):
            return 0

        nested = payload.get("data")
        if isinstance(nested, dict) and (
            "price" in nested or "bids" in nested or "events" in nested or "ticks" in nested
        ):
            merged = {**nested, **{key: value for key, value in payload.items() if key != "data"}}
            return await self.ingest_message(merged)

        ingested = 0
        ticks = payload.get("ticks") or payload.get("trades")
        if isinstance(ticks, list):
            symbol = str(payload.get("symbol") or "")
            for item in ticks:
                if not isinstance(item, dict):
                    continue
                row = dict(item)
                row.setdefault("symbol", symbol)
                ingested += await self.ingest_message(row)

        msg_type = str(payload.get("type") or payload.get("channel") or "").lower()
        if msg_type in {"trade", "tick", "print"} or (
            payload.get("price") is not None and payload.get("symbol") and "bids" not in payload
        ):
            ingested += 1 if await self._ingest_trade(payload) else 0
        if msg_type in {"trades_snapshot", "snapshot", "ticks_snapshot"} or isinstance(
            payload.get("events"), list
        ):
            ingested += await self._ingest_trades_snapshot(payload)
        if msg_type in {"depth_snapshot", "depth", "orderbook", "book", "order_book"} or (
            "bids" in payload or "asks" in payload or isinstance(payload.get("order_book"), dict)
        ):
            ingested += 1 if await self._ingest_depth(payload) else 0
        if ingested:
            self._last_cloud_count += ingested
            self._last_cloud_ingest = datetime.now(timezone.utc).isoformat()
        return ingested

    async def hydrate_symbol(self, symbol: str) -> int:
        """Optional REST snapshot only when TICKCHART_REST_URL is set."""

        ticker = symbol.strip().upper()
        if not ticker or not self.enabled or not self._rest_url:
            return 0
        ingested = 0
        ingested += await self._rest_trades(ticker)
        ingested += await self._rest_depth(ticker)
        return ingested

    def seed_last_closes(self) -> int:
        """Fill the last-close book from ranking snapshots when ticks are absent."""

        store = self._ranking
        if store is None or not hasattr(store, "snapshot"):
            return 0
        missing: list[dict[str, Any]] = []
        for row in store.snapshot() or []:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "").strip().upper()
            if not symbol or self._quotes.price(symbol):
                continue
            missing.append(row)
        return self._quotes.apply_closes(missing) if missing else 0

    async def pull_session(self) -> dict[str, Any]:
        """Immediately pull live ticks or last-close quotes for the sector/radar tape."""

        seeded = self.seed_last_closes()
        ingested = 0
        watched = 0
        delayed = 0
        symbols = self._universe_symbols()[:40]
        for symbol in symbols:
            await self.watch(symbol)
            watched += 1
            ingested += await self.hydrate_symbol(symbol)
        if not any(self.radar_report(symbol).get("quote_mode") == "live" for symbol in symbols[:8]):
            delayed = await self._pull_delayed_closes(symbols)
        rows = self.market_rows()
        live_count = sum(1 for row in rows if row.get("quote_mode") == "live")
        close_count = sum(1 for row in rows if row.get("quote_mode") == "last_close")
        if live_count:
            quote_mode = "live"
        elif close_count or rows:
            quote_mode = "last_close"
        else:
            quote_mode = "waiting"
        return {
            "success": True,
            "source": "TickChart",
            "watched": watched,
            "ingested": ingested,
            "seeded_last_close": seeded,
            "delayed_closes": delayed,
            "count": len(rows),
            "live": live_count,
            "last_close": close_count,
            "quote_mode": quote_mode,
            "data": rows,
        }

    async def _bootstrap_session(self) -> None:
        await asyncio.sleep(0.05)
        try:
            await self.pull_session()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("TickChart session bootstrap failed", exc_info=True)

    async def _pull_delayed_closes(self, symbols: list[str]) -> int:
        """Use delayed/close quotes so the tape is not stuck waiting for live ticks."""

        if not self._api_key:
            return 0
        provider_factory = getattr(self, "_close_quotes_provider", None)
        if provider_factory is None and not self._owns_client:
            return 0
        try:
            from app.services.sahm_data_provider import SahmDataProvider
            from app.services.sahm_live_market import _flatten_quote, _merge_board
        except Exception:
            return 0
        provider = provider_factory() if callable(provider_factory) else SahmDataProvider(self._settings, api_key=self._api_key)
        closes: list[dict[str, Any]] = []
        try:
            board = await asyncio.wait_for(provider.fetch_market_board(), timeout=10.0)
            movers = _merge_board(board)
            wanted = {str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()}
            for symbol, quote in movers.items():
                if wanted and symbol not in wanted:
                    continue
                closes.append(quote)
            missing = [symbol for symbol in symbols if not self._quotes.price(symbol)]
            if missing:
                extra = await asyncio.wait_for(
                    provider.fetch_quotes_for(missing[:12], limit=12),
                    timeout=12.0,
                )
                for symbol, payload in extra.items():
                    closes.append(_flatten_quote(payload) or {"symbol": symbol, **payload})
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("delayed last-close pull failed", exc_info=True)
            return 0
        finally:
            closer = getattr(provider, "aclose", None)
            if callable(closer):
                try:
                    await closer()
                except Exception:
                    pass
        rows: list[dict[str, Any]] = []
        for quote in closes:
            symbol = str(quote.get("symbol") or "").strip().upper()
            price = quote.get("price") or quote.get("last_price") or quote.get("close")
            if not symbol or not price:
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "last_price": price,
                    "volume": quote.get("volume"),
                    "value_traded": quote.get("value_traded"),
                    "change_percent": quote.get("change_percent"),
                }
            )
        return self._quotes.apply_closes(rows)

    async def watch(self, symbol: str) -> None:
        ticker = symbol.strip().upper()
        if ticker:
            await self._subscribe_symbol(ticker)

    async def ensure_radar(self, symbol: str) -> dict[str, Any]:
        ticker = symbol.strip().upper()
        self.seed_last_closes()
        session = self._engine.session_snapshot(ticker)
        if session.last_price is None:
            await self.hydrate_symbol(ticker)
        if self.radar_report(ticker).get("last_price") is None:
            await self._pull_delayed_closes([ticker])
        await self._subscribe_symbol(ticker)
        return self.radar_report(ticker)

    def radar_report(self, symbol: str) -> dict[str, Any]:
        ticker = symbol.strip().upper()
        report = self._engine.get_latest_signal_report(ticker)
        levels = self._engine.levels_snapshot(ticker)
        session = self._engine.session_snapshot(ticker)
        tape = self._tape(ticker)
        live = tape.snapshot()
        trap = live.get("trap") or report.get("trap")
        if trap:
            report["trap"] = trap
            if trap.get("kind") == "silent_accumulation":
                report["signal"] = "entry"
                report["entry"] = True
            elif trap.get("kind") in {"bull_trap", "bear_trap", "silent_distribution"}:
                report["signal"] = "trap"
            reasons = list(report.get("reasons") or [])
            if trap["label"] not in reasons:
                reasons.insert(0, trap["label"])
            report["reasons"] = reasons
        bid = live.get("bid") if live.get("bid") is not None else _json_number(levels.bid)
        ask = live.get("ask") if live.get("ask") is not None else _json_number(levels.ask)
        spread = None
        if bid is not None and ask is not None:
            spread = round(float(ask) - float(bid), 6)
        last_price = report.get("last_price") or live.get("last_price")
        live_tick = last_price is not None
        stored = self._quotes.get(ticker) or {}
        ranking = self._ranking_row(ticker) or {}
        if last_price is None:
            last_price = stored.get("last_price") or self._quotes.price(ticker)
        if last_price is None:
            last_price = ranking.get("last_price") or self._ranking_price(ticker)
        phase = session_phase(now_riyadh())
        if live_tick and phase == "open":
            quote_mode = "live"
        elif last_price is not None:
            quote_mode = "last_close"
        else:
            quote_mode = "waiting"
        reasons = list(report.get("reasons") or [])
        if quote_mode == "last_close":
            note = "آخر إغلاق مسجّل — يُحدَّث مع أول تكات للجلسة"
            reasons = [item for item in reasons if "انتظار بيانات الجلسة" not in str(item)]
            if note not in reasons:
                reasons.insert(0, note)
        elif quote_mode == "waiting":
            note = "في انتظار بيانات الجلسة"
            if note not in reasons:
                reasons.insert(0, note)
        change = live.get("change_percent")
        if change is None:
            change = report.get("change_percent")
        if change is None:
            change = stored.get("change_percent") or ranking.get("change_percent")
        session_volume = live.get("session_volume") or _json_number(session.buy_volume + session.sell_volume)
        if not session_volume:
            session_volume = stored.get("volume") or ranking.get("volume")
        session_value = live.get("session_value") or stored.get("value_traded") or ranking.get("value_traded")
        net_flow = report.get("net_flow") or 0
        if not net_flow and session_value and change:
            net_flow = float(session_value) * (float(change) / 100.0)
        report.update(
            {
                "symbol": ticker,
                "name": company_name_for(ticker) or ticker,
                "sector": sector_for(ticker),
                "bid": bid,
                "ask": ask,
                "spread": spread,
                "bid_size": _json_number(levels.bid_size) or _json_number(tape.bid_size()),
                "ask_size": _json_number(levels.ask_size) or _json_number(tape.ask_size()),
                "book_pressure": _json_number(levels.book_pressure),
                "last_price": last_price,
                "change_percent": change,
                "mfi": live.get("mfi"),
                "institutional_mfi": live.get("institutional_mfi"),
                "retail_mfi": live.get("retail_mfi"),
                "volume_ratio": live.get("volume_ratio"),
                "block_trades": live.get("block_trades"),
                "last_block_value": live.get("last_block_value"),
                "bid_wall": live.get("bid_wall"),
                "ask_wall": live.get("ask_wall"),
                "levels": live.get("levels"),
                "session_volume": session_volume,
                "session_value": session_value,
                "net_flow": net_flow,
                "live_quote": quote_mode == "live",
                "quote_mode": quote_mode,
                "session_phase": phase,
                "session_label": phase_label(phase),
                "reasons": reasons,
                "source": "TickChart",
            }
        )
        return report

    def market_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for symbol in self._universe_symbols():
            report = self.radar_report(symbol)
            if not report.get("last_price"):
                continue
            volume = report.get("session_volume") or 0
            value = report.get("session_value") or 0
            change = report.get("change_percent") or 0
            net_flow = report.get("net_flow") or 0
            if not net_flow and value and change:
                net_flow = float(value) * (float(change) / 100.0)
            rows.append(
                {
                    "symbol": symbol,
                    "name": report.get("name") or symbol,
                    "sector": report.get("sector") or sector_for(symbol),
                    "last_price": report.get("last_price"),
                    "price": report.get("last_price"),
                    "price_change_pct": change,
                    "volume": volume,
                    "value_traded": value,
                    "net_flow": net_flow,
                    "inflow": report.get("inflow") or max(float(net_flow), 0.0),
                    "outflow": report.get("outflow") or max(-float(net_flow), 0.0),
                    "mfi": report.get("mfi"),
                    "institutional_mfi": report.get("institutional_mfi"),
                    "retail_mfi": report.get("retail_mfi"),
                    "trap": report.get("trap"),
                    "signal": report.get("signal"),
                    "live": report.get("quote_mode") == "live",
                    "quote_mode": report.get("quote_mode"),
                }
            )
        return rows

    def opportunities(self) -> list[dict[str, Any]]:
        if session_phase(now_riyadh()) == "open":
            return self.live_recommendations()
        return self.close_recommendations()

    def live_recommendations(self) -> list[dict[str, Any]]:
        """Intraday entries from live ticks and session flow while TASI is open."""

        return self._live_opportunities()

    def close_recommendations(self) -> list[dict[str, Any]]:
        """Always scan last close + closing volume for next-session entries."""

        from app.services.eod_scan import scan_end_of_day

        return scan_end_of_day(self._close_snapshots())

    def _live_opportunities(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for report in (self.radar_report(symbol) for symbol in self._universe_symbols()):
            last = report.get("last_price")
            if not last:
                continue
            trap = report.get("trap") or {}
            kind = str(trap.get("kind") or "")
            signal = str(report.get("signal") or "neutral")
            inst = report.get("institutional_mfi")
            bounce = kind == "silent_accumulation" or (signal == "entry" and (inst or 50) >= 55)
            momentum = signal == "entry" and not bounce and (report.get("volume_ratio") or 0) >= 1.2
            trap_exit = kind in {"bull_trap", "bear_trap", "silent_distribution"} or signal in {"trap", "exit"}
            if not (bounce or momentum or trap_exit):
                continue
            atr = float(report.get("atr") or last * 0.012)
            if bounce:
                signal_type = "ارتداد إيجابي من تجميع صامت 📈"
                signal_kind = "bounce"
                reason = trap.get("label") or "تجميع مؤسسي صامت مع جدار طلب"
                target = last + atr * 1.4
                stop = last - atr
            elif trap_exit:
                signal_type = "فخ سيولة لحظي ⚠️"
                signal_kind = "bounce" if kind == "bear_trap" else "momentum"
                reason = trap.get("label") or "ضغط دفتر أوامر مقابل تضاعف الحجم"
                target = last + atr if kind == "bear_trap" else last - atr * 0.8
                stop = last - atr if kind == "bear_trap" else last + atr
            else:
                signal_type = "استمرار صعود بسيولة مؤسسية 🚀"
                signal_kind = "momentum"
                reason = "تدفق مؤسسي مع تكات صاعدة وعمق سوق داعم"
                target = last + atr * 1.6
                stop = last - atr
            score = int(min(94, max(68, float(report.get("score") or 70))))
            if inst:
                score = int(min(94, max(score, inst)))
            rows.append(
                {
                    "symbol": report["symbol"],
                    "name": report.get("name") or report["symbol"],
                    "close_price": float(last),
                    "signal_type": signal_type,
                    "signal_kind": signal_kind,
                    "confidence": f"{score}%",
                    "confidence_score": score,
                    "entry_price": f"{float(last):.2f}",
                    "target_price": f"{float(target):.2f}",
                    "stop_loss": f"{float(stop):.2f}",
                    "reason": reason,
                    "volume_ratio": report.get("volume_ratio"),
                    "mfi": report.get("institutional_mfi") or report.get("mfi"),
                    "scan_mode": "live",
                    "horizon": "intraday",
                    "entry": True,
                    "entry_rule": "intraday_flow",
                }
            )
        rows.sort(key=lambda item: int(item.get("confidence_score") or 0), reverse=True)
        return rows

    def _close_snapshots(self) -> list[dict[str, Any]]:
        snapshots: list[dict[str, Any]] = []
        for symbol in self._universe_symbols():
            report = self.radar_report(symbol)
            last = report.get("last_price")
            if not last:
                continue
            levels = self._engine.levels_snapshot(symbol)
            tape = self._tape(symbol)
            prices = list(tape.prices)
            ranking = self._ranking_row(symbol) or {}
            history = self._quotes.close_history(symbol)
            closes = [float(bar["close"]) for bar in history if bar.get("close")]
            volumes = [float(bar.get("volume") or 0) for bar in history]
            snapshots.append(
                {
                    "symbol": symbol,
                    "name": report.get("name") or ranking.get("name") or symbol,
                    "last_price": last,
                    "close_price": last,
                    "closes": closes,
                    "volumes": volumes,
                    "session_volume": report.get("session_volume") or ranking.get("volume") or 0,
                    "volume": ranking.get("volume") or report.get("session_volume") or 0,
                    "volume_ratio": report.get("volume_ratio"),
                    "change_percent": report.get("change_percent"),
                    "institutional_mfi": report.get("institutional_mfi"),
                    "mfi": report.get("mfi") or ranking.get("mfi"),
                    "net_flow": report.get("net_flow") or 0,
                    "atr": report.get("atr"),
                    "session_high": _json_number(levels.session_high)
                    or (float(max(prices)) if prices else last),
                    "session_low": _json_number(levels.session_low)
                    or (float(min(prices)) if prices else last),
                    "trap": report.get("trap"),
                    "book_pressure": report.get("book_pressure"),
                    "bid_size": report.get("bid_size"),
                    "ask_size": report.get("ask_size"),
                    "spread": report.get("spread"),
                    "bid_wall": report.get("bid_wall"),
                    "ask_wall": report.get("ask_wall"),
                }
            )
        return snapshots

    def _ranking_row(self, symbol: str) -> dict[str, Any] | None:
        store = self._ranking
        if store is None or not hasattr(store, "snapshot"):
            return None
        ticker = symbol.strip().upper()
        for row in store.snapshot() or []:
            if str(row.get("symbol") or "").strip().upper() == ticker:
                return dict(row)
        return None

    def _universe_symbols(self) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        sources: list[str] = list(self._active_symbols())
        if self._ranking is not None and hasattr(self._ranking, "snapshot"):
            for row in self._ranking.snapshot() or []:
                sources.append(str(row.get("symbol") or ""))
        for row in self._quotes.snapshot():
            sources.append(str(row.get("symbol") or ""))
        for symbol in sources:
            ticker = str(symbol).strip().upper()
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)
            ordered.append(ticker)
        return ordered

    def alerts(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for row in self.market_rows():
            trap = row.get("trap") or {}
            kind = str(trap.get("kind") or "")
            if kind in {"bull_trap", "bear_trap", "silent_distribution"}:
                items.append(
                    {
                        "id": f"trap-{row['symbol']}-{kind}",
                        "kind": "trap",
                        "symbol": row["symbol"],
                        "name": row["name"],
                        "title": "فخ سيولة لحظي",
                        "message": trap.get("label") or "",
                    }
                )
            elif kind == "silent_accumulation" or (row.get("net_flow") or 0) > 0:
                items.append(
                    {
                        "id": f"inflow-{row['symbol']}",
                        "kind": "inflow",
                        "symbol": row["symbol"],
                        "name": row["name"],
                        "title": "تدفق سيولة مؤسسي",
                        "message": f"MFI مؤسسي {row.get('institutional_mfi') or '—'} على {row['name']}",
                    }
                )
        for row in self.opportunities():
            items.append(
                {
                    "id": f"opp-{row['symbol']}-{row['signal_kind']}",
                    "kind": "opportunity",
                    "symbol": row["symbol"],
                    "name": row["name"],
                    "title": row["signal_type"],
                    "message": row["reason"],
                }
            )
        return items

    def _tape(self, symbol: str) -> SymbolTape:
        ticker = symbol.strip().upper()
        tape = self._tapes.get(ticker)
        if tape is None:
            tape = SymbolTape(symbol=ticker)
            self._tapes[ticker] = tape
        return tape

    def _active_symbols(self) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        sources: list[str] = []
        sources.extend(self._configured_symbols)
        if self._watchlist is not None:
            sources.extend(self._watchlist.symbols())
        sources.extend(DEFAULT_TICKCHART_SYMBOLS)
        try:
            sources.extend(self._manager.subscribed_symbols())
        except Exception:
            pass
        sources.extend(self._subscribed)
        for symbol in sources:
            ticker = str(symbol).strip().upper()
            if not ticker or ticker in seen or is_prohibited(ticker):
                continue
            seen.add(ticker)
            ordered.append(ticker)
        return ordered or ["2222"]

    async def _subscribe_symbol(self, symbol: str) -> None:
        ticker = symbol.strip().upper()
        if not ticker or ticker in self._subscribed:
            self._subscribed.add(ticker)
            return
        self._subscribed.add(ticker)
        if not self._running:
            return
        await self._send_subscribe([ticker])

    async def _send_subscribe(self, symbols: list[str]) -> None:
        if not symbols:
            return
        trades_msg = {"action": "subscribe", "symbols": symbols}
        depth_msg = {"action": "subscribe", "symbols": symbols, "levels": self._depth_levels}
        async with self._ws_lock:
            await _ws_send(self._trades_socket, trades_msg)
            await _ws_send(self._depth_socket, depth_msg)

    async def _run_ws(self, url: str, channel: str) -> None:
        delay = 1.0
        while self._running:
            try:
                ws_url = _with_api_key(url, self._api_key)
                async with websockets.connect(
                    ws_url,
                    additional_headers=_auth_headers(self._api_key),
                    ping_interval=None,
                    close_timeout=5,
                    max_size=2**22,
                ) as ws:
                    delay = 1.0
                    if channel == "trades":
                        self._trades_socket = ws
                        self._trades_live = True
                    else:
                        self._depth_socket = ws
                        self._depth_live = True
                    await _ws_send(
                        ws,
                        {
                            "action": "subscribe",
                            "symbols": self._active_symbols()[:60],
                            **({"levels": self._depth_levels} if channel == "depth" else {}),
                        },
                    )
                    logger.info("TickChart %s websocket connected", channel)
                    await self._pump_ws(ws, channel)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("TickChart %s websocket disconnected; retrying", channel, exc_info=True)
            finally:
                if channel == "trades":
                    self._trades_live = False
                    self._trades_socket = None
                else:
                    self._depth_live = False
                    self._depth_socket = None
            if not self._running:
                return
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60.0)

    async def _pump_ws(self, ws: Any, channel: str) -> None:
        ping_at = asyncio.get_running_loop().time() + self._ping_seconds
        while self._running:
            timeout = max(ping_at - asyncio.get_running_loop().time(), 0.1)
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            except TimeoutError:
                await _ws_send(ws, {"action": "ping"})
                ping_at = asyncio.get_running_loop().time() + self._ping_seconds
                continue
            ping_at = asyncio.get_running_loop().time() + self._ping_seconds
            payload = _decode_ws_payload(raw)
            if payload is None:
                continue
            msg_type = str(payload.get("type") or "").lower()
            if msg_type in {"ping", "pong", "connected", "subscribed", "unsubscribed"}:
                continue
            if msg_type == "error":
                logger.warning("TickChart %s error: %s", channel, payload.get("message") or payload)
                continue
            await self.ingest_message(payload)

    async def _run_rest_fallback(self) -> None:
        await asyncio.sleep(2)
        while self._running:
            try:
                if not self._trades_live:
                    for symbol in self._active_symbols()[:12]:
                        if not self._running:
                            break
                        await self._rest_trades(symbol)
                        await asyncio.sleep(0.15)
                if not self._depth_live:
                    for symbol in self._active_symbols()[:12]:
                        if not self._running:
                            break
                        await self._rest_depth(symbol)
                        await asyncio.sleep(0.15)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("TickChart REST fallback cycle failed", exc_info=True)
            await asyncio.sleep(self._poll_seconds)

    async def _rest_trades(self, symbol: str) -> int:
        payload = await self._get_json(f"/market/trades/{symbol}/", {"limit": 50})
        if not payload:
            return 0
        payload.setdefault("symbol", symbol)
        payload.setdefault("type", "trades_snapshot")
        return await self._ingest_trades_snapshot(payload)

    async def _rest_depth(self, symbol: str) -> int:
        payload = await self._get_json(
            f"/market/depth/{symbol}/",
            {"levels": self._depth_levels},
        )
        if not payload:
            return 0
        payload.setdefault("symbol", symbol)
        payload.setdefault("type", "depth_snapshot")
        return 1 if await self._ingest_depth(payload) else 0

    async def _get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        if not self._rest_url:
            return None
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=20.0,
                headers=_auth_headers(self._api_key),
            )
            self._owns_client = True
        url = f"{self._rest_url.rstrip('/')}{path}"
        try:
            response = await self._client.get(
                url,
                params=params,
                headers=_auth_headers(self._api_key),
            )
        except httpx.HTTPError:
            logger.warning("TickChart REST network error for %s", path)
            return None
        if response.status_code >= 400:
            logger.warning("TickChart REST HTTP %s for %s", response.status_code, path)
            return None
        try:
            payload = response.json()
        except ValueError:
            return None
        return payload if isinstance(payload, dict) else None

    async def _ingest_trades_snapshot(self, payload: dict[str, Any]) -> int:
        events = payload.get("events") or payload.get("ticks") or payload.get("trades") or []
        if not isinstance(events, list):
            return 0
        symbol = str(payload.get("symbol") or "")
        ordered = sorted(events, key=_event_sort_key)
        ingested = 0
        for event in ordered:
            if not isinstance(event, dict):
                continue
            trade = dict(event)
            trade.setdefault("symbol", symbol)
            if await self._ingest_trade(trade):
                ingested += 1
        return ingested

    async def _ingest_trade(self, payload: dict[str, Any]) -> bool:
        parsed = parse_tick(payload)
        if parsed is None:
            return False
        symbol, price, volume, timestamp, dedupe_key = parsed
        if not self._mark_seen(dedupe_key):
            return False
        try:
            result = self._engine.process_trade(symbol, price, volume, timestamp=timestamp)
            self._tape(symbol).observe_print(
                price,
                volume,
                side=result.side,
                block_floor=self._block_floor,
            )
            message = LiquidityStreamMessage.from_trade(result)
            await self._manager.broadcast(symbol, message.as_json())
            if self._alerts is not None:
                await self._alerts.handle_trade(result)
            self._last_trade_time[symbol] = timestamp.isoformat()
            self._quotes.remember(symbol, price, volume=volume)
            return True
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("failed to ingest TickChart tick for %s", symbol)
            return False

    async def _ingest_depth(self, payload: dict[str, Any]) -> bool:
        parsed = parse_depth(payload)
        if parsed is None:
            return False
        symbol = parsed["symbol"]
        try:
            self._engine.observe_market(symbol, parsed)
            tape = self._tape(symbol)
            raw = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            book = raw.get("order_book") if isinstance(raw.get("order_book"), dict) else raw
            tape.observe_book(parse_book_levels(book.get("bids")), parse_book_levels(book.get("asks")))
            if parsed.get("bid") and not tape.bids:
                tape.observe_book(
                    parse_book_levels([{"price": parsed.get("bid"), "quantity": parsed.get("bid_size") or 0}]),
                    parse_book_levels([{"price": parsed.get("ask"), "quantity": parsed.get("ask_size") or 0}]),
                )
            session = self._engine.session_snapshot(symbol)
            if session.last_price is None and parsed.get("bid") and parsed.get("ask"):
                mid = (Decimal(str(parsed["bid"])) + Decimal(str(parsed["ask"]))) / 2
                self._engine.observe_market(symbol, {**parsed, "price": mid})
            snapshot = LiquidityStreamMessage.from_session(
                self._engine.session_snapshot(symbol),
                timestamp=datetime.now(timezone.utc),
            )
            await self._manager.broadcast(symbol, snapshot.as_json())
            return True
        except Exception:
            logger.exception("failed to ingest TickChart depth for %s", symbol)
            return False

    def _mark_seen(self, key: str) -> bool:
        if key in self._seen_set:
            return False
        if len(self._seen) >= _SEEN_LIMIT:
            expired = self._seen.popleft()
            self._seen_set.discard(expired)
        self._seen.append(key)
        self._seen_set.add(key)
        return True


def parse_tick(payload: dict[str, Any]) -> tuple[str, Decimal, Decimal, datetime, str] | None:
    """Parse a live print from TickChart or SAHMK trade messages."""

    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        return None
    symbol = str(data.get("symbol") or payload.get("symbol") or "").strip().upper()
    if not symbol:
        return None
    price_raw = data.get("price", data.get("last", data.get("last_price", data.get("close"))))
    qty_raw = data.get(
        "quantity",
        data.get("volume", data.get("size", data.get("qty", data.get("trade_quantity")))),
    )
    try:
        price = Decimal(str(price_raw))
        volume = Decimal(str(qty_raw))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if price <= 0 or volume < 0:
        return None
    timestamp = _parse_time(
        data.get("event_time") or data.get("timestamp") or data.get("time") or payload.get("updated_at")
    )
    dedupe = (
        data.get("id")
        or data.get("trade_id")
        or f"{symbol}|{data.get('event_time') or timestamp.isoformat()}|{price}|{volume}"
    )
    return symbol, price, volume, timestamp, str(dedupe)


def parse_depth(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize TickChart / SAHMK order-book snapshots for `observe_market`."""

    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        return None
    book = data.get("order_book") if isinstance(data.get("order_book"), dict) else data
    symbol = str(data.get("symbol") or payload.get("symbol") or book.get("symbol") or "").strip().upper()
    if not symbol:
        return None
    bids = book.get("bids") if isinstance(book.get("bids"), list) else data.get("bids")
    asks = book.get("asks") if isinstance(book.get("asks"), list) else data.get("asks")
    bid, bid_size = _top_level(bids, book.get("best_bid") or data.get("best_bid") or data.get("bid"))
    ask, ask_size = _top_level(asks, book.get("best_ask") or data.get("best_ask") or data.get("ask"))
    if bid_size is None:
        bid_size = _optional_decimal(
            book.get("bid_size")
            or data.get("bid_size")
            or data.get("total_bid_quantity_top5")
            or data.get("total_bid_quantity")
        )
    if ask_size is None:
        ask_size = _optional_decimal(
            book.get("ask_size")
            or data.get("ask_size")
            or data.get("total_ask_quantity_top5")
            or data.get("total_ask_quantity")
        )
    if bid is None and ask is None:
        return None
    return {
        "symbol": symbol,
        "bid": bid,
        "ask": ask,
        "best_bid": bid,
        "best_ask": ask,
        "bid_size": bid_size,
        "ask_size": ask_size,
        "spread": data.get("spread"),
        "order_book": {
            "bid": bid,
            "ask": ask,
            "bid_size": bid_size,
            "ask_size": ask_size,
        },
    }


def _top_level(levels: Any, fallback: Any) -> tuple[Decimal | None, Decimal | None]:
    price = _optional_decimal(fallback)
    size = None
    if isinstance(levels, list) and levels:
        first = levels[0]
        if isinstance(first, dict):
            price = _optional_decimal(first.get("price") or first.get("p") or first.get("bid") or first.get("ask")) or price
            size = _optional_decimal(first.get("quantity") or first.get("size") or first.get("q") or first.get("volume"))
        elif isinstance(first, (list, tuple)) and first:
            price = _optional_decimal(first[0]) or price
            if len(first) > 1:
                size = _optional_decimal(first[1])
    return price, size


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def _json_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _event_sort_key(event: Any) -> str:
    if not isinstance(event, dict):
        return ""
    return str(event.get("event_time") or event.get("timestamp") or event.get("time") or "")


def _clean_symbols(values: list[str] | None) -> list[str]:
    return [item.strip().upper() for item in (values or []) if str(item).strip()]


def _auth_headers(api_key: str) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    key = str(api_key or "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
        headers["X-API-Key"] = key
    return headers


def _sanitize_rest_url(raw: str | None) -> str:
    url = str(raw or "").strip().rstrip("/")
    if not url:
        return ""
    host = urlsplit(url).netloc.lower()
    if any(blocked in host for blocked in _BLOCKED_REST_HOSTS):
        logger.warning("Ignoring leftover Sahm REST URL; TickChart uses ticks/depth only")
        return ""
    return url


def _resolve_tickchart_key(settings: Settings) -> str:
    for raw in (settings.tickchart_api_key, settings.sahmk_api_key):
        key = str(raw or "").strip()
        if key and key.lower() not in _PLACEHOLDER_KEYS:
            return key
    return ""


def _with_api_key(url: str, api_key: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if api_key and "api_key" not in query:
        query["api_key"] = api_key
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _redact_url(url: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if "api_key" in query:
        query["api_key"] = "***"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _decode_ws_payload(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        payload = json.loads(raw)
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


async def _ws_send(socket: Any, payload: dict[str, Any]) -> None:
    if socket is None:
        return
    try:
        await socket.send(json.dumps(payload))
    except Exception:
        logger.debug("TickChart websocket send skipped", exc_info=True)
