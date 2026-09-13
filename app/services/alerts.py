from __future__ import annotations

import logging
import threading
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.core.config import Settings
from app.models.alert import AlertKind, LiquidityAlert
from app.models.trade import TradeResult, TradeSide
from app.services.broadcaster import ConnectionManager
from app.services.telegram_bot import TelegramBot

logger = logging.getLogger(__name__)

_KIND_PRIORITY = (
    AlertKind.NET_FLOW_SPIKE,
    AlertKind.OUTFLOW_SURGE,
    AlertKind.INFLOW_SURGE,
    AlertKind.VOLUME_SURGE,
)

_KIND_TITLE = {
    AlertKind.NET_FLOW_SPIKE: "إشارة دخول 🚀",
    AlertKind.OUTFLOW_SURGE: "إشارة خروج / تصريف ⚠️",
    AlertKind.INFLOW_SURGE: "إشارة دخول 🚀",
    AlertKind.VOLUME_SURGE: "ارتفاع مفاجئ في الكمية",
}


@dataclass
class _Sample:
    at: datetime
    inflow: Decimal
    outflow: Decimal
    volume: Decimal
    money_flow: Decimal


class AlertService:
    """Detects short-window liquidity spikes for the live dashboard.

    Telegram queues these trades into interval summaries. Instant radar/trap
    alerts are sent separately from LiquidityRadarEngine reports.
    """

    def __init__(
        self,
        settings: Settings,
        broadcaster: ConnectionManager | None = None,
        telegram: TelegramBot | None = None,
    ) -> None:
        self._settings = settings
        self._broadcaster = broadcaster
        self._telegram = telegram
        self._windows: dict[str, deque[_Sample]] = defaultdict(deque)
        self._last_fired: dict[tuple[str, AlertKind], datetime] = {}
        self._history: deque[LiquidityAlert] = deque(maxlen=settings.alert_history_limit)
        self._guard = threading.RLock()

    def recent(self, symbol: str | None = None) -> list[LiquidityAlert]:
        with self._guard:
            alerts = list(self._history)
        if symbol is None:
            return list(reversed(alerts))
        ticker = symbol.upper()
        return list(reversed([alert for alert in alerts if alert.symbol == ticker]))

    async def handle_trade(self, result: TradeResult) -> LiquidityAlert | None:
        if self._telegram is not None:
            self._telegram.record_trade(result)
        alert = self._evaluate(result)
        if alert is None:
            return None
        if self._broadcaster is not None:
            try:
                await self._broadcaster.broadcast(alert.symbol, alert.as_json())
            except Exception:
                logger.exception("failed to broadcast alert for %s", alert.symbol)
        return alert

    def _evaluate(self, result: TradeResult) -> LiquidityAlert | None:
        now = result.timestamp or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        inflow = result.money_flow if result.side is TradeSide.BUY else Decimal("0")
        outflow = abs(result.money_flow) if result.side is TradeSide.SELL else Decimal("0")
        volume = result.volume if result.side is not None else Decimal("0")

        window = timedelta(seconds=self._settings.alert_window_seconds)
        with self._guard:
            samples = self._windows[result.symbol]
            samples.append(
                _Sample(
                    at=now,
                    inflow=inflow,
                    outflow=outflow,
                    volume=volume,
                    money_flow=result.money_flow,
                )
            )
            cutoff = now - window
            while samples and samples[0].at < cutoff:
                samples.popleft()

            window_inflow = sum((sample.inflow for sample in samples), Decimal("0"))
            window_outflow = sum((sample.outflow for sample in samples), Decimal("0"))
            window_volume = sum((sample.volume for sample in samples), Decimal("0"))
            window_net = sum((sample.money_flow for sample in samples), Decimal("0"))
            turnover = window_inflow + window_outflow
            buy_ratio = (window_inflow / turnover) if turnover > 0 else None
            sell_ratio = (window_outflow / turnover) if turnover > 0 else None
            aggressive = self._settings.signal_aggressive_ratio

            triggered: list[AlertKind] = []
            if (
                window_net >= self._settings.alert_net_flow_threshold
                and buy_ratio is not None
                and buy_ratio >= aggressive
            ):
                triggered.append(AlertKind.NET_FLOW_SPIKE)
            if (
                window_net <= -self._settings.alert_net_flow_threshold
                and sell_ratio is not None
                and sell_ratio >= aggressive
            ):
                triggered.append(AlertKind.OUTFLOW_SURGE)
            if (
                window_inflow >= self._settings.alert_inflow_threshold
                and window_net > 0
                and buy_ratio is not None
                and buy_ratio >= aggressive
            ):
                triggered.append(AlertKind.INFLOW_SURGE)
            if (
                window_outflow >= self._settings.alert_inflow_threshold
                and window_net < 0
                and sell_ratio is not None
                and sell_ratio >= aggressive
            ):
                triggered.append(AlertKind.OUTFLOW_SURGE)
            if window_volume >= self._settings.alert_volume_threshold:
                triggered.append(AlertKind.VOLUME_SURGE)
            if not triggered:
                return None

            kind = next(item for item in _KIND_PRIORITY if item in triggered)
            last = self._last_fired.get((result.symbol, kind))
            cooldown = timedelta(seconds=self._settings.alert_cooldown_seconds)
            if last is not None and now - last < cooldown:
                return None

            self._last_fired[(result.symbol, kind)] = now
            alert = LiquidityAlert(
                id=uuid.uuid4().hex,
                symbol=result.symbol,
                kind=kind,
                title=_KIND_TITLE[kind],
                message=_format_message(result.symbol, kind, window_net, result.session.inflow, result.session.outflow),
                window_seconds=self._settings.alert_window_seconds,
                window_inflow=window_inflow,
                window_outflow=window_outflow,
                window_volume=window_volume,
                window_net_flow=window_net,
                session_inflow=result.session.inflow,
                session_outflow=result.session.outflow,
                last_price=result.price,
                timestamp=now,
                cooldown_seconds=self._settings.alert_cooldown_seconds,
            )
            self._history.append(alert)
            return alert


def _format_message(
    symbol: str,
    kind: AlertKind,
    window_net: Decimal,
    session_inflow: Decimal,
    session_outflow: Decimal,
) -> str:
    return (
        f"اسم السهم: {symbol} | "
        f"حالة السيولة: {_KIND_TITLE[kind]} | "
        f"صافي التدفق اللحظي: {window_net:.2f} ر.س | "
        f"إجمالي الشراء: {session_inflow:.2f} ر.س | "
        f"إجمالي البيع: {session_outflow:.2f} ر.س"
    )
