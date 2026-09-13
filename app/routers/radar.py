import logging

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.exceptions import TickChartNotConfiguredError
from app.models.schemas import RadarLiveResponse, TriggerTestAlertResponse
from app.services.telegram_alert_bot import TelegramAlertBot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/radar", tags=["radar"])

_TEST_ALERT_DETAILS = (
    "رصد حجم تداول غير طبيعي مع تراكم تدفق سيولة مؤسسي إيجابي."
)


@router.get("/live/{symbol}", response_model=RadarLiveResponse)
async def get_live_liquidity_radar(
    symbol: str,
    request: Request,
    interval: str = Query(default="1d", description="kept for compatibility; live radar uses TickChart ticks"),
    limit: int = Query(default=100, ge=1, le=2000),
) -> RadarLiveResponse:
    """Return the latest liquidity/trap signal from TickChart ticks and depth."""

    del interval, limit
    feed = getattr(request.app.state, "tickchart", None)
    if feed is None or not getattr(feed, "enabled", False):
        raise TickChartNotConfiguredError()

    ticker = symbol.strip().upper()
    report = await feed.ensure_radar(ticker)
    if report.get("live_quote"):
        telegram = getattr(request.app.state, "telegram", None)
        if telegram is not None:
            try:
                await telegram.send_radar_event(report)
            except Exception:
                logger.exception("failed to send telegram radar event for %s", ticker)

    return RadarLiveResponse(
        symbol=str(report.get("symbol") or ticker),
        success=True,
        source="TickChart",
        analysis=report,
    )


@router.post("/trigger-test-alert", response_model=TriggerTestAlertResponse)
async def trigger_test_alert(
    request: Request,
    symbol: str = Query(..., min_length=1, max_length=12, description="رمز السهم مثل 4030"),
    name: str = Query(..., min_length=1, max_length=80, description="اسم الشركة"),
    signal: str = Query(..., min_length=1, max_length=80, description="نوع الإشارة مثل دخول مؤسسي أو فخ سعري"),
) -> TriggerTestAlertResponse:
    """مسار تجريبي لاختبار إرسال التنبيه الفوري عبر تيليجرام."""

    bot = _alert_bot(request)
    sent = await bot.send_intraday_alert(
        symbol=symbol.strip().upper(),
        symbol_name=name.strip(),
        signal_type=signal.strip(),
        details=_TEST_ALERT_DETAILS,
    )
    if not sent:
        raise HTTPException(
            status_code=503,
            detail=(
                "تعذر إرسال التنبيه. أنشئ بوتاً عبر @BotFather ثم أضف "
                "TELEGRAM_BOT_TOKEN و TELEGRAM_CHAT_ID في ملف .env"
            ),
        )
    return TriggerTestAlertResponse(
        success=True,
        message="تم إرسال التنبيه التجريبي عبر تيليجرام بنجاح.",
    )


def _alert_bot(request: Request) -> TelegramAlertBot:
    bot = getattr(request.app.state, "telegram_alerts", None)
    if bot is not None and callable(getattr(bot, "send_intraday_alert", None)):
        return bot
    telegram = getattr(request.app.state, "telegram", None)
    inner = getattr(telegram, "alerts", None) or getattr(telegram, "_intraday", None)
    if inner is not None and callable(getattr(inner, "send_intraday_alert", None)):
        return inner
    settings = getattr(request.app.state, "settings", None)
    return TelegramAlertBot(settings)
