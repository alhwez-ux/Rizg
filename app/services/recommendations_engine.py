from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from typing import Any, Mapping

import numpy as np
import pandas as pd

from app.core.exceptions import SahmApiError
from app.services.company_ranker import MAJOR_TASI_COMPANIES
from app.services.sahm_data_provider import SahmDataProvider
from app.services.shariah import company_name_for, is_prohibited

logger = logging.getLogger(__name__)

SIGNAL_MOMENTUM = "استمرار صعود وقوة سيولة 🚀"
SIGNAL_BOUNCE = "ارتداد إيجابي مؤكد من الدعم 📈"
KIND_MOMENTUM = "momentum"
KIND_BOUNCE = "bounce"
MIN_BARS = 20
SCAN_LIMIT = 12
CANDLE_DAYS = 90
CACHE_TTL_SECONDS = 180.0
MIN_CONFIDENCE = 68

_NAME_BY_SYMBOL = {item["symbol"]: item["name"] for item in MAJOR_TASI_COMPANIES}
_cache: tuple[float, list[dict[str, Any]]] | None = None


class MarketRecommendationsEngine:
    """Scan close/volume/liquidity candles for bounce and momentum setups."""

    def __init__(self, market_candles_data: Mapping[str, pd.DataFrame], names: Mapping[str, str] | None = None):
        self.market_data = dict(market_candles_data or {})
        self._names = dict(names or {})

    def scan_for_opportunities(self) -> list[dict[str, Any]]:
        opportunities: list[dict[str, Any]] = []
        for symbol, frame in self.market_data.items():
            ticker = str(symbol or "").strip().upper()
            if not ticker or is_prohibited(ticker):
                continue
            row = self._evaluate(ticker, frame)
            if row is not None:
                opportunities.append(row)
        opportunities.sort(key=lambda item: int(item.get("confidence_score") or 0), reverse=True)
        return opportunities

    def _evaluate(self, symbol: str, raw: pd.DataFrame) -> dict[str, Any] | None:
        frame = _prepare_frame(raw, symbol)
        if frame is None or len(frame) < MIN_BARS:
            return None
        close = frame["close"]
        volume = frame["volume"]
        high = frame["high"]
        low = frame["low"]
        opened = frame["open"]
        sma20 = close.rolling(20, min_periods=MIN_BARS).mean()
        vol_avg = volume.rolling(20, min_periods=10).mean()
        atr = _average_true_range(high, low, close)
        mfi = _money_flow_index(high, low, close, volume)
        last_close = float(close.iloc[-1])
        prev_close = float(close.iloc[-2])
        last_open = float(opened.iloc[-1])
        last_high = float(high.iloc[-1])
        last_low = float(low.iloc[-1])
        last_sma = float(sma20.iloc[-1]) if pd.notna(sma20.iloc[-1]) else last_close
        last_atr = float(atr.iloc[-1]) if pd.notna(atr.iloc[-1]) else max(last_close * 0.015, 0.05)
        last_mfi = float(mfi.iloc[-1]) if pd.notna(mfi.iloc[-1]) else 50.0
        vol_ratio = float(volume.iloc[-1] / vol_avg.iloc[-1]) if pd.notna(vol_avg.iloc[-1]) and vol_avg.iloc[-1] > 0 else 1.0
        recent_low = float(low.tail(8).min())
        recent_high = float(high.tail(20).max())
        prior_mfi = float(mfi.iloc[-5]) if len(mfi) >= 5 and pd.notna(mfi.iloc[-5]) else last_mfi

        bounce = _bounce_score(
            last_close=last_close,
            prev_close=prev_close,
            last_open=last_open,
            last_high=last_high,
            last_low=last_low,
            last_sma=last_sma,
            last_mfi=last_mfi,
            prior_mfi=prior_mfi,
            vol_ratio=vol_ratio,
            recent_low=recent_low,
            close_series=close,
            sma_series=sma20,
        )
        momentum = _momentum_score(
            last_close=last_close,
            prev_close=prev_close,
            last_sma=last_sma,
            last_mfi=last_mfi,
            vol_ratio=vol_ratio,
            recent_high=recent_high,
            close_series=close,
        )
        if bounce >= momentum and bounce >= MIN_CONFIDENCE:
            kind = KIND_BOUNCE
            signal = SIGNAL_BOUNCE
            score = bounce
            reason = _bounce_reason(vol_ratio, last_mfi, last_close, last_sma)
            target = last_close + max(last_atr * 1.4, last_close * 0.025)
            stop = min(last_close - last_atr, recent_low * 0.995)
        elif momentum >= MIN_CONFIDENCE:
            kind = KIND_MOMENTUM
            signal = SIGNAL_MOMENTUM
            score = momentum
            reason = _momentum_reason(vol_ratio, last_mfi, last_close, last_sma)
            target = last_close + max(last_atr * 1.6, last_close * 0.03)
            stop = last_close - max(last_atr, last_close * 0.015)
        else:
            return None
        if stop >= last_close or target <= last_close:
            return None
        return _opportunity_row(
            symbol=symbol,
            name=self._names.get(symbol) or company_name_for(symbol) or _NAME_BY_SYMBOL.get(symbol, symbol),
            close_price=last_close,
            signal_type=signal,
            signal_kind=kind,
            score=score,
            entry=last_close,
            target=target,
            stop=stop,
            reason=reason,
            volume_ratio=vol_ratio,
            mfi=last_mfi,
        )


def scan_universe() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in MAJOR_TASI_COMPANIES:
        symbol = item["symbol"]
        if is_prohibited(symbol):
            continue
        rows.append(item)
        if len(rows) >= SCAN_LIMIT:
            break
    return rows


async def live_market_recommendations(provider: SahmDataProvider, *, use_cache: bool = True) -> list[dict[str, Any]]:
    """Fetch live daily candles from Sahm and return bounce/momentum opportunities."""

    global _cache
    if not provider.enabled:
        raise SahmApiError(
            "SAHM_API_KEY is missing; cannot scan recommendations",
            status_code=503,
            error_code="sahm_not_configured",
        )
    now = time.monotonic()
    if use_cache and _cache is not None and now - _cache[0] < CACHE_TTL_SECONDS:
        return list(_cache[1])
    universe = scan_universe()
    symbols = [item["symbol"] for item in universe]
    names = {item["symbol"]: item["name"] for item in universe}
    start = date.today() - timedelta(days=CANDLE_DAYS)
    try:
        combined = await provider.candles_for(symbols, interval="1d", from_date=start)
    except SahmApiError:
        raise
    except Exception as exc:
        logger.warning("recommendations candle scan failed: %s", exc)
        raise SahmApiError(
            "تعذر جلب شموع الإغلاق من Sahm API",
            status_code=502,
            error_code="sahm_api_error",
        ) from exc
    if combined is None or combined.empty:
        raise SahmApiError(
            "تعذر جلب بيانات الإغلاق من Sahm API",
            status_code=404,
            error_code="sahm_empty",
        )
    frames = _split_by_symbol(combined)
    quotes = await provider.fetch_quotes_for(list(frames), limit=len(frames))
    engine = MarketRecommendationsEngine(frames, names=names)
    rows = engine.scan_for_opportunities()
    if quotes:
        rows = [_apply_quote(row, quotes.get(str(row["symbol"]))) for row in rows]
    _cache = (now, list(rows))
    return rows


def clear_recommendations_cache() -> None:
    global _cache
    _cache = None


def _prepare_frame(raw: pd.DataFrame, symbol: str) -> pd.DataFrame | None:
    if raw is None or not isinstance(raw, pd.DataFrame) or raw.empty:
        return None
    frame = raw.copy()
    for column in ("open", "high", "low", "close", "volume"):
        if column not in frame.columns:
            if column == "open" and "close" in frame.columns:
                frame["open"] = frame["close"]
            elif column in {"high", "low"} and "close" in frame.columns:
                frame[column] = frame["close"]
            elif column == "volume":
                frame["volume"] = 0.0
            else:
                return None
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["close"]).reset_index(drop=True)
    if "symbol" not in frame.columns:
        frame["symbol"] = symbol
    return frame if len(frame) >= MIN_BARS else None


def _split_by_symbol(combined: pd.DataFrame) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    if "symbol" not in combined.columns:
        return frames
    for symbol, group in combined.groupby(combined["symbol"].astype(str).str.upper(), sort=False):
        ticker = str(symbol).strip().upper()
        if ticker:
            frames[ticker] = group.reset_index(drop=True)
    return frames


def _average_true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(14, min_periods=7).mean()


def _money_flow_index(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    typical = (high + low + close) / 3.0
    raw_flow = typical * volume
    delta = typical.diff()
    positive = raw_flow.where(delta > 0, 0.0)
    negative = raw_flow.where(delta < 0, 0.0)
    pos_sum = positive.rolling(14, min_periods=7).sum()
    neg_sum = negative.rolling(14, min_periods=7).sum().replace(0, np.nan)
    ratio = pos_sum / neg_sum
    return 100.0 - (100.0 / (1.0 + ratio))


def _bounce_score(
    *,
    last_close: float,
    prev_close: float,
    last_open: float,
    last_high: float,
    last_low: float,
    last_sma: float,
    last_mfi: float,
    prior_mfi: float,
    vol_ratio: float,
    recent_low: float,
    close_series: pd.Series,
    sma_series: pd.Series,
) -> int:
    score = 0
    dipped = bool((close_series.tail(6) < sma_series.tail(6) * 0.995).any())
    if dipped:
        score += 22
    if last_close > prev_close:
        score += 16
    candle_range = max(last_high - last_low, 1e-9)
    body = last_close - last_open
    lower_wick = min(last_open, last_close) - last_low
    if body > 0 and body / candle_range >= 0.45:
        score += 14
    if lower_wick / candle_range >= 0.28:
        score += 10
    if last_close >= last_sma * 0.992:
        score += 12
    if last_mfi <= 42 or (prior_mfi <= 35 and last_mfi > prior_mfi):
        score += 14
    if vol_ratio >= 1.4:
        score += 12
    elif vol_ratio >= 1.1:
        score += 7
    if last_low <= recent_low * 1.01:
        score += 6
    return min(score, 99)


def _momentum_score(
    *,
    last_close: float,
    prev_close: float,
    last_sma: float,
    last_mfi: float,
    vol_ratio: float,
    recent_high: float,
    close_series: pd.Series,
) -> int:
    score = 0
    if last_close > last_sma:
        score += 24
    if last_close > prev_close:
        score += 14
    if len(close_series) >= 4 and last_close > float(close_series.iloc[-3]) > float(close_series.iloc[-4]):
        score += 12
    up_days = int((close_series.diff().tail(5) > 0).sum())
    if up_days >= 3:
        score += 10
    if vol_ratio >= 1.8:
        score += 16
    elif vol_ratio >= 1.3:
        score += 10
    if last_mfi >= 55:
        score += 12
    if last_close >= recent_high * 0.997:
        score += 12
    return min(score, 99)


def _bounce_reason(vol_ratio: float, mfi: float, close: float, sma: float) -> str:
    location = "فوق" if close >= sma else "قرب"
    return (
        f"شمعة ارتداد من الدعم مع إغلاق {location} متوسط 20 يوماً، "
        f"وتدفق سيولة (MFI {mfi:.0f}) وحجم يعادل {vol_ratio:.1f}× المتوسط."
    )


def _momentum_reason(vol_ratio: float, mfi: float, close: float, sma: float) -> str:
    return (
        f"إغلاق فوق متوسط 20 يوماً ({sma:.2f}) مع تدفق سيولة إيجابي (MFI {mfi:.0f}) "
        f"وحجم تداول {vol_ratio:.1f}× المتوسط، بما يدعم استمرار الزخم الصاعد."
    )


def _opportunity_row(
    *,
    symbol: str,
    name: str,
    close_price: float,
    signal_type: str,
    signal_kind: str,
    score: int,
    entry: float,
    target: float,
    stop: float,
    reason: str,
    volume_ratio: float,
    mfi: float,
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "name": name,
        "close_price": round(close_price, 2),
        "signal_type": signal_type,
        "signal_kind": signal_kind,
        "confidence": f"{int(score)}%",
        "confidence_score": int(score),
        "entry_price": _fmt(entry),
        "target_price": _fmt(target),
        "stop_loss": _fmt(stop),
        "reason": reason,
        "volume_ratio": round(volume_ratio, 2),
        "mfi": round(mfi, 1),
    }


def _apply_quote(row: dict[str, Any], quote: Mapping[str, Any] | None) -> dict[str, Any]:
    if not quote:
        return row
    nested = quote.get("data") if isinstance(quote.get("data"), dict) else quote
    price = nested.get("price") if isinstance(nested, Mapping) else None
    try:
        live = float(price)
    except (TypeError, ValueError):
        return row
    if live <= 0:
        return row
    delta = live - float(row["close_price"])
    updated = dict(row)
    updated["close_price"] = round(live, 2)
    updated["entry_price"] = _fmt(live)
    updated["target_price"] = _fmt(float(row["target_price"]) + delta)
    updated["stop_loss"] = _fmt(float(row["stop_loss"]) + delta)
    return updated


def _fmt(value: float) -> str:
    return f"{float(value):.2f}"
