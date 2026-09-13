from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.services.shariah import company_name_for

logger = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org"
_PLACEHOLDER_TOKENS = {
    "",
    "YOUR_BOT_TOKEN",
    "your_bot_token",
    "your_bot_token_here",
}
_PLACEHOLDER_CHATS = {
    "",
    "YOUR_CHAT_ID",
    "your_chat_id",
    "your_chat_id_here",
}


class TelegramAlertBot:
    """Instant TASI radar/trap alerts to the trader's phone via Telegram Bot API."""

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        self.token = settings.telegram_bot_token.strip()
        self.chat_id = settings.telegram_chat_id.strip()
        self.base_url = f"{_TELEGRAM_API}/bot{self.token}/sendMessage"

    @property
    def enabled(self) -> bool:
        return self.token not in _PLACEHOLDER_TOKENS and _is_chat_id(self.chat_id)

    def format_intraday_alert(
        self,
        symbol: str,
        symbol_name: str,
        signal_type: str,
        details: str,
    ) -> str:
        emoji = "🚨" if "فخ" in signal_type else "⚡"
        name = (symbol_name or symbol).strip() or symbol
        return (
            f"{emoji} <b>رادار السيولة اللحظية (رزق)</b>\n\n"
            f"📌 <b>السهم:</b> {name} ({symbol})\n"
            f"🎯 <b>الإشارة:</b> {signal_type}\n"
            f"💡 <b>التفاصيل:</b> {details}\n\n"
            "⏱️ التوقيت: مباشر من جلسة تاسي"
        )

    async def send_intraday_alert(
        self,
        symbol: str,
        symbol_name: str,
        signal_type: str,
        details: str,
    ) -> bool:
        """إرسال تنبيه لحظي عند رصد دخول مؤسسي أو فخ سعري."""

        if not self.enabled:
            logger.warning("telegram bot token/chat_id are not configured; skipping intraday alert")
            return False

        payload = {
            "chat_id": self.chat_id,
            "text": self.format_intraday_alert(symbol, symbol_name, signal_type, details),
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(self.base_url, json=payload)
            if response.status_code == 200 and response.json().get("ok"):
                logger.info("telegram intraday alert sent for %s", symbol)
                return True
            logger.warning("telegram intraday alert rejected: %s", response.text)
            return False
        except httpx.HTTPError:
            logger.warning("telegram intraday alert failed for %s", symbol, exc_info=True)
            return False


def alert_copy_from_report(report: dict[str, Any]) -> tuple[str, str, str, str]:
    ticker = str(report.get("symbol") or "").upper()
    name = str(report.get("name") or company_name_for(ticker) or ticker)
    trap = report.get("trap") if isinstance(report.get("trap"), dict) else None
    signal = str(report.get("signal") or "neutral")
    reasons = report.get("reasons") if isinstance(report.get("reasons"), list) else []
    details = " — ".join(str(item) for item in reasons if item) or "إشارة لحظية من محرك الرادار"

    if trap:
        signal_type = str(trap.get("label") or "فخ سعري لحظي")
        if "فخ" not in signal_type:
            signal_type = f"فخ سعري: {signal_type}"
        return ticker, name, signal_type, details
    if signal == "entry":
        return ticker, name, "دخول مؤسسي", details
    if signal == "exit":
        return ticker, name, "خروج سيولة", details
    return ticker, name, signal, details


def _is_chat_id(value: str) -> bool:
    if value in _PLACEHOLDER_CHATS:
        return False
    return value.lstrip("-").isdigit()
