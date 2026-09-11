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
from app.services.liquidity_engine import LiquidityEngine
from app.services.market_data import MarketDataService
from app.services.screener import ScreenerService
from app.services.sahmk_feed import SahmkTradeFeed
from app.services.telegram_bot import TelegramBot
from app.services.tick_feed import MockTickFeed
from app.services.watchlist import WatchlistService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    store = init_store(settings)
    broadcaster = ConnectionManager()
    broadcaster.bind_loop(asyncio.get_running_loop())
    liquidity = LiquidityService()
    liquidity_engine = LiquidityEngine()
    telegram = TelegramBot(settings)
    if settings.telegram_enabled:
        await telegram.start()
    alerts = AlertService(
        settings,
        broadcaster,
        telegram=telegram if settings.telegram_enabled else None,
    )
    watchlist = WatchlistService(initial=settings.sahmk_symbols)
    screener = ScreenerService(settings, watchlist, liquidity_engine=liquidity_engine)
    live_feed = SahmkTradeFeed(
        liquidity_engine,
        broadcaster,
        settings,
        alerts=alerts,
        watchlist=watchlist,
        screener=screener,
    )
    mock_feed = MockTickFeed(liquidity_engine, broadcaster, settings, alerts=alerts)
    tick_feed = live_feed if live_feed.enabled else mock_feed

    app.state.store = store
    app.state.broadcaster = broadcaster
    app.state.liquidity = liquidity
    app.state.liquidity_engine = liquidity_engine
    app.state.telegram = telegram
    app.state.alerts = alerts
    app.state.watchlist = watchlist
    app.state.screener = screener
    app.state.live_feed = live_feed
    app.state.tick_feed = tick_feed
    app.state.market_data = MarketDataService(store, liquidity, broadcaster)

    if live_feed.enabled:
        await live_feed.start()
    elif settings.enable_mock_feed:
        await mock_feed.start()

    yield

    await live_feed.stop()
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
    allow_credentials = "*" not in settings.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
