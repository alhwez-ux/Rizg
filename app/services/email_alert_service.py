from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

TARGET_EMAIL = "alhwez@gmail.com"

_CATEGORY_AR = {
    "PURE": "نقي",
    "MIXED": "مختلط",
    "PROHIBITED": "محرّم",
}

_STRUCTURAL_UP = ("قلاع النمو",)
_STRUCTURAL_DOWN = ("الخاسرة", "ضعيفة النمو")


class EmailAlertService:
    """Compares stored vs new ranking categories and emails structural changes immediately."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self.smtp_server = (self._settings.smtp_server or "smtp.gmail.com").strip()
        self.smtp_port = int(self._settings.smtp_port or 587)
        self.sender_email = (self._settings.sender_email or "").strip()
        self.sender_password = (self._settings.sender_password or "").strip()
        self.target_email = (self._settings.alert_recipient_email or TARGET_EMAIL).strip() or TARGET_EMAIL

    @property
    def enabled(self) -> bool:
        return bool(self.sender_email and self.sender_password and self.target_email)

    def send_alert(
        self,
        company_name: str,
        symbol: str,
        old_category: str,
        new_category: str,
    ) -> bool:
        """إرسال تنبيه بالبريد الإلكتروني عند تغير تصنيف الشركة."""

        previous = _label(old_category)
        current = _label(new_category)
        if previous == current:
            return False
        if not self.enabled:
            logger.info(
                "SMTP is not configured; skipped ranking alert for %s (%s → %s)",
                symbol,
                previous,
                current,
            )
            return False

        ticker = (symbol or "").strip().upper()
        name = (company_name or ticker).strip() or ticker
        message = self._build_message(name, ticker, previous, current)
        try:
            self._deliver(message)
        except Exception:
            logger.exception("failed to send ranking alert for %s", ticker)
            return False
        logger.info("sent ranking alert for %s (%s → %s) to %s", ticker, previous, current, self.target_email)
        return True

    def _build_message(self, company_name: str, symbol: str, old_category: str, new_category: str) -> MIMEMultipart:
        subject = f"🚨 رادار رزق: تحديث وتغير تصنيف السهم {company_name} ({symbol})"
        html_content = f"""
        <div dir="rtl" style="font-family: Arial, sans-serif; padding: 20px; background-color: #0f172a; color: #f8fafc; border-radius: 12px;">
            <h2 style="color: #38bdf8; border-bottom: 2px solid #334155; padding-bottom: 10px;">تنبيه تغير مصفوفة السيولة والنمو</h2>
            <p>أهلاً بك أبو نايف،</p>
            <p>رصد محرك التحليل المالي في نظام <strong>رزق</strong> تغيراً جوهرياً في أداء وتصنيف الشركة التالية:</p>
            <div style="background: #1e293b; padding: 15px; border-radius: 8px; margin: 15px 0; border: 1px solid #334155;">
                <p style="margin: 5px 0;"><strong>اسم الشركة:</strong> {company_name} ({symbol})</p>
                <p style="margin: 5px 0;"><strong>التصنيف السابق:</strong> <span style="color: #94a3b8;">{old_category}</span></p>
                <p style="margin: 5px 0;"><strong>التصنيف الجديد:</strong> <span style="color: #10b981; font-weight: bold;">{new_category}</span></p>
            </div>
            <p style="font-size: 12px; color: #64748b; margin-top: 20px;">هذا البريد مرسل بشكل آلي من نظام رادار السوق السعودي (تاسي) - مشروع رزق.</p>
        </div>
        """
        plain = (
            f"تنبيه رزق: تغير تصنيف {company_name} ({symbol})\n"
            f"التصنيف السابق: {old_category}\n"
            f"التصنيف الجديد: {new_category}\n"
        )
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = self.sender_email
        message["To"] = self.target_email
        message.attach(MIMEText(plain, "plain", "utf-8"))
        message.attach(MIMEText(html_content, "html", "utf-8"))
        return message

    def _deliver(self, message: MIMEMultipart) -> None:
        with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=20) as server:
            server.ehlo()
            if self.smtp_port != 465:
                server.starttls()
                server.ehlo()
            server.login(self.sender_email, self.sender_password)
            server.sendmail(self.sender_email, self.target_email, message.as_string())


def is_structural_change(old_category: str, new_category: str) -> bool:
    previous = _label(old_category)
    current = _label(new_category)
    if not previous or not current or previous == current:
        return False
    if any(token in current for token in _STRUCTURAL_UP):
        return True
    if any(token in current for token in _STRUCTURAL_DOWN):
        return True
    if any(token in previous for token in _STRUCTURAL_UP + _STRUCTURAL_DOWN):
        return True
    return previous != current


def _label(category: str) -> str:
    raw = (category or "").strip()
    if not raw:
        return ""
    return _CATEGORY_AR.get(raw.upper(), raw)
