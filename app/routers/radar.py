import logging

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.exceptions import InvalidSymbolError, SahmApiError
from app.models.schemas import RadarLiveResponse, TriggerTestAlertResponse
from app.services.liquidity_engine import LiquidityRadarEngine
from app.services.sahm_data_provider import SahmDataProvider
from app.services.sahm_live_market import overlay_quote_on_report
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
    interval: str = Query(default="1d", description="Sahm candle interval: 1d, 1w, 1h, 60m, 30m"),
    limit: int = Query(default=100, ge=1, le=2000),
) -> RadarLiveResponse:
    """Fetch Sahm candles automatically and return the latest liquidity/trap signal."""

    provider: SahmDataProvider | None = getattr(request.app.state, "sahm", None)
    if provider is None:
        raise HTTPException(status_code=503, detail="مزود بيانات Sahm غير مهيأ")
    if not provider.enabled:
        raise HTTPException(status_code=503, detail="SAHM_API_KEY is missing; cannot fetch live radar")

    try:
        frame = await provider.fetch_candles(symbol, interval=interval)
        quote = await provider.fetch_quote(symbol)
    except InvalidSymbolError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except SahmApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if frame is None or frame.empty:
        raise HTTPException(
            status_code=404,
            detail=f"تعذر جلب بيانات الشموع للسهم {symbol} من Sahm API",
        )

    capped = frame.tail(limit).reset_index(drop=True)
    engine = LiquidityRadarEngine(capped)
    report = overlay_quote_on_report(engine.get_latest_signal_report(), quote)
    analysis = getattr(request.app.state, "sahm_analysis", None)
    if analysis is not None:
        await analysis.ensure_seeded(symbol, interval=interval, limit=limit)

    telegram = getattr(request.app.state, "telegram", None)
    if telegram is not None:
        try:
            await telegram.send_radar_event(report)
        except Exception:
            logger.exception("failed to send telegram radar event for %s", symbol)

    ticker = str(report.get("symbol") or symbol).upper()
    return RadarLiveResponse(
        symbol=ticker,
        success=True,
        source="Sahm API",
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
