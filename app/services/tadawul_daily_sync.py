from __future__ import annotations

import asyncio
import json
import logging
import threading
import time as time_module
from datetime import datetime, time
from pathlib import Path
from typing import Any

import httpx
from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import Settings, get_settings
from app.services.company_ranker import (
    MAJOR_TASI_COMPANIES,
    CompanyRankingEngine,
    merge_ranking_financials,
)
from app.services.recommendations_engine import clear_recommendations_cache
from app.services.sahm_live_market import _flatten_quote
from app.services.shariah import company_name_for, compliance_universe, is_prohibited, sector_for
from app.services.tasi_clock import TASI_TZ, is_tasi_weekday, now_riyadh, phase_label, session_phase

logger = logging.getLogger(__name__)

TAPE_PATH = Path("data/tasi_daily_tape.json")
WEEKDAYS = "sun,mon,tue,wed,thu"
JOB_ID = "tadawul_daily_close"
TADAWUL_HOME = "https://www.saudiexchange.sa"
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
}


class TadawulDailySync:
    """Nightly TASI close pull at 16:00 Asia/Riyadh — prices, change, volume, ranking."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        sahm: Any = None,
        ranking_store: Any = None,
        telegram: Any = None,
        scheduler: BackgroundScheduler | None = None,
        tape_path: Path | None = None,
        enable_scheduler: bool = True,
        tadawul_get: Any = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._sahm = sahm
        self._ranking_store = ranking_store
        self._telegram = telegram
        self.scheduler = scheduler or BackgroundScheduler(timezone=TASI_TZ)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._tadawul_get = tadawul_get
        self._tape_path = tape_path or TAPE_PATH
        self._enabled = enable_scheduler and self._settings.tadawul_daily_sync_enabled
        self._guard = threading.RLock()
        self._last: dict[str, Any] | None = None
        self._rows: list[dict[str, Any]] = []
        self._as_of: str | None = None
        self._load_tape()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def start(self) -> None:
        if not self._enabled:
            logger.info("Tadawul daily sync is disabled")
            return
        if self.scheduler.get_job(JOB_ID) is None:
            self.scheduler.add_job(
                self.sync_market_closing_prices,
                "cron",
                id=JOB_ID,
                day_of_week=WEEKDAYS,
                hour=self._settings.tadawul_daily_sync_hour,
                minute=self._settings.tadawul_daily_sync_minute,
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=7200,
            )
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("🌙 تم تفعيل مجدول السحب اليومي لإغلاقات تداول للاستخدام الشخصي.")

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def status(self) -> dict[str, Any]:
        current = now_riyadh()
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
            "hour": self._settings.tadawul_daily_sync_hour,
            "minute": self._settings.tadawul_daily_sync_minute,
            "phase": session_phase(current),
            "phase_label": phase_label(session_phase(current)),
            "as_of": self._as_of,
            "symbols": len(self._rows),
            "jobs": jobs,
            "last": dict(self._last or {}),
        }

    def snapshot(self) -> list[dict[str, Any]]:
        with self._guard:
            return [dict(row) for row in self._rows]

    def should_catch_up(self, moment: datetime | None = None) -> bool:
        """True after 16:00 on a TASI weekday when today's close is not stored yet."""

        current = now_riyadh(moment)
        if not is_tasi_weekday(current):
            return False
        target = time(
            self._settings.tadawul_daily_sync_hour,
            self._settings.tadawul_daily_sync_minute,
        )
        if current.time().replace(microsecond=0) < target:
            return False
        return self._as_of != current.date().isoformat()

    def schedule_startup_catch_up(self) -> None:
        """Run today's close pull in the background if 16:00 already passed."""

        if not self._settings.tadawul_daily_sync_on_startup:
            return
        if not self.should_catch_up():
            return
        logger.info("Tadawul daily sync catching up today's close in the background")
        asyncio.create_task(self._catch_up_safe())

    async def _catch_up_safe(self) -> None:
        await self.run_daily_sync()

    def sync_market_closing_prices(self) -> dict[str, Any]:
        """Cron entry: daily 16:00 Asia/Riyadh — Tadawul probe then Sahm closes."""

        return self._run_async(self.run_daily_sync())

    async def run_daily_sync(self) -> dict[str, Any]:
        current_time = now_riyadh().strftime("%Y-%m-%d %H:%M:%S")
        logger.info("🔄 جاري سحب إغلاقات تداول اليومية - %s...", current_time)
        try:
            return await self._sync_market_closing_prices()
        except httpx.RequestError as exc:
            logger.error("❌ حدث خطأ في الشبكة أثناء الاتصال بموقع تداول: %s", exc)
            return self._use_last_recorded(reason="network")
        except Exception as exc:
            logger.exception("❌ حدث خطأ غير متوقع أثناء معالجة بيانات الإغلاق: %s", exc)
            return self._use_last_recorded(reason="unexpected")

    def _run_async(self, coro: Any) -> Any:
        loop = self._loop
        if loop is not None and loop.is_running():
            return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=420)
        return asyncio.run(coro)

    async def _sync_market_closing_prices(self) -> dict[str, Any]:
        """Probe saudiexchange.sa, then persist Sahm closes and recompute ranking."""

        status = await self.probe_tadawul_site()
        if status != 200:
            logger.warning(
                "⚠️ تعذر الوصول للاستجابة المباشرة، رمز الحالة: %s. سيتم الاعتماد على آخر بيانات مسجلة.",
                status,
            )
            return self._use_last_recorded(reason="tadawul_status", status_code=status)

        current = now_riyadh()
        rows = await self.fetch_daily_market_data()
        ranking_updated = 0
        if not rows:
            logger.warning(
                "⚠️ تعذر الوصول للاستجابة المباشرة، رمز الحالة: %s. سيتم الاعتماد على آخر بيانات مسجلة.",
                status,
            )
            return self._use_last_recorded(reason="empty_fetch", status_code=status)

        self.save_to_database(rows, as_of=current.date().isoformat())
        ranking_updated = self.update_ranking_matrix(rows)
        clear_recommendations_cache()
        payload = {
            "job": "daily_close",
            "ran_at": current.isoformat(),
            "as_of": current.date().isoformat(),
            "symbols": len(rows),
            "ranking_updated": ranking_updated,
            "source": "Sahm API",
            "tadawul_status": status,
            "used_last_recorded": False,
        }
        self._last = payload
        await self._notify(
            "رزق · سحب إغلاق تاسي اليومي 16:00\n"
            f"أسعار وحجوم {len(rows)} شركة · مصفوفة التصنيف: {ranking_updated}"
        )
        logger.info("✅ تم بنجاح سحب وتحديث إغلاقات السوق ومصفوفة التصنيف لجميع الشركات دون أخطاء.")
        return payload

    async def probe_tadawul_site(self) -> int:
        """GET saudiexchange.sa with a browser User-Agent; timeout 15s."""

        getter = self._tadawul_get
        if getter is not None:
            result = getter()
            if asyncio.iscoroutine(result):
                result = await result
            return int(result)
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers=BROWSER_HEADERS,
        ) as client:
            response = await client.get(TADAWUL_HOME)
            return response.status_code

    def _use_last_recorded(self, *, reason: str, status_code: int | None = None) -> dict[str, Any]:
        payload = {
            "job": "daily_close",
            "ran_at": now_riyadh().isoformat(),
            "as_of": self._as_of,
            "symbols": len(self._rows),
            "ranking_updated": 0,
            "source": "last_recorded",
            "used_last_recorded": True,
            "reason": reason,
            "tadawul_status": status_code,
        }
        self._last = payload
        return payload

    async def fetch_daily_market_data(self) -> list[dict[str, Any]]:
        """Pull close / change / volume via Sahm market-watch APIs (gainers, volume, value, quotes)."""

        provider = self._sahm
        if provider is None or not getattr(provider, "enabled", False):
            logger.warning("Tadawul daily sync skipped: Sahm is not configured")
            return []

        directory: dict[str, dict[str, Any]] = {}
        try:
            companies = await provider.fetch_company_directory()
        except Exception:
            logger.exception("Tadawul daily sync: company directory failed")
            companies = []
        for item in companies if isinstance(companies, list) else []:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "").strip().upper()
            if symbol:
                directory[symbol] = item

        movers: dict[str, dict[str, Any]] = {}
        try:
            board = await provider.fetch_market_board()
        except Exception:
            logger.exception("Tadawul daily sync: market board failed")
            board = {}
        for key in ("gainers", "volume", "value"):
            for raw in board.get(key) or []:
                quote = _flatten_quote(raw if isinstance(raw, dict) else {})
                symbol = str(quote.get("symbol") or "").strip().upper()
                if not symbol:
                    continue
                current = movers.setdefault(symbol, {"symbol": symbol})
                current.update({k: v for k, v in quote.items() if v not in (None, "")})

        wanted = self._universe_symbols(directory)
        missing = [symbol for symbol in wanted if symbol not in movers]
        extra: dict[str, dict[str, Any]] = {}
        if missing and hasattr(provider, "fetch_quotes_for"):
            try:
                extra = await provider.fetch_quotes_for(missing, limit=self._settings.tadawul_daily_quote_limit)
            except Exception:
                logger.exception("Tadawul daily sync: quote fill failed")
                extra = {}
        for symbol, payload in extra.items():
            ticker = str(symbol or "").strip().upper()
            if not ticker or ticker in movers:
                continue
            movers[ticker] = _flatten_quote(payload)

        as_of = now_riyadh().date().isoformat()
        rows: list[dict[str, Any]] = []
        for symbol in wanted:
            quote = movers.get(symbol) or {}
            profile = directory.get(symbol) or {}
            close = quote.get("price") or quote.get("last_price")
            if close in (None, ""):
                continue
            name = (
                str(quote.get("name") or "").strip()
                or company_name_for(symbol)
                or str(profile.get("name_ar") or profile.get("name") or symbol)
            )
            sector = (
                str(quote.get("sector") or "").strip()
                or str(profile.get("sector") or "").strip()
                or sector_for(symbol)
                or "أخرى"
            )
            change = float(quote.get("change_percent") or 0)
            volume = float(quote.get("volume") or 0)
            value = float(quote.get("value_traded") or 0)
            rows.append(
                {
                    "symbol": symbol,
                    "name": name,
                    "sector": sector,
                    "close": round(float(close), 4),
                    "change_percent": round(change, 4),
                    "volume": round(volume, 4),
                    "value_traded": round(value, 4),
                    "as_of": as_of,
                }
            )
        return rows

    def save_to_database(self, rows: list[dict[str, Any]], *, as_of: str | None = None) -> None:
        stamp = as_of or now_riyadh().date().isoformat()
        with self._guard:
            self._rows = [dict(row) for row in rows]
            self._as_of = stamp
            self._tape_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "source": "Sahm API",
                "as_of": stamp,
                "synced_at": now_riyadh().isoformat(),
                "count": len(self._rows),
                "data": self._rows,
            }
            self._tape_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def update_ranking_matrix(self, rows: list[dict[str, Any]]) -> int:
        store = self._ranking_store
        if store is None:
            return 0
        previous = {
            str(item.get("symbol") or "").strip().upper(): item
            for item in (store.snapshot() if hasattr(store, "snapshot") else [])
            if isinstance(item, dict) and item.get("symbol")
        }
        financials: list[dict[str, Any]] = []
        for row in rows:
            symbol = str(row.get("symbol") or "").strip().upper()
            if not symbol or is_prohibited(symbol):
                continue
            quote = {
                "symbol": symbol,
                "name": row.get("name"),
                "price": row.get("close"),
                "change_percent": row.get("change_percent"),
                "volume": row.get("volume"),
                "value_traded": row.get("value_traded"),
            }
            financials.append(
                merge_ranking_financials(
                    symbol,
                    str(row.get("name") or symbol),
                    quote=quote,
                    stored=previous.get(symbol),
                )
            )
        if not financials:
            return 0
        ranked = CompanyRankingEngine(financials).get_ranked_payload()
        synced_at = now_riyadh().isoformat()
        store.replace(ranked, synced_at, source="Sahm API")
        return len(ranked)

    def _universe_symbols(self, directory: dict[str, dict[str, Any]]) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()

        def add(raw: Any) -> None:
            symbol = str(raw or "").strip().upper()
            if not symbol or symbol in seen:
                return
            seen.add(symbol)
            ordered.append(symbol)

        for item in MAJOR_TASI_COMPANIES:
            add(item.get("symbol"))
        for item in compliance_universe():
            add(item.get("symbol"))
        for symbol in directory:
            add(symbol)
        return ordered[: max(1, self._settings.tadawul_daily_quote_limit)]

    def _load_tape(self) -> None:
        if not self._tape_path.exists():
            return
        try:
            payload = json.loads(self._tape_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        rows = payload.get("data") or []
        if not isinstance(rows, list):
            return
        self._rows = [row for row in rows if isinstance(row, dict)]
        as_of = payload.get("as_of")
        self._as_of = str(as_of) if as_of else None

    async def _notify(self, text: str) -> None:
        send = getattr(self._telegram, "send_message", None) or getattr(self._telegram, "send", None)
        if not callable(send):
            return
        try:
            result = send(text)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            logger.exception("Tadawul daily sync telegram notify failed")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sync_service = TadawulDailySync()
    sync_service.start()
    try:
        while True:
            time_module.sleep(60)
    except KeyboardInterrupt:
        sync_service.shutdown()
