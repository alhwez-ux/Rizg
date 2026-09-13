import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.core.config import Settings, get_settings
from app.core.database import close_store, init_store
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware, register_exception_handlers
from app.routers import api_router
from app.services.alerts import AlertService
from app.services.broadcaster import ConnectionManager
from app.services.liquidity import LiquidityService
from app.services.liquidity_engine import LiquidityRadarEngine
from app.services.market_data import MarketDataService
from app.services.screener import ScreenerService
from app.services.email_alert_service import EmailAlertService
from app.services.financial_sync import FinancialSyncService
from app.services.financial_sync_service import FinancialSyncService as MarketFinancialSyncService
from app.services.ranking_store import RankingStore
from app.services.telegram_bot import TelegramBot
from app.services.tick_feed import MockTickFeed
from app.services.tickchart_integration import DEFAULT_TICKCHART_SYMBOLS, TickChartFeed
from app.services.tickchart_autosync import TickChartAutoSync
from app.services.tasi_scheduler import TasiMarketScheduler
from app.services.watchlist import WatchlistService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    store = init_store(settings)
    broadcaster = ConnectionManager()
    broadcaster.bind_loop(asyncio.get_running_loop())
    liquidity = LiquidityService()
    liquidity_engine = LiquidityRadarEngine()
    telegram = TelegramBot(settings)
    if settings.telegram_enabled:
        await telegram.start()
    alerts = AlertService(
        settings,
        broadcaster,
        telegram=telegram,
    )
    watchlist = WatchlistService(
        initial=settings.tickchart_symbols or settings.sahmk_symbols or DEFAULT_TICKCHART_SYMBOLS
    )
    screener = ScreenerService(settings, watchlist, liquidity_engine=liquidity_engine)
    tickchart = TickChartFeed(
        liquidity_engine,
        broadcaster,
        settings,
        alerts=alerts,
        watchlist=watchlist,
        screener=screener,
    )
    mock_feed = MockTickFeed(liquidity_engine, broadcaster, settings, alerts=alerts)
    tick_feed = tickchart if tickchart.enabled else mock_feed
    tickchart_autosync = TickChartAutoSync(tickchart, settings)
    tickchart.bind_autosync(tickchart_autosync)
    market_data = MarketDataService(store, liquidity, broadcaster)
    financial_sync = FinancialSyncService(settings)
    ranking_store = RankingStore()
    email_alerts = EmailAlertService(settings)
    market_financial_sync = MarketFinancialSyncService(
        settings,
        store=ranking_store,
        email_service=email_alerts,
        provider=lambda: [],
        enable_scheduler=False,
    )
    tasi_scheduler = TasiMarketScheduler(
        settings,
        sahm=None,
        telegram=telegram,
        ranking_sync=None,
        watchlist=watchlist,
        tickchart=tickchart,
        enable_scheduler=settings.tasi_scheduler_enabled,
    )
    app.state.store = store
    app.state.broadcaster = broadcaster
    app.state.liquidity = liquidity
    app.state.liquidity_engine = liquidity_engine
    app.state.telegram = telegram
    app.state.telegram_alerts = telegram.alerts
    app.state.alerts = alerts
    app.state.watchlist = watchlist
    app.state.screener = screener
    app.state.live_feed = None
    app.state.tickchart = tickchart
    app.state.tickchart_autosync = tickchart_autosync
    app.state.tick_feed = tick_feed
    app.state.market_data = market_data
    app.state.sahm = None
    app.state.sahm_analysis = None
    app.state.financial_sync = financial_sync
    app.state.ranking_store = ranking_store
    app.state.market_financial_sync = market_financial_sync
    app.state.sync_service = market_financial_sync
    app.state.email_alerts = email_alerts
    app.state.tasi_scheduler = tasi_scheduler
    app.state.tadawul_daily_sync = None

    if tickchart.enabled:
        await tickchart.start()
    if tickchart_autosync.enabled:
        await tickchart_autosync.start()
    elif settings.enable_mock_feed and not settings.tickchart_enabled:
        await mock_feed.start()

    tasi_scheduler.bind_loop(asyncio.get_running_loop())
    tasi_scheduler.start()

    yield

    tasi_scheduler.shutdown()
    await tickchart_autosync.stop()
    await tickchart.stop()
    await mock_feed.stop()
    await telegram.aclose()
    await broadcaster.close_all()
    await close_store()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="Real-time stock liquidity tracking API",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.state.settings = settings

    app.add_middleware(RequestContextMiddleware)
    cors_origins = list(settings.cors_origins)
    for origin in (
        "https://rizg.vercel.app",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ):
        if origin not in cors_origins:
            cors_origins.append(origin)
    allow_credentials = "*" not in cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
