from fastapi import APIRouter

from app.routers import alerts, analyze, compliance, health, liquidity, market, preopen, quotes, radar, recovery, screener, smart_money, tickchart, watchlist, ws

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(quotes.router)
api_router.include_router(liquidity.router)
api_router.include_router(alerts.router)
api_router.include_router(watchlist.router)
api_router.include_router(screener.router)
api_router.include_router(analyze.router)
api_router.include_router(radar.router)
api_router.include_router(tickchart.router)
api_router.include_router(compliance.router)
api_router.include_router(market.router)
api_router.include_router(preopen.router)
api_router.include_router(smart_money.router)
api_router.include_router(recovery.router)
api_router.include_router(ws.router)
