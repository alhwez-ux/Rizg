from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import Settings, get_settings
from app.services.company_ranker import SAMPLE_COMPANIES, CompanyRankingEngine
from app.services.email_alert_service import EmailAlertService, is_structural_change
from app.services.ranking_store import RankingStore

logger = logging.getLogger(__name__)

_RIYADH = timezone(timedelta(hours=3))
_LIVE_UPDATES: list[dict[str, Any]] = [
    {
        "symbol": "1120",
        "name": "الراجحي",
        "profit_growth": 14.1,
        "dividend_yield": 3.4,
        "roe": 19.0,
        "pe_ratio": 15.8,
        "net_income": 16500,
    },
    {
        "symbol": "2222",
        "name": "أرامكو السعودية",
        "profit_growth": 1.2,
        "dividend_yield": 7.0,
        "roe": 26.0,
        "pe_ratio": 15.0,
        "net_income": 410000,
    },
]

ProviderFn = Callable[[], list[dict[str, Any]]]


class FinancialSyncService:
    """Scheduled TASI financials sync that recalculates the ranking matrix on save."""

    def __init__(
        self,
        settings: Settings | None = None,
        store: RankingStore | None = None,
        provider: ProviderFn | None = None,
        scheduler: BackgroundScheduler | None = None,
        email_service: EmailAlertService | None = None,
        *,
        enable_scheduler: bool = True,
    ) -> None:
        self._settings = settings or get_settings()
        self.store = store or RankingStore()
        self._provider = provider
        self.scheduler = scheduler or BackgroundScheduler(timezone=_RIYADH)
        self.email_service = email_service or EmailAlertService(self._settings)
        self._enable_scheduler = enable_scheduler and self._settings.financial_sync_enabled

    def start_scheduler(self) -> None:
        """بدء تشغيل الجدولة الخلفية"""

        if not self._enable_scheduler:
            logger.info("market financial sync scheduler is disabled")
            return
        if self.scheduler.get_job("sync_market_financials") is None:
            self.scheduler.add_job(
                self.sync_market_financials,
                "cron",
                hour=self._settings.financial_sync_hour,
                minute=self._settings.financial_sync_minute,
                id="sync_market_financials",
                replace_existing=True,
                coalesce=True,
                misfire_grace_time=3600,
            )
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info(
                "market financial sync scheduled daily at %02d:%02d Asia/Riyadh",
                self._settings.financial_sync_hour,
                self._settings.financial_sync_minute,
            )

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def fetch_latest_from_provider(self) -> list[dict[str, Any]]:
        """جلب أحدث القوائم المالية وعوائد التوزيعات ونمو الأرباح."""

        if self._provider is not None:
            return list(self._provider() or [])
        stamped = datetime.now(timezone.utc).isoformat()
        updates = {str(row["symbol"]).upper(): dict(row) for row in _LIVE_UPDATES}
        merged: list[dict[str, Any]] = []
        for row in SAMPLE_COMPANIES:
            item = dict(row)
            patch = updates.get(str(item.get("symbol") or "").upper())
            if patch:
                item.update(patch)
            item["last_updated"] = stamped
            merged.append(item)
        return merged

    def sync_market_financials(self) -> dict[str, Any]:
        """سحب، حفظ، إعادة حساب وتحديث المصفوفة فوراً."""

        logger.info("syncing TASI financials for the ranking matrix")
        try:
            raw_data = self.fetch_latest_from_provider()
            if not raw_data:
                logger.warning("financial provider returned no rows; ranking store unchanged")
                return {"updated": 0, "synced_at": self.store.synced_at(), "data": []}

            ranked_results = CompanyRankingEngine(raw_data).get_ranked_payload()
            previous = self.store.snapshot()
            alerts = self._alert_category_changes(previous, ranked_results)
            synced_at = datetime.now(timezone.utc).isoformat()
            for row in ranked_results:
                row.setdefault("last_updated", synced_at)
            self.store.replace(ranked_results, synced_at)
            logger.info(
                "updated ranking matrix for %s companies (%s structural alerts)",
                len(ranked_results),
                alerts,
            )
            return {
                "updated": len(ranked_results),
                "synced_at": synced_at,
                "alerts": alerts,
                "data": ranked_results,
            }
        except Exception:
            logger.exception("failed to sync market financials")
            raise

    def _alert_category_changes(
        self,
        previous: list[dict[str, Any]],
        ranked: list[dict[str, Any]],
    ) -> int:
        old_by_symbol = {
            str(row.get("symbol") or "").strip().upper(): str(row.get("category") or "").strip()
            for row in previous
            if row.get("symbol")
        }
        sent = 0
        for row in ranked:
            symbol = str(row.get("symbol") or "").strip().upper()
            new_category = str(row.get("category") or "").strip()
            old_category = old_by_symbol.get(symbol, "")
            if not symbol or not is_structural_change(old_category, new_category):
                continue
            name = str(row.get("name") or symbol)
            if self.email_service.send_alert(name, symbol, old_category, new_category):
                sent += 1
        return sent
