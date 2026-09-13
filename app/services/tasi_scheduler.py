from __future__ import annotations

import asyncio
import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import Settings, get_settings
from app.services.liquidity_engine import LiquidityRadarEngine
from app.services.recommendations_engine import clear_recommendations_cache, live_market_recommendations
from app.services.sahm_live_market import overlay_quote_on_report, _flatten_quote
from app.services.shariah import company_name_for, is_prohibited
from app.services.tasi_clock import (
    TASI_TZ,
    is_intraday_window,
    now_riyadh,
    phase_label,
    session_phase,
)

logger = logging.getLogger(__name__)

DEFAULT_SCAN_SYMBOLS = [
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

WEEKDAYS = "sun,mon,tue,wed,thu"


class TasiMarketScheduler:
    """TASI session jobs: 09:30 open prep, 2-minute tape scan, 15:30 close refresh."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        sahm: Any = None,
        telegram: Any = None,
        ranking_sync: Any = None,
        watchlist: Any = None,
        scheduler: AsyncIOScheduler | None = None,
        enable_scheduler: bool = True,
    ) -> None:
        self._settings = settings or get_settings()
        self._sahm = sahm
        self._telegram = telegram
        self._ranking_sync = ranking_sync
        self._watchlist = watchlist
        self.scheduler = scheduler or AsyncIOScheduler(timezone=TASI_TZ)
        self._enabled = enable_scheduler and self._settings.tasi_scheduler_enabled
        self._last: dict[str, Any] = {"open": None, "scan": None, "close": None}

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.scheduler.configure(event_loop=loop)

    def start(self) -> None:
        if not self._enabled:
            logger.info("TASI market scheduler is disabled")
            return
        interval = max(1, int(self._settings.tasi_scan_interval_minutes))
        self.scheduler.add_job(
            self.prepare_open,
            "cron",
            id="tasi_open_prep",
            day_of_week=WEEKDAYS,
            hour=self._settings.tasi_open_hour,
            minute=self._settings.tasi_open_minute,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=1800,
        )
        self.scheduler.add_job(
            self.scan_session,
            "interval",
            id="tasi_intraday_scan",
            minutes=interval,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=60,
        )
        self.scheduler.add_job(
            self.close_market,
            "cron",
            id="tasi_close_refresh",
            day_of_week=WEEKDAYS,
            hour=self._settings.tasi_close_hour,
            minute=self._settings.tasi_close_minute,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=1800,
        )
        if not self.scheduler.running:
            self.scheduler.start()
        logger.info(
            "TASI scheduler started (open %02d:%02d, scan every %sm 10:00-15:00, close %02d:%02d Asia/Riyadh)",
            self._settings.tasi_open_hour,
            self._settings.tasi_open_minute,
            interval,
            self._settings.tasi_close_hour,
            self._settings.tasi_close_minute,
        )

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def status(self) -> dict[str, Any]:
        current = now_riyadh()
        phase = session_phase(current)
        jobs: list[dict[str, Any]] = []
        try:
            scheduled = self.scheduler.get_jobs()
        except Exception:
            scheduled = []
        for job in scheduled:
            nxt = getattr(job, "next_run_time", None)
            jobs.append({"id": job.id, "next_run_at": nxt.isoformat() if nxt else None})
        return {
            "success": True,
            "enabled": self._enabled,
            "running": bool(self.scheduler.running),
            "timezone": "Asia/Riyadh",
            "clock": current.isoformat(),
            "phase": phase,
            "phase_label": phase_label(phase),
            "intraday": is_intraday_window(current),
            "jobs": jobs,
            "last": dict(self._last),
        }

    async def prepare_open(self) -> dict[str, Any]:
        """09:30 — load opening quotes and previous closes."""

        current = now_riyadh()
        quotes = await self._collect_quotes()
        payload = {
            "job": "open",
            "ran_at": current.isoformat(),
            "symbols": len(quotes),
            "quotes": quotes,
        }
        self._last["open"] = {"job": "open", "ran_at": payload["ran_at"], "symbols": payload["symbols"]}
        await self._notify(
            "رزق · تجهيز افتتاح تاسي 09:30\n"
            f"تم فحص إغلاقات وأسعار {len(quotes)} رمزاً قبل الجلسة."
        )
        logger.info("TASI open prep scanned %s symbols", len(quotes))
        return payload

    async def scan_session(self, *, force: bool = False) -> dict[str, Any]:
        """Every 2 minutes during 10:00-15:00 — liquidity, volume, traps, alerts."""

        current = now_riyadh()
        if not force and not is_intraday_window(current):
            return {"job": "scan", "skipped": True, "reason": "outside_session", "ran_at": current.isoformat()}
        symbols = self._scan_symbols()
        alerts: list[dict[str, Any]] = []
        scanned = 0
        provider = self._sahm
        if provider is None or not getattr(provider, "enabled", False):
            payload = {
                "job": "scan",
                "ran_at": current.isoformat(),
                "scanned": 0,
                "alerts": 0,
                "reason": "sahm_disabled",
            }
            self._last["scan"] = payload
            return payload
        interval = "30m" if is_intraday_window(current) else "1d"
        for symbol in symbols:
            frame = None
            try:
                frame = await provider.fetch_candles(symbol, interval=interval)
            except Exception:
                frame = None
            if frame is None or getattr(frame, "empty", True):
                try:
                    frame = await provider.fetch_candles(symbol, interval="1d")
                except Exception:
                    logger.exception("TASI scan candles failed for %s", symbol)
                    continue
            try:
                quote = await provider.fetch_quote(symbol)
            except Exception:
                quote = {}
            if frame is None or getattr(frame, "empty", True):
                continue
            scanned += 1
            engine = LiquidityRadarEngine(frame.tail(80).reset_index(drop=True))
            report = overlay_quote_on_report(engine.get_latest_signal_report(symbol), quote)
            if not _is_actionable(report):
                continue
            sent = False
            if self._telegram is not None:
                try:
                    sent = bool(await self._telegram.send_radar_event(report))
                except Exception:
                    logger.exception("failed to send TASI scan alert for %s", symbol)
            alerts.append(
                {
                    "symbol": symbol,
                    "name": company_name_for(symbol) or symbol,
                    "signal": report.get("signal"),
                    "trap": bool(report.get("trap")),
                    "score": report.get("score"),
                    "volume": report.get("volume"),
                    "change_percent": report.get("change_percent"),
                    "notified": sent,
                }
            )
        payload = {
            "job": "scan",
            "ran_at": current.isoformat(),
            "scanned": scanned,
            "alerts": len(alerts),
            "signals": alerts,
        }
        self._last["scan"] = {
            "job": "scan",
            "ran_at": payload["ran_at"],
            "scanned": scanned,
            "alerts": len(alerts),
        }
        logger.info("TASI session scan: %s symbols, %s alerts", scanned, len(alerts))
        return payload

    async def close_market(self) -> dict[str, Any]:
        """15:30 — recompute ranking matrix and refresh recommendations from last close."""

        current = now_riyadh()
        ranking_updated = 0
        recs = 0
        if self._ranking_sync is not None:
            try:
                result = self._ranking_sync.sync_market_financials()
                ranking_updated = int(result.get("updated") or 0)
            except Exception:
                logger.exception("TASI close ranking sync failed")
        clear_recommendations_cache()
        provider = self._sahm
        if provider is not None and getattr(provider, "enabled", False):
            try:
                rows = await live_market_recommendations(provider, use_cache=False)
                recs = len(rows)
            except Exception:
                logger.exception("TASI close recommendations refresh failed")
        payload = {
            "job": "close",
            "ran_at": current.isoformat(),
            "ranking_updated": ranking_updated,
            "recommendations": recs,
        }
        self._last["close"] = payload
        await self._notify(
            "رزق · إغلاق تاسي 15:30\n"
            f"مصفوفة التصنيف: {ranking_updated} شركة\n"
            f"لوحة التوصيات: {recs} فرصة من آخر إغلاق."
        )
        logger.info("TASI close refresh ranking=%s recs=%s", ranking_updated, recs)
        return payload

    async def run(self, job: str, *, force: bool = False) -> dict[str, Any]:
        if job == "open":
            return await self.prepare_open()
        if job == "scan":
            return await self.scan_session(force=force)
        if job == "close":
            return await self.close_market()
        raise ValueError(job)

    def _scan_symbols(self) -> list[str]:
        seen: list[str] = []
        source: list[str] = []
        getter = getattr(self._watchlist, "symbols", None)
        if callable(getter):
            source.extend(str(item) for item in (getter() or []))
        source.extend(DEFAULT_SCAN_SYMBOLS)
        limit = max(4, int(self._settings.tasi_scan_limit))
        for symbol in source:
            ticker = symbol.strip().upper()
            if not ticker or ticker in seen or is_prohibited(ticker):
                continue
            seen.append(ticker)
            if len(seen) >= limit:
                break
        return seen

    async def _collect_quotes(self) -> list[dict[str, Any]]:
        provider = self._sahm
        symbols = self._scan_symbols()
        if provider is None or not getattr(provider, "enabled", False):
            return [{"symbol": item, "name": company_name_for(item) or item} for item in symbols]
        try:
            raw = await provider.fetch_quotes_for(symbols, limit=len(symbols))
        except Exception:
            logger.exception("TASI open quote fetch failed")
            return [{"symbol": item, "name": company_name_for(item) or item} for item in symbols]
        rows: list[dict[str, Any]] = []
        mapping = raw if isinstance(raw, dict) else {}
        for symbol in symbols:
            quote = _flatten_quote(mapping.get(symbol))
            price = quote.get("price")
            change = quote.get("change_percent")
            previous = None
            if price not in (None, 0) and change is not None:
                previous = round(float(price) / (1 + float(change) / 100.0), 4)
            rows.append(
                {
                    "symbol": symbol,
                    "name": quote.get("name") or company_name_for(symbol) or symbol,
                    "last": price,
                    "previous_close": previous,
                    "change_percent": change,
                    "volume": quote.get("volume"),
                    "value_traded": quote.get("value_traded"),
                }
            )
        return rows

    async def _notify(self, text: str) -> None:
        bot = self._telegram
        if bot is None or not getattr(bot, "enabled", False):
            return
        try:
            await bot.send_message(text)
        except Exception:
            logger.exception("TASI scheduler telegram notify failed")


def _is_actionable(report: dict[str, Any]) -> bool:
    if report.get("trap"):
        return True
    signal = str(report.get("signal") or "neutral")
    if signal in {"entry", "exit", "trap"}:
        return True
    try:
        return float(report.get("score")) >= 70
    except (TypeError, ValueError):
        return False
