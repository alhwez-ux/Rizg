"""Import prior TASI main-market daily closes for end-of-day scans."""

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import Any, Iterable

import httpx

from app.models.screener import is_tasi_main_symbol
from app.services.tasi_clock import TASI_TZ, now_riyadh

logger = logging.getLogger(__name__)

YAHOO_SPARK = "https://query1.finance.yahoo.com/v7/finance/spark"
_RIYADH = TASI_TZ
_BATCH = 10
_RANGE = "1mo"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
_RETRIES = 3


def main_market_symbols(symbols: Iterable[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in symbols:
        ticker = str(raw or "").strip().upper().split(".", 1)[0]
        if not is_tasi_main_symbol(ticker) or ticker in seen:
            continue
        seen.add(ticker)
        ordered.append(ticker)
    return ordered


def parse_spark_bars(
    payload: dict[str, Any],
    *,
    today: date | None = None,
    sessions: int = 10,
) -> list[dict[str, Any]]:
    """Turn a Yahoo spark payload into dated close/volume bars before today."""

    cutoff = today or now_riyadh().date()
    want = max(1, min(int(sessions), 40))
    rows: list[dict[str, Any]] = []
    for item in _spark_results(payload):
        ticker = str(item.get("symbol") or "").strip().upper().replace(".SR", "")
        if not is_tasi_main_symbol(ticker):
            continue
        chart = _first_response(item)
        stamps = chart.get("timestamp") if isinstance(chart, dict) else None
        quote = _quote_block(chart)
        closes = quote.get("close") if isinstance(quote, dict) else None
        volumes = quote.get("volume") if isinstance(quote, dict) else None
        if not isinstance(stamps, list) or not isinstance(closes, list):
            continue
        series: list[dict[str, Any]] = []
        for index, stamp in enumerate(stamps):
            day = _riyadh_day(stamp)
            if day is None or day >= cutoff:
                continue
            close = _positive(closes[index] if index < len(closes) else None)
            if close is None:
                continue
            volume = _number(volumes[index] if isinstance(volumes, list) and index < len(volumes) else 0) or 0.0
            series.append({"symbol": ticker, "date": day.isoformat(), "close": close, "volume": volume})
        series.sort(key=lambda row: str(row.get("date") or ""))
        rows.extend(series[-want:])
    return rows


def fetch_prior_session_bars(
    symbols: Iterable[str],
    *,
    sessions: int = 10,
    today: date | None = None,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Download the last `sessions` main-market daily closes before today."""

    tickers = main_market_symbols(symbols)
    if not tickers:
        return []
    cutoff = today or now_riyadh().date()
    own_client = client is None
    http = client or httpx.Client(timeout=30.0, headers={"User-Agent": _UA, "Accept": "application/json"})
    bars: list[dict[str, Any]] = []
    try:
        for start in range(0, len(tickers), _BATCH):
            chunk = tickers[start : start + _BATCH]
            joined = ",".join(f"{symbol}.SR" for symbol in chunk)
            payload = None
            for attempt in range(_RETRIES):
                try:
                    response = http.get(YAHOO_SPARK, params={"symbols": joined, "range": _RANGE, "interval": "1d"})
                    response.raise_for_status()
                    payload = response.json()
                    break
                except (httpx.HTTPError, ValueError) as exc:
                    logger.warning("Yahoo spark attempt %s failed for %s: %s", attempt + 1, chunk[:3], exc)
                    time.sleep(0.4 * (attempt + 1))
            if payload is None:
                continue
            bars.extend(parse_spark_bars(payload, today=cutoff, sessions=sessions))
            if start + _BATCH < len(tickers):
                time.sleep(0.15)
    finally:
        if own_client:
            http.close()
    return bars


def _spark_results(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    spark = payload.get("spark") if isinstance(payload.get("spark"), dict) else payload
    rows = spark.get("result") if isinstance(spark, dict) else None
    if not isinstance(rows, list):
        return []
    return [item for item in rows if isinstance(item, dict)]


def _first_response(item: dict[str, Any]) -> dict[str, Any]:
    responses = item.get("response")
    if isinstance(responses, list) and responses and isinstance(responses[0], dict):
        return responses[0]
    return item if "timestamp" in item else {}


def _quote_block(chart: dict[str, Any]) -> dict[str, Any]:
    indicators = chart.get("indicators") if isinstance(chart.get("indicators"), dict) else {}
    quotes = indicators.get("quote") if isinstance(indicators, dict) else None
    if isinstance(quotes, list) and quotes and isinstance(quotes[0], dict):
        return quotes[0]
    return {}


def _riyadh_day(stamp: Any) -> date | None:
    try:
        value = int(stamp)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return datetime.fromtimestamp(value, tz=_RIYADH).date()


def _positive(value: Any) -> float | None:
    number = _number(value)
    return number if number is not None and number > 0 else None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or abs(number) == float("inf"):
        return None
    return number

