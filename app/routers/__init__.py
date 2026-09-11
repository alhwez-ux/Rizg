from fastapi import APIRouter

from app.routers import alerts, health, liquidity, quotes, screener, watchlist, ws

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(quotes.router)
api_router.include_router(liquidity.router)
api_router.include_router(alerts.router)
api_router.include_router(watchlist.router)
api_router.include_router(screener.router)
api_router.include_router(ws.router)
