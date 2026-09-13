from __future__ import annotations

import asyncio
import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import Settings, get_settings
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
        tickchart: Any = None,
        scheduler: AsyncIOScheduler | None = None,
        enable_scheduler: bool = True,
    ) -> None:
        self._settings = settings or get_settings()
        self._sahm = None
        self._telegram = telegram
        self._ranking_sync = ranking_sync
        self._watchlist = watchlist
        self._tickchart = tickchart
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
        feed = self._tickchart
        if feed is None or not getattr(feed, "enabled", False):
            payload = {
                "job": "scan",
                "ran_at": current.isoformat(),
                "scanned": 0,
                "alerts": 0,
                "reason": "tickchart_disabled",
            }
            self._last["scan"] = payload
            return payload
        for symbol in symbols:
            try:
                report = feed.radar_report(symbol)
            except Exception:
                logger.exception("TASI TickChart scan failed for %s", symbol)
                continue
            if not report.get("last_price"):
                continue
            scanned += 1
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
                    "volume": report.get("session_volume"),
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
        feed = self._tickchart
        if feed is not None:
            recs = len(feed.opportunities())
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
        feed = self._tickchart
        symbols = self._scan_symbols()
        if feed is None:
            return [{"symbol": item, "name": company_name_for(item) or item} for item in symbols]
        rows: list[dict[str, Any]] = []
        for symbol in symbols:
            report = feed.radar_report(symbol)
            rows.append(
                {
                    "symbol": symbol,
                    "name": company_name_for(symbol) or symbol,
                    "last": report.get("last_price"),
                    "change_percent": report.get("change_percent"),
                    "volume": report.get("session_volume"),
                    "value_traded": report.get("session_value"),
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
