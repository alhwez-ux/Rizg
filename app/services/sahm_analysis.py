from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from app.core.exceptions import InvalidSymbolError, SahmApiError, SymbolNotFoundError
from app.models.quote import Quote
from app.models.schemas import AnalyzeResponse, CandleOut, MarketLevelsOut
from app.models.trade import SessionFlow
from app.services.liquidity_engine import LiquidityEngine, LiquidityRadarEngine
from app.services.market_data import MarketDataService
from app.services.sahm_data_provider import SahmDataProvider, normalize_sahm_symbol
from app.services.telegram_bot import TelegramBot

logger = logging.getLogger(__name__)


class SahmAnalysisService:
    """Fetch TASI candles from Sahm and run them through LiquidityRadarEngine."""

    def __init__(
        self,
        provider: SahmDataProvider,
        engine: LiquidityEngine,
        *,
        market_data: MarketDataService | None = None,
        telegram: TelegramBot | None = None,
    ) -> None:
        self._provider = provider
        self._engine = engine
        self._market_data = market_data
        self._telegram = telegram
        self._seeded: set[str] = set()
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self._provider.enabled

    async def analyze(
        self,
        symbol: str,
        *,
        interval: str = "1d",
        limit: int = 100,
    ) -> AnalyzeResponse:
        ticker, frame = await self._load_candles(symbol, interval=interval, limit=limit)
        radar = LiquidityRadarEngine()
        radar.ingest(frame)
        await self._notify_radar(radar, ticker)
        await self._seed_shared(ticker, frame)
        await self._store_last_bar(ticker, frame)
        session = radar.session_snapshot(ticker)
        levels = radar.levels_snapshot(ticker)
        return AnalyzeResponse(
            symbol=ticker,
            interval=str(frame["interval"].iloc[-1]) if "interval" in frame.columns else interval,
            source="sahm",
            bars=int(len(frame)),
            session=session,
            levels=MarketLevelsOut(
                symbol=levels.symbol,
                vwap=levels.vwap,
                atr=levels.atr,
                last_price=levels.last_price,
                session_high=levels.session_high,
                session_low=levels.session_low,
                book_pressure=levels.book_pressure,
            ),
            candles=_candles_out(frame),
        )

    async def _notify_radar(self, radar: LiquidityRadarEngine, ticker: str) -> None:
        if self._telegram is None:
            return
        try:
            report = radar.get_latest_signal_report(ticker)
            await self._telegram.send_radar_event(report)
        except Exception:
            logger.exception("failed to send telegram radar event for %s", ticker)

    async def ensure_seeded(self, symbol: str, *, interval: str = "1d", limit: int = 100) -> SessionFlow | None:
        """Load Sahm candles into the shared engine the first time a symbol is requested."""

        if not self.enabled:
            return None
        try:
            ticker = normalize_sahm_symbol(symbol)
        except InvalidSymbolError:
            return None
        async with self._lock:
            if ticker in self._seeded:
                return self._engine.session_snapshot(ticker)
            existing = self._engine.session_snapshot(ticker)
            if existing.trade_count > 0:
                self._seeded.add(ticker)
                return existing
            try:
                ticker, frame = await self._load_candles(ticker, interval=interval, limit=limit)
            except (SahmApiError, SymbolNotFoundError, InvalidSymbolError) as exc:
                logger.warning("sahm seed skipped for %s: %s", ticker, getattr(exc, "message", exc))
                return None
            self._engine.ingest(frame)
            self._seeded.add(ticker)
        await self._store_last_bar(ticker, frame)
        logger.info("sahm seeded radar engine for %s bars=%s", ticker, len(frame))
        return self._engine.session_snapshot(ticker)

    async def _load_candles(
        self,
        symbol: str,
        *,
        interval: str,
        limit: int,
    ) -> tuple[str, pd.DataFrame]:
        if not self.enabled:
            raise SahmApiError(
                "SAHM_API_KEY is missing; cannot analyze this symbol",
                status_code=503,
                error_code="sahm_not_configured",
            )
        ticker = normalize_sahm_symbol(symbol)
        cap = max(1, min(int(limit), 2000))
        frame = await self._provider.fetch_candles(ticker, interval=interval)
        if frame is None or frame.empty:
            raise SymbolNotFoundError(ticker)
        return ticker, frame.tail(cap).reset_index(drop=True)

    async def _seed_shared(self, ticker: str, frame: pd.DataFrame) -> None:
        async with self._lock:
            if ticker in self._seeded:
                return
            if self._engine.session_snapshot(ticker).trade_count > 0:
                self._seeded.add(ticker)
                return
            self._engine.ingest(frame)
            self._seeded.add(ticker)

    async def _store_last_bar(self, ticker: str, frame: pd.DataFrame) -> None:
        if self._market_data is None or frame.empty:
            return
        row = frame.iloc[-1]
        close = float(row["close"])
        if close <= 0:
            return
        timestamp = _row_timestamp(row)
        volume = float(row["volume"]) if pd.notna(row.get("volume")) else 0.0
        quote = Quote(
            symbol=ticker,
            bid=close,
            ask=close,
            bid_size=0,
            ask_size=0,
            last_price=close,
            volume=max(volume, 0.0),
            timestamp=timestamp,
        )
        try:
            await self._market_data.upsert(quote)
        except Exception:
            logger.warning("failed to cache last Sahm bar for %s", ticker, exc_info=True)


def _candles_out(frame: pd.DataFrame) -> list[CandleOut]:
    rows: list[CandleOut] = []
    for row in frame.itertuples(index=False):
        close = float(getattr(row, "close"))
        rows.append(
            CandleOut(
                timestamp=_value_timestamp(getattr(row, "timestamp", None)),
                open=float(getattr(row, "open", close)),
                high=float(getattr(row, "high", close)),
                low=float(getattr(row, "low", close)),
                close=close,
                volume=float(getattr(row, "volume", 0) or 0),
            )
        )
    return rows


def _row_timestamp(row: Any) -> datetime:
    return _value_timestamp(row["timestamp"] if "timestamp" in row.index else None)


def _value_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    to_pydatetime = getattr(value, "to_pydatetime", None)
    if callable(to_pydatetime):
        return _value_timestamp(to_pydatetime())
    return datetime.now(timezone.utc)
