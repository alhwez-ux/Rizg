from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx

from app.core.config import Settings
from app.models.alert import AlertKind, LiquidityAlert
from app.models.trade import TradeResult, TradeSide

logger = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org"
_ZERO = Decimal("0")


@dataclass
class IntervalReport:
    """Aggregated money-flow totals for one symbol over a reporting window."""

    symbol: str
    interval_minutes: int
    inflow: Decimal = _ZERO
    outflow: Decimal = _ZERO
    net_flow: Decimal = _ZERO
    buy_volume: Decimal = _ZERO
    sell_volume: Decimal = _ZERO
    trade_count: int = 0
    last_price: Decimal | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None


class TelegramBot:
    """Queues trades and sends one Arabic summary per interval instead of instant alerts."""

    def __init__(self, settings: Settings) -> None:
        self._token = settings.telegram_bot_token.strip()
        self._chat_id = settings.telegram_chat_id.strip()
        self._interval = timedelta(minutes=settings.telegram_report_interval_minutes)
        self._interval_minutes = settings.telegram_report_interval_minutes
        self._symbols = {
            item.strip().upper()
            for item in settings.telegram_report_symbols
            if item.strip()
        }
        self._client: httpx.AsyncClient | None = None
        self._buckets: dict[str, IntervalReport] = {}
        self._guard = threading.RLock()
        self._last_flush_at: datetime | None = None
        self._flush_task: asyncio.Task[None] | None = None
        self._running = False

    @property
    def enabled(self) -> bool:
        return bool(self._token) and _is_chat_id(self._chat_id)

    @property
    def interval_minutes(self) -> int:
        return self._interval_minutes

    async def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        if self._token and not _is_chat_id(self._chat_id):
            logger.warning(
                "Telegram bot token is set but TELEGRAM_CHAT_ID is missing or invalid; reports will not be sent"
            )
            return
        if not self.enabled:
            return
        logger.info(
            "Telegram interval reports enabled every %s minutes",
            self._interval_minutes,
        )
        if self._flush_task is None:
            self._running = True
            self._flush_task = asyncio.create_task(self._flush_loop(), name="telegram-report-flush")

    async def aclose(self) -> None:
        self._running = False
        task = self._flush_task
        self._flush_task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def record_trade(self, result: TradeResult) -> None:
        if not self.enabled:
            return
        ticker = result.symbol.upper()
        if self._symbols and ticker not in self._symbols:
            return

        inflow = result.money_flow if result.side is TradeSide.BUY else _ZERO
        outflow = abs(result.money_flow) if result.side is TradeSide.SELL else _ZERO
        buy_volume = result.volume if result.side is TradeSide.BUY else _ZERO
        sell_volume = result.volume if result.side is TradeSide.SELL else _ZERO

        with self._guard:
            bucket = self._buckets.get(ticker)
            if bucket is None:
                bucket = IntervalReport(symbol=ticker, interval_minutes=self._interval_minutes)
                self._buckets[ticker] = bucket
            bucket.inflow += inflow
            bucket.outflow += outflow
            bucket.net_flow += result.money_flow
            bucket.buy_volume += buy_volume
            bucket.sell_volume += sell_volume
            bucket.trade_count += 1
            bucket.last_price = result.price

    def pending_reports(self) -> list[IntervalReport]:
        with self._guard:
            return [self._clone(bucket) for bucket in self._buckets.values()]

    def format_interval_report(self, report: IntervalReport) -> str:
        if report.net_flow > 0:
            regime = "🚀 تراكم"
        elif report.net_flow < 0:
            regime = "⚠️ تصريف"
        else:
            regime = "توازن"

        return (
            "ملخص سيولة دوري\n"
            "━━━━━━━━━━━━━━\n"
            f"فترة التقرير: {_period_label(report.interval_minutes)}\n"
            f"اسم السهم: <code>{report.symbol}</code>\n"
            f"كمية الشراء: {_qty(report.buy_volume)}\n"
            f"كمية البيع: {_qty(report.sell_volume)}\n"
            f"إجمالي سيولة الشراء: {_sar(report.inflow)}\n"
            f"إجمالي سيولة البيع: {_sar(report.outflow)}\n"
            f"صافي التدفق النهائي: <b>{_sar(report.net_flow)}</b>\n"
            f"حالة السهم: {regime}"
        )

    def format_liquidity_alert(self, alert: LiquidityAlert) -> str:
        accumulating = alert.kind in {AlertKind.NET_FLOW_SPIKE, AlertKind.INFLOW_SURGE} or (
            alert.kind is not AlertKind.OUTFLOW_SURGE and alert.window_net_flow >= 0
        )
        if accumulating:
            regime = "🚀 دخول سيولة قوي (تراكم)"
        else:
            regime = "⚠️ خروج سيولة (تصريف)"

        return (
            "تنبيه سيولة لحظي\n"
            "━━━━━━━━━━━━━━\n"
            f"اسم السهم: <code>{alert.symbol}</code>\n"
            f"حالة السيولة: {regime}\n"
            f"صافي التدفق اللحظي: <b>{_sar(alert.window_net_flow)}</b>\n"
            f"إجمالي الشراء: {_sar(alert.session_inflow)}\n"
            f"إجمالي البيع: {_sar(alert.session_outflow)}"
        )

    async def send_liquidity_alert(self, alert: LiquidityAlert) -> bool:
        return await self.send_message(self.format_liquidity_alert(alert))

    async def flush_reports(self, *, force: bool = False) -> int:
        now = datetime.now(timezone.utc)
        if not force and self._last_flush_at is not None and now - self._last_flush_at < self._interval:
            return 0

        with self._guard:
            buckets = list(self._buckets.values())
            self._buckets = {}

        sent = 0
        leftover: list[IntervalReport] = []
        for bucket in buckets:
            if bucket.trade_count == 0:
                continue
            bucket.ended_at = now
            ok = await self.send_message(self.format_interval_report(bucket))
            if ok:
                sent += 1
            else:
                leftover.append(bucket)

        if leftover:
            with self._guard:
                for bucket in leftover:
                    existing = self._buckets.get(bucket.symbol)
                    if existing is None:
                        self._buckets[bucket.symbol] = bucket
                    else:
                        existing.inflow += bucket.inflow
                        existing.outflow += bucket.outflow
                        existing.net_flow += bucket.net_flow
                        existing.buy_volume += bucket.buy_volume
                        existing.sell_volume += bucket.sell_volume
                        existing.trade_count += bucket.trade_count
                        existing.last_price = bucket.last_price or existing.last_price

        if sent or force:
            self._last_flush_at = now
        return sent

    async def send_message(self, text: str) -> bool:
        if not self.enabled:
            return False
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        url = f"{_TELEGRAM_API}/bot{self._token}/sendMessage"
        try:
            response = await self._client.post(
                url,
                json={
                    "chat_id": self._chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
            response.raise_for_status()
            payload = response.json()
            if not payload.get("ok"):
                logger.warning("telegram API rejected message: %s", payload)
                return False
            return True
        except httpx.HTTPError:
            logger.warning("telegram send failed", exc_info=True)
            return False

    async def _flush_loop(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(self._interval.total_seconds())
                if not self._running:
                    break
                try:
                    sent = await self.flush_reports()
                    if sent:
                        logger.info("telegram sent %s interval report(s)", sent)
                except Exception:
                    logger.exception("telegram interval flush failed")
        except asyncio.CancelledError:
            logger.info("telegram report loop cancelled")
            raise

    @staticmethod
    def _clone(bucket: IntervalReport) -> IntervalReport:
        return IntervalReport(
            symbol=bucket.symbol,
            interval_minutes=bucket.interval_minutes,
            inflow=bucket.inflow,
            outflow=bucket.outflow,
            net_flow=bucket.net_flow,
            buy_volume=bucket.buy_volume,
            sell_volume=bucket.sell_volume,
            trade_count=bucket.trade_count,
            last_price=bucket.last_price,
            started_at=bucket.started_at,
            ended_at=bucket.ended_at,
        )


def _is_chat_id(value: str) -> bool:
    if not value:
        return False
    return value.lstrip("-").isdigit()


def _sar(value: Decimal) -> str:
    quantized = value.quantize(Decimal("0.01"))
    sign = "+" if quantized > 0 else ""
    formatted = f"{quantized:,.2f}"
    return f"{sign}{formatted} ر.س"


def _qty(value: Decimal) -> str:
    quantized = value.quantize(Decimal("0.01"))
    formatted = f"{quantized:,.2f}".rstrip("0").rstrip(".")
    return formatted


def _period_label(minutes: int) -> str:
    if minutes == 15:
        return "ملخص آخر ربع ساعة"
    if minutes == 60:
        return "ملخص آخر ساعة"
    if minutes % 60 == 0:
        hours = minutes // 60
        return f"ملخص آخر {hours} ساعات"
    return f"ملخص آخر {minutes} دقيقة"
