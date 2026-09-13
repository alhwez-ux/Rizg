from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any

from app.core.config import Settings, get_settings
from app.services.email_alert_service import EmailAlertService
from app.services.shariah import apply_status_overlay, compliance_universe, current_status

logger = logging.getLogger(__name__)

_STATUS_ALIASES = {
    "PURE": "PURE",
    "HALAL": "PURE",
    "نقي": "PURE",
    "MIXED": "MIXED",
    "مختلط": "MIXED",
    "PROHIBITED": "PROHIBITED",
    "HARAM": "PROHIBITED",
    "محرم": "PROHIBITED",
    "محرّم": "PROHIBITED",
}


class FinancialSyncService:
    """Compares stored Shariah categories with newly scheduled ones and emails on change."""

    def __init__(
        self,
        settings: Settings | None = None,
        email_service: EmailAlertService | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self.email_service = email_service or EmailAlertService(self._settings)
        self._categories: dict[str, str] = {}
        self._names: dict[str, str] = {}
        self.reload_baseline()

    def reload_baseline(self) -> None:
        """Load the current stored classifications without sending alerts."""

        self._categories.clear()
        self._names.clear()
        for item in compliance_universe():
            symbol, name, category = _row_fields(item)
            if not symbol or not category:
                continue
            self._categories[symbol] = category
            self._names[symbol] = name

    def check_and_alert_changes(self, symbol: str, name: str, old_cat: str, new_cat: str) -> bool:
        """التحقق من تغير التصنيف وإطلاق التنبيه الفوري."""

        ticker = (symbol or "").strip().upper()
        display_name = (name or self._names.get(ticker) or ticker).strip()
        previous = normalize_category(old_cat)
        scheduled = normalize_category(new_cat)
        if not ticker or not scheduled or previous == scheduled:
            if ticker and scheduled:
                self._store(ticker, display_name, scheduled)
            return False

        emailed = self.email_service.send_alert(display_name, ticker, previous, scheduled)
        self._store(ticker, display_name, scheduled)
        logger.info(
            "classification changed for %s: %s → %s (emailed=%s)",
            ticker,
            previous or "—",
            scheduled,
            emailed,
        )
        return True

    def apply_scheduled(self, symbol: str, name: str, new_cat: str) -> bool:
        ticker = (symbol or "").strip().upper()
        display_name = (name or self._names.get(ticker) or ticker).strip()
        old_cat = self._categories.get(ticker) or current_status(ticker) or ""
        return self.check_and_alert_changes(ticker, display_name, old_cat, new_cat)

    def sync_from_source(self) -> list[dict[str, Any]]:
        """Re-read the scheduled universe file and alert when a stored category drifted."""

        from app.services.shariah import compliance_universe as load_universe

        previous = dict(self._categories)
        load_universe.cache_clear()
        self._categories = previous
        return self.sync_scheduled(load_universe())

    def sync_scheduled(self, items: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        """Apply newly scheduled classifications and return the rows that changed."""

        changes: list[dict[str, Any]] = []
        for item in items:
            symbol, name, new_cat = _row_fields(item)
            if not symbol or not new_cat:
                continue
            old_cat = self._categories.get(symbol) or current_status(symbol) or ""
            if not self.check_and_alert_changes(symbol, name, old_cat, new_cat):
                continue
            changes.append(
                {
                    "symbol": symbol,
                    "name": self._names.get(symbol, name),
                    "old_category": normalize_category(old_cat),
                    "new_category": normalize_category(new_cat),
                }
            )
        return changes

    def stored_category(self, symbol: str) -> str | None:
        ticker = (symbol or "").strip().upper()
        return self._categories.get(ticker)

    def _store(self, symbol: str, name: str, category: str) -> None:
        self._categories[symbol] = category
        if name:
            self._names[symbol] = name
        apply_status_overlay(symbol, category)


def normalize_category(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    mapped = _STATUS_ALIASES.get(raw) or _STATUS_ALIASES.get(raw.upper())
    return mapped or raw.upper()


def _row_fields(item: Mapping[str, Any]) -> tuple[str, str, str]:
    symbol = str(item.get("symbol") or "").strip().upper()
    name = str(
        item.get("name")
        or item.get("companyNameAr")
        or item.get("companyNameEn")
        or symbol
    ).strip()
    category = normalize_category(
        item.get("currentStatus")
        or item.get("current_status")
        or item.get("status")
        or item.get("category")
        or item.get("new_cat")
    )
    return symbol, name, category
