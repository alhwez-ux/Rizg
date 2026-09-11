"""Send a one-off Telegram message using TELEGRAM_* values from .env."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx

from app.core.config import Settings
from app.services.telegram_bot import TelegramBot


TEST_TEXT = (
    "اختبار بوت رزق\n"
    "━━━━━━━━━━━━━━\n"
    "إذا وصلت هذه الرسالة فإعدادات تيليجرام تعمل."
)


async def main() -> int:
    settings = Settings()
    bot = TelegramBot(settings)
    chat_id = settings.telegram_chat_id.strip()

    if not bot.enabled:
        print("FAIL: Telegram is not enabled. Check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
        return 1

    token = settings.telegram_bot_token.strip()
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": TEST_TEXT,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
            payload = response.json()
        except httpx.HTTPError as exc:
            print(f"FAIL: network error talking to Telegram ({type(exc).__name__})")
            return 1

    if payload.get("ok"):
        message_id = payload.get("result", {}).get("message_id")
        print(f"OK: test message delivered to chat {chat_id} (message_id={message_id})")
        sent = await bot.send_message("تأكيد ثانٍ من خدمة TelegramBot داخل رزق.")
        print("OK: TelegramBot.send_message succeeded" if sent else "FAIL: TelegramBot.send_message returned False")
        await bot.aclose()
        return 0 if sent else 1

    print(
        "FAIL: Telegram rejected the message "
        f"(error_code={payload.get('error_code')}, description={payload.get('description')})"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
