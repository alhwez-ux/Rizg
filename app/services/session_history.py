"""Import prior TASI main-market daily closes for end-of-day scans."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import httpx

from app.models.screener import is_tasi_main_symbol
from app.services.tasi_clock import TASI_TZ, now_riyadh

logger = logging.getLogger(__name__)

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.SR"
_RIYADH = TASI_TZ
_RANGE = "3mo"
_CHART_WORKERS = 8
_VOLUME_FLOOR = 10_000.0
_OFFICIAL_SESSION = Path(__file__).resolve().parents[1] / "data" / "official_session.json"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
_FETCH_BUDGET_SECONDS = 10.0
_LISTINGS_PATH = Path(__file__).resolve().parents[1] / "data" / "tasi_main_symbols.json"


def listed_main_market_symbols() -> list[str]:
    try:
        raw = json.loads(_LISTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return []
    if not isinstance(raw, list):
        return []
    return main_market_symbols(str(item) for item in raw)


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


def parse_spark_market(
    payload: dict[str, Any],
    *,
    today: date | None = None,
    sessions: int = 10,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Prior closes before today plus the latest last-price quote (today if present)."""

    cutoff = today or now_riyadh().date()
    want = max(1, min(int(sessions), 40))
    bars: list[dict[str, Any]] = []
    quotes: list[dict[str, Any]] = []
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
        meta = chart.get("meta") if isinstance(chart.get("meta"), dict) else {}
        market_price = _positive(meta.get("regularMarketPrice"))
        last_index = len(stamps) - 1
        series: list[dict[str, Any]] = []
        for index, stamp in enumerate(stamps):
            day = _riyadh_day(stamp)
            close = _positive(closes[index] if index < len(closes) else None)
            if close is None and index == last_index and market_price is not None:
                close = market_price
            if day is None or close is None:
                continue
            volume = _number(volumes[index] if isinstance(volumes, list) and index < len(volumes) else 0) or 0.0
            series.append({"symbol": ticker, "date": day.isoformat(), "close": close, "volume": volume})
        series.sort(key=lambda row: str(row.get("date") or ""))
        if not series:
            continue
        prior = [row for row in series if str(row["date"]) < cutoff.isoformat()][-want:]
        bars.extend(prior)
        last = series[-1]
        earlier = [row for row in series if str(row["date"]) < str(last["date"])]
        prev = earlier[-1]["close"] if earlier else None
        change = None
        if prev and prev > 0:
            change = round(((last["close"] - prev) / prev) * 100, 4)
        quotes.append(
            {
                "symbol": ticker,
                "last_price": last["close"],
                "volume": last.get("volume") or 0.0,
                "prev_close": prev,
                "change_percent": change,
                "session_date": date.fromisoformat(last["date"]),
            }
        )
    return bars, quotes


def load_official_session(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Last measured daily close and session volume, keyed by symbol."""

    tape_path = path or _OFFICIAL_SESSION
    try:
        payload = json.loads(tape_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    quotes = payload.get("quotes") if isinstance(payload, dict) else None
    if not isinstance(quotes, dict):
        return {}
    book: dict[str, dict[str, Any]] = {}
    for raw_symbol, item in quotes.items():
        ticker = str(raw_symbol or "").strip().upper()
        if not is_tasi_main_symbol(ticker) or not isinstance(item, dict):
            continue
        price = _positive(item.get("last_price"))
        if price is None:
            continue
        book[ticker] = {
            "last_price": price,
            "volume": _positive(item.get("volume")),
            "session_date": str(item.get("session_date") or "")[:10],
        }
    return book


def save_official_session(quotes: list[dict[str, Any]], path: Path | None = None) -> int:
    """Persist measured daily closes. A missing volume is left out rather than stored as a print size."""

    book: dict[str, dict[str, Any]] = {}
    as_of = ""
    for item in quotes:
        ticker = str(item.get("symbol") or "").strip().upper()
        price = _positive(item.get("last_price"))
        if not is_tasi_main_symbol(ticker) or price is None:
            continue
        volume = _positive(item.get("volume"))
        day = str(item.get("session_date") or "")[:10]
        book[ticker] = {
            "last_price": round(price, 2),
            "volume": None if volume is None else float(int(volume)),
            "session_date": day,
        }
        if day > as_of:
            as_of = day
    if not book:
        return 0
    tape_path = path or _OFFICIAL_SESSION
    tape_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"as_of": as_of, "source": "daily-close", "quotes": book}
    tape_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return len(book)


def overlay_session_closes(
    rows: list[dict[str, Any]],
    *,
    phase: str,
    official: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Replace a print-sized volume with the measured session close. Never invent a price."""

    book = official if official is not None else load_official_session()
    closed = phase not in {"preopen", "open", "auction"}
    for row in rows:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("symbol") or "").strip().upper()
        known = book.get(ticker)
        volume = _number(row.get("volume"))
        implausible = volume is None or volume < _VOLUME_FLOOR
        if closed and known is not None:
            row["last_price"] = known["last_price"]
            if known.get("volume"):
                row["volume"] = known["volume"]
            elif implausible:
                row["volume"] = None
            continue
        if known is not None and implausible and known.get("volume"):
            row["volume"] = known["volume"]
        elif implausible:
            row["volume"] = None
    return rows


def _download_chart(symbol: str, timeout: float) -> dict[str, Any] | None:
    try:
        with httpx.Client(
            timeout=httpx.Timeout(timeout, connect=min(3.0, timeout)),
            headers={"User-Agent": _UA, "Accept": "application/json"},
        ) as http:
            return _chart_with_client(http, symbol)
    except httpx.HTTPError as exc:
        logger.warning("daily close fetch failed for %s: %s", symbol, exc)
        return None


def _chart_with_client(http: httpx.Client, symbol: str) -> dict[str, Any] | None:
    try:
        response = http.get(YAHOO_CHART.format(symbol=symbol), params={"range": _RANGE, "interval": "1d"})
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("daily close fetch failed for %s: %s", symbol, exc)
        return None
    chart = body.get("chart") if isinstance(body, dict) else None
    result = chart.get("result") if isinstance(chart, dict) else None
    if not isinstance(result, list) or not result or not isinstance(result[0], dict):
        return None
    item = dict(result[0])
    meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
    item["symbol"] = str(meta.get("symbol") or f"{symbol}.SR")
    return item


def fetch_main_market_closes(
    symbols: Iterable[str] | None = None,
    *,
    sessions: int = 10,
    today: date | None = None,
    client: httpx.Client | None = None,
    budget_seconds: float = _FETCH_BUDGET_SECONDS,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Download prior sessions and the latest close, stopping within the time budget."""

    tickers = main_market_symbols(symbols or listed_main_market_symbols())
    if not tickers:
        return [], []
    cutoff = today or now_riyadh().date()
    budget = max(0.2, float(budget_seconds))
    per_call = min(8.0, max(2.0, budget))
    bars: list[dict[str, Any]] = []
    quotes: list[dict[str, Any]] = []

    def take(item: dict[str, Any] | None) -> None:
        if item is None:
            return
        chunk_bars, chunk_quotes = parse_spark_market(
            {"spark": {"result": [item]}},
            today=cutoff,
            sessions=sessions,
        )
        bars.extend(chunk_bars)
        quotes.extend(chunk_quotes)

    if client is not None:
        for symbol in tickers:
            take(_chart_with_client(client, symbol))
        return bars, quotes

    workers = min(_CHART_WORKERS, len(tickers))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_download_chart, symbol, per_call) for symbol in tickers]
        for future in as_completed(futures):
            take(future.result())
    if len(quotes) < len(tickers):
        logger.warning(
            "daily close fetch returned %s/%s symbols within the worker pool",
            len(quotes),
            len(tickers),
        )
    return bars, quotes


def fetch_prior_session_bars(
    symbols: Iterable[str],
    *,
    sessions: int = 10,
    today: date | None = None,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Download the last `sessions` main-market daily closes before today."""

    bars, _quotes = fetch_main_market_closes(symbols, sessions=sessions, today=today, client=client)
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

