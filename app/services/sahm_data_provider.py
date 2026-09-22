from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

import httpx
import pandas as pd

from app.core.config import Settings, get_settings
from app.core.exceptions import InvalidSymbolError, SahmApiError
from app.models.screener import normalize_tasi_symbol
from app.services.liquidity_engine import LiquidityEngine, LiquidityRadarEngine
from app.services.sahm_quota import SahmQuota, get_sahm_quota

logger = logging.getLogger(__name__)

_SAHMK_REST_URL = "https://api.sahmk.sa/api/v1"
_SAHMCAPITAL_REST_URL = "https://api.sahmcapital.com/v1"
_DEFAULT_REST_URL = _SAHMK_REST_URL
_PLACEHOLDER_API_KEYS = frozenset({
    "",
    "your_api_key",
    "your_api_key_here",
    "your_sahm_api_key",
    "changeme",
    "ضع_مفتاح_sahm_api_الخاص_بك_هنا",
})
_INDEX_SYMBOLS = frozenset({"TASI", "NOMU"})
_HISTORICAL_INTERVALS = frozenset({"1d", "1w", "1m"})
_INTRADAY_INTERVALS = frozenset({"30m", "60m"})
_ALL_INTERVALS = _HISTORICAL_INTERVALS | _INTRADAY_INTERVALS
_PAGE_LIMIT = 500
_PAGE_LIMIT_MAX = 2000
_MAX_PAGES = 40
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

try:
    from zoneinfo import ZoneInfo

    _RIYADH = ZoneInfo("Asia/Riyadh")
except Exception:  # pragma: no cover - Windows without tzdata
    _RIYADH = timezone(timedelta(hours=3))

RADAR_COLUMNS: tuple[str, ...] = (
    "timestamp",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "turnover",
    "trades",
    "adjusted_close",
    "interval",
    "is_intraday",
    "is_final",
)

CANDLE_COLUMNS: tuple[str, ...] = ("timestamp", "open", "high", "low", "close", "volume")

RADAR_DTYPES: dict[str, str] = {
    "symbol": "string",
    "open": "float64",
    "high": "float64",
    "low": "float64",
    "close": "float64",
    "volume": "float64",
    "turnover": "float64",
    "trades": "Int64",
    "adjusted_close": "float64",
    "interval": "string",
    "is_intraday": "boolean",
    "is_final": "boolean",
}


def sahm_rest_candidates(configured: str | None, api_key: str = "") -> list[str]:
    """Prefer the SAHMK host for `shmk_` keys, then the configured URL, then capital."""

    ordered: list[str] = []
    key = str(api_key or "").strip().lower()
    configured_url = str(configured or "").strip().rstrip("/")
    if key.startswith("shmk"):
        ordered.append(_SAHMK_REST_URL)
    if configured_url:
        ordered.append(configured_url)
    ordered.extend((_SAHMK_REST_URL, _SAHMCAPITAL_REST_URL))
    unique: list[str] = []
    for url in ordered:
        clean = url.rstrip("/")
        if clean and clean not in unique:
            unique.append(clean)
    return unique or [_DEFAULT_REST_URL]


def prefer_sahm_rest_url(configured: str | None, api_key: str = "") -> str:
    return sahm_rest_candidates(configured, api_key)[0]


class SahmDataProvider:
    """Programmatic bridge to the Sahm / SAHMK market-data API.

    Reads `SAHM_API_KEY` / `SAHMK_API_KEY` and `SAHM_API_BASE_URL` from the
    environment, fetches historical and intraday OHLCV candles, and returns a
    DataFrame that can be passed to `LiquidityRadarEngine.ingest()`.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        api_key: str | None = None,
        rest_url: str | None = None,
        quota: SahmQuota | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self.api_key = resolve_sahm_api_key(self._settings, explicit=api_key)
        configured = (
            rest_url
            or os.getenv("SAHM_API_BASE_URL")
            or self._settings.sahmk_rest_url
            or _DEFAULT_REST_URL
        )
        self._rest_bases = sahm_rest_candidates(configured, self.api_key)
        self.base_url = self._rest_bases[0]
        self.headers = sahm_auth_headers(self.api_key)
        self._api_key = self.api_key
        self._rest_url = self.base_url
        self._data_mode = (self._settings.sahmk_data_mode or "delayed").strip().lower()
        self._request_gap = float(self._settings.sahmk_request_gap_seconds)
        self._max_backoff = float(self._settings.sahmk_max_backoff_seconds)
        self._client = client
        self._owns_client = client is None
        self._quota = quota or get_sahm_quota(daily_limit=int(self._settings.sahmk_daily_limit))
        self._http_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    async def __aenter__(self) -> SahmDataProvider:
        await self._ensure_client()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def start(self) -> None:
        await self._ensure_client()

    def fetch_historical_candles(
        self,
        symbol: str,
        interval: str = "1d",
        limit: int = 100,
    ) -> pd.DataFrame | None:
        """Fetch historical / intraday candles as a DataFrame for LiquidityRadarEngine.

        `interval` accepts `1d`, `1w`, `1h`/`60m`, and `30m`. Minute bars such as
        `1m` or `5m` are not available from SAHMK.
        """

        raw = (interval or "1d").strip().lower()
        if raw in {"1m", "5m", "5min", "3m", "15m"}:
            logger.warning(
                "Sahm interval '%s' is not available on SAHMK; use 1d, 1w, 1h/60m, or 30m",
                interval,
            )
            return None
        mapped = _map_bridge_interval(interval)
        if mapped is None:
            logger.warning("Sahm interval '%s' is not supported", interval)
            return None
        cap = max(1, min(int(limit), _PAGE_LIMIT_MAX))
        try:
            frame = self._run_sync(self.fetch_candles(symbol, interval=mapped))
        except (SahmApiError, InvalidSymbolError) as exc:
            logger.warning("خطأ في جلب بيانات Sahm للسهم %s: %s", symbol, exc.message)
            return None
        except Exception:
            logger.exception("استثناء أثناء الاتصال بـ Sahm API")
            return None
        if frame is None or frame.empty:
            return None
        missing = [column for column in CANDLE_COLUMNS if column not in frame.columns]
        if missing:
            logger.error("العمود الأساسي %s غير موجود في استجابة Sahm API", missing[0])
            return None
        return frame.tail(cap).reset_index(drop=True)

    def _run_sync(self, coroutine: Any) -> pd.DataFrame:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coroutine).result()

    async def historical_candles(
        self,
        symbol: str,
        *,
        from_date: date | datetime | str | None = None,
        to_date: date | datetime | str | None = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """Daily / weekly / monthly OHLCV bars for one TASI (or index) symbol."""

        resolved = _normalize_interval(interval, allowed=_HISTORICAL_INTERVALS, fallback="1d")
        return await self.fetch_candles(
            symbol,
            interval=resolved,
            from_date=from_date,
            to_date=to_date,
        )

    async def intraday_candles(
        self,
        symbol: str,
        *,
        from_date: date | datetime | str | None = None,
        to_date: date | datetime | str | None = None,
        interval: str = "60m",
    ) -> pd.DataFrame:
        """Intraday 30m / 60m candles. Plan-gated by SAHMK (`403 PLAN_LIMIT`)."""

        resolved = _normalize_interval(interval, allowed=_INTRADAY_INTERVALS, fallback="60m")
        start = from_date if from_date is not None else date.today() - timedelta(days=7)
        return await self.fetch_candles(
            symbol,
            interval=resolved,
            from_date=start,
            to_date=to_date,
        )

    async def fetch_candles(
        self,
        symbol: str,
        *,
        interval: str = "1d",
        from_date: date | datetime | str | None = None,
        to_date: date | datetime | str | None = None,
    ) -> pd.DataFrame:
        ticker = normalize_sahm_symbol(symbol)
        resolved = _normalize_interval(interval, allowed=_ALL_INTERVALS, fallback="1d")
        params: dict[str, str | int] = {
            "interval": resolved,
            "limit": _PAGE_LIMIT,
            "offset": 0,
        }
        start = _as_date_param(from_date)
        end = _as_date_param(to_date)
        if start:
            params["from"] = start
        if end:
            params["to"] = end

        rows: list[dict[str, Any]] = []
        metadata: dict[str, Any] = {}
        offset = 0
        for _page in range(_MAX_PAGES):
            params["offset"] = offset
            payload = await self._get(f"/historical/{ticker}/", params)
            metadata = _historical_metadata(payload, resolved)
            page_rows = _extract_candle_rows(payload)
            rows.extend(page_rows)
            if not page_rows:
                break
            limit = min(int(payload.get("limit") or params["limit"]), _PAGE_LIMIT_MAX)
            has_more = payload.get("has_more")
            total = payload.get("total")
            offset += limit
            if has_more is False:
                break
            if has_more is True:
                await asyncio.sleep(self._request_gap)
                continue
            if isinstance(total, int) and offset >= total:
                break
            if len(page_rows) < limit:
                break
            await asyncio.sleep(self._request_gap)

        frame = candles_to_radar_frame(
            rows,
            symbol=ticker,
            interval=str(metadata.get("interval") or resolved),
            is_intraday=bool(metadata.get("is_intraday", resolved in _INTRADAY_INTERVALS)),
        )
        logger.info(
            "sahm candles symbol=%s interval=%s rows=%s from=%s to=%s",
            ticker,
            resolved,
            len(frame),
            start or "-",
            end or "-",
        )
        return frame

    async def candles_for(
        self,
        symbols: Iterable[str],
        *,
        interval: str = "1d",
        from_date: date | datetime | str | None = None,
        to_date: date | datetime | str | None = None,
        intraday: bool | None = None,
    ) -> pd.DataFrame:
        """Fetch candles for many TASI symbols with request pacing."""

        resolved = _normalize_interval(
            interval,
            allowed=_INTRADAY_INTERVALS if intraday else _ALL_INTERVALS,
            fallback="60m" if intraday else "1d",
        )
        frames: list[pd.DataFrame] = []
        for index, raw in enumerate(dict.fromkeys(symbols)):
            if index:
                await asyncio.sleep(self._request_gap)
            try:
                frame = await self.fetch_candles(
                    raw,
                    interval=resolved,
                    from_date=from_date,
                    to_date=to_date,
                )
            except (InvalidSymbolError, SahmApiError) as exc:
                logger.warning("sahm skipped %s: %s", raw, exc.message)
                continue
            if not frame.empty:
                frames.append(frame)
        if not frames:
            return empty_radar_frame()
        return (
            pd.concat(frames, ignore_index=True)
            .sort_values(["symbol", "timestamp"], kind="mergesort")
            .reset_index(drop=True)
        )

    async def list_tasi_symbols(self, *, active_only: bool = True) -> list[str]:
        """Listed TASI tickers from `GET /companies/?market=TASI`."""

        symbols: list[str] = []
        offset = 0
        limit = 500
        for _page in range(_MAX_PAGES):
            payload = await self._get(
                "/companies/",
                {"market": "TASI", "limit": limit, "offset": offset},
            )
            results = payload.get("results") or payload.get("companies") or []
            if not isinstance(results, list):
                break
            for item in results:
                if not isinstance(item, dict):
                    continue
                raw = str(item.get("symbol") or "").strip()
                if active_only:
                    status = str(item.get("status") or "active").strip().lower()
                    if status and status not in {"active", "listed", "trading"}:
                        continue
                try:
                    symbols.append(normalize_tasi_symbol(raw))
                except ValueError:
                    continue
            total = int(payload.get("total") or 0)
            offset += int(payload.get("limit") or limit)
            if not results or (total and offset >= total) or len(results) < limit:
                break
            await asyncio.sleep(self._request_gap)
        return list(dict.fromkeys(symbols))

    async def fetch_quote(self, symbol: str) -> dict[str, Any]:
        """Live delayed/realtime quote for one TASI symbol."""

        ticker = normalize_sahm_symbol(symbol)
        try:
            payload = await self._get(
                f"/quote/{ticker}/",
                {"data_mode": self._data_mode},
            )
        except (SahmApiError, InvalidSymbolError):
            return {}
        return payload if isinstance(payload, dict) else {}

    async def fetch_market_board(self) -> dict[str, Any]:
        """TASI gainers / volume / value / summary from Sahm in one paced pass."""

        params = {"index": "TASI", "limit": 50, "data_mode": self._data_mode}
        board: dict[str, Any] = {"gainers": [], "volume": [], "value": [], "summary": {}}
        endpoints = (
            ("gainers", "/market/gainers/", params, "gainers"),
            ("volume", "/market/volume/", params, "stocks"),
            ("value", "/market/value/", params, "stocks"),
            ("summary", "/market/summary/", {"index": "TASI", "data_mode": self._data_mode}, None),
        )
        for index, (key, path, query, list_key) in enumerate(endpoints):
            if index:
                await asyncio.sleep(self._request_gap)
            try:
                payload = await self._get(path, query)
            except SahmApiError as exc:
                logger.warning("sahm market board skipped %s: %s", key, exc.message)
                continue
            if key == "summary":
                board["summary"] = payload
                continue
            rows = payload.get(list_key) or payload.get("data") or payload.get("results") or []
            board[key] = rows if isinstance(rows, list) else []
        return board

    async def fetch_company_directory(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        """Full TASI company directory from Sahm (`GET /companies/`)."""

        companies: list[dict[str, Any]] = []
        offset = 0
        limit = 500
        for _page in range(_MAX_PAGES):
            payload = await self._get(
                "/companies/",
                {"market": "TASI", "limit": limit, "offset": offset},
            )
            results = payload.get("results") or payload.get("companies") or payload.get("data") or []
            if not isinstance(results, list):
                break
            for item in results:
                if not isinstance(item, dict):
                    continue
                if active_only:
                    status = str(item.get("status") or "active").strip().lower()
                    if status and status not in {"active", "listed", "trading"}:
                        continue
                companies.append(item)
            total = int(payload.get("total") or 0)
            offset += int(payload.get("limit") or limit)
            if not results or (total and offset >= total) or len(results) < limit:
                break
            await asyncio.sleep(self._request_gap)
        return companies

    async def fetch_quotes_for(self, symbols: Iterable[str], *, limit: int = 40) -> dict[str, dict[str, Any]]:
        """Paced live quotes for the requested TASI names."""

        quotes: dict[str, dict[str, Any]] = {}
        seen: set[str] = set()
        for raw in symbols:
            if len(quotes) >= max(1, limit):
                break
            try:
                ticker = normalize_sahm_symbol(str(raw))
            except InvalidSymbolError:
                continue
            if ticker in seen:
                continue
            seen.add(ticker)
            if not self._quota.allow():
                logger.warning("sahm quote fill stopped; remaining=%s", self._quota.remaining())
                break
            if quotes:
                await asyncio.sleep(self._request_gap)
            payload = await self.fetch_quote(ticker)
            if payload:
                quotes[ticker] = payload
        return quotes

    def feed_engine(self, engine: LiquidityEngine, candles: pd.DataFrame) -> list[Any]:
        """Pass a radar DataFrame into LiquidityEngine / LiquidityRadarEngine."""

        ingest = getattr(engine, "ingest", None)
        if callable(ingest):
            return list(ingest(candles))
        return engine.ingest_candles(candles)

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(20.0, connect=10.0),
                headers=sahm_auth_headers(self._api_key),
            )
            self._owns_client = True
        return self._client

    def _ordered_bases(self) -> list[str]:
        bases = [url for url in self._rest_bases if url]
        current = self._rest_url
        if current in bases:
            index = bases.index(current)
            return bases[index:] + bases[:index]
        return bases or [_DEFAULT_REST_URL]

    async def _get(self, path: str, params: Mapping[str, Any]) -> dict[str, Any]:
        if not self._api_key:
            raise SahmApiError(
                "SAHM_API_KEY is missing; cannot fetch live Sahm data",
                status_code=503,
                error_code="sahm_not_configured",
            )
        cached = self._cache_get(path, params, allow_stale=False)
        if cached is not None:
            return cached
        if not self._quota.allow():
            stale = self._cache_get(path, params, allow_stale=True)
            if stale is not None:
                logger.warning("sahm quota exhausted; serving cache path=%s remaining=%s", path, self._quota.remaining())
                return stale
            raise SahmApiError(
                "Sahm daily REST quota exhausted; using TickChart / last-close instead",
                status_code=429,
                error_code="sahm_rate_limit",
                details={"path": path, **self._quota.snapshot()},
            )
        client = await self._ensure_client()
        headers = sahm_auth_headers(self._api_key)
        last_error: Exception | None = None
        for base in self._ordered_bases():
            delay = max(self._request_gap, 0.4)
            try_next_host = False
            for attempt in range(4):
                fresh = self._cache_get(path, params, allow_stale=False)
                if fresh is not None:
                    return fresh
                if not self._quota.allow():
                    stale = self._cache_get(path, params, allow_stale=True)
                    if stale is not None:
                        return stale
                    break
                url = f"{base}{path}"
                try:
                    response = await client.get(url, params=dict(params), headers=headers)
                except httpx.HTTPError as exc:
                    last_error = exc
                    logger.warning("sahm network error %s %s attempt=%s", path, exc.__class__.__name__, attempt + 1)
                    await asyncio.sleep(min(delay, self._max_backoff))
                    delay = min(delay * 2, self._max_backoff)
                    continue

                self._quota.consume(1)
                if response.status_code == 429:
                    self._quota.trip("http_429")
                    logger.warning("sahm rate limited (HTTP 429) path=%s — stopping REST for the Riyadh day", path)
                    stale = self._cache_get(path, params, allow_stale=True)
                    if stale is not None:
                        return stale
                    last_error = SahmApiError(
                        "SAHMK rate limit exceeded",
                        status_code=429,
                        error_code="sahm_rate_limit",
                        details={"path": path, **self._quota.snapshot()},
                    )
                    break
                if response.status_code >= 500:
                    last_error = SahmApiError(
                        f"SAHMK server error (HTTP {response.status_code})",
                        status_code=502,
                        error_code="sahm_server_error",
                        details={"path": path, "status": response.status_code},
                    )
                    if attempt >= 1 or self._quota.remaining() < 8:
                        break
                    await asyncio.sleep(min(delay, self._max_backoff))
                    delay = min(delay * 2, self._max_backoff)
                    continue
                if response.status_code == 404:
                    last_error = _api_error(response, path)
                    try_next_host = True
                    break
                if response.status_code >= 400:
                    error = _api_error(response, path)
                    if error.error_code in {"sahm_plan_limit", "sahm_rate_limit"}:
                        self._quota.trip(error.error_code)
                    raise error
                payload = _response_json(response)
                if payload is None:
                    raise SahmApiError(
                        "SAHMK returned a non-JSON payload",
                        status_code=502,
                        error_code="sahm_invalid_payload",
                        details={"path": path},
                    )
                nested = payload.get("error")
                if nested:
                    error = _payload_error(nested, response.status_code, path)
                    if error.status_code == 404 or error.error_code == "sahm_symbol_not_found":
                        last_error = error
                        try_next_host = True
                        break
                    if error.error_code in {"sahm_plan_limit", "sahm_rate_limit"}:
                        self._quota.trip(error.error_code)
                    raise error
                if base != self._rest_url:
                    logger.info("sahm host failover succeeded base=%s path=%s", base, path)
                self._rest_url = base
                self.base_url = base
                self._cache_put(path, params, payload)
                return payload
            if try_next_host:
                logger.warning("sahm host 404, trying next base=%s path=%s", base, path)
                continue
            if isinstance(last_error, SahmApiError) and last_error.error_code == "sahm_rate_limit":
                break

        stale = self._cache_get(path, params, allow_stale=True)
        if stale is not None:
            return stale
        if isinstance(last_error, SahmApiError):
            raise last_error
        raise SahmApiError(
            "SAHMK request failed after retries",
            status_code=502,
            error_code="sahm_unreachable",
            details={"path": path, "reason": str(last_error) if last_error else None},
        ) from last_error

    def _cache_key(self, path: str, params: Mapping[str, Any]) -> str:
        items = "&".join(f"{key}={params[key]}" for key in sorted(params))
        return f"{path}?{items}"

    def _ttl_for(self, path: str) -> float:
        if path.startswith("/market/") or path.startswith("/companies/"):
            return float(getattr(self._settings, "sahmk_board_cache_ttl_seconds", 900) or 900)
        if path.startswith("/historical/"):
            return 12 * 3600
        return float(self._settings.sahmk_cache_ttl_seconds)

    def _cache_get(self, path: str, params: Mapping[str, Any], *, allow_stale: bool) -> dict[str, Any] | None:
        item = self._http_cache.get(self._cache_key(path, params))
        if item is None:
            return None
        stored_at, payload = item
        age = time.monotonic() - stored_at
        if not allow_stale and age > self._ttl_for(path):
            return None
        return dict(payload)

    def _cache_put(self, path: str, params: Mapping[str, Any], payload: dict[str, Any]) -> None:
        self._http_cache[self._cache_key(path, params)] = (time.monotonic(), dict(payload))


def candles_to_radar_frame(
    rows: Iterable[Mapping[str, Any]],
    *,
    symbol: str,
    interval: str,
    is_intraday: bool,
) -> pd.DataFrame:
    """Normalize SAHMK candle rows into a LiquidityRadarEngine-ready DataFrame."""

    records: list[dict[str, Any]] = []
    for row in rows:
        parsed = _parse_candle(row, symbol=symbol, interval=interval, is_intraday=is_intraday)
        if parsed is not None:
            records.append(parsed)
    if not records:
        return empty_radar_frame()
    frame = pd.DataFrame.from_records(records, columns=list(RADAR_COLUMNS))
    frame = _apply_radar_dtypes(frame)
    frame = (
        frame.drop_duplicates(subset=["symbol", "timestamp"], keep="last")
        .sort_values(["symbol", "timestamp"], kind="mergesort")
        .reset_index(drop=True)
    )
    return frame


def _clean_api_key(raw: object) -> str:
    key = str(raw or "").strip().strip("\"'").strip()
    if not key or key.lower() in _PLACEHOLDER_API_KEYS:
        return ""
    return key


def resolve_sahm_api_key(
    settings: Settings | None = None,
    *,
    explicit: str | None = None,
) -> str:
    """Read SAHM_API_KEY / SAHMK_API_KEY, ignoring empty placeholder values."""

    if explicit is not None:
        return _clean_api_key(explicit)
    candidates = (
        settings.sahmk_api_key if settings is not None else None,
        os.getenv("SAHM_API_KEY"),
        os.getenv("SAHMK_API_KEY"),
    )
    for raw in candidates:
        key = _clean_api_key(raw)
        if key:
            return key
    return ""


def sahm_auth_headers(api_key: str) -> dict[str, str]:
    """Headers required on every Sahm/SAHMK REST call."""

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    key = _clean_api_key(api_key)
    if key:
        headers["Authorization"] = f"Bearer {key}"
        headers["X-API-Key"] = key
    return headers


def empty_radar_frame() -> pd.DataFrame:
    frame = pd.DataFrame({column: [] for column in RADAR_COLUMNS})
    return _apply_radar_dtypes(frame)


def normalize_sahm_symbol(value: str) -> str:
    raw = value.strip().translate(_ARABIC_DIGITS).upper()
    if raw.endswith(".SR") or raw.endswith(".SA"):
        raw = raw[:-3]
    if raw in _INDEX_SYMBOLS:
        return raw
    try:
        return normalize_tasi_symbol(raw)
    except ValueError as exc:
        raise InvalidSymbolError(value) from exc


def _apply_radar_dtypes(frame: pd.DataFrame) -> pd.DataFrame:
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    for column, dtype in RADAR_DTYPES.items():
        frame[column] = frame[column].astype(dtype)
    return frame.dropna(subset=["timestamp", "symbol", "close"])


def _parse_candle(
    row: Mapping[str, Any],
    *,
    symbol: str,
    interval: str,
    is_intraday: bool,
) -> dict[str, Any] | None:
    stamp = _parse_timestamp(
        row.get("timestamp") or row.get("date") or row.get("time") or row.get("datetime"),
        is_intraday=is_intraday,
    )
    close = _as_float(row.get("close") or row.get("c") or row.get("price"))
    if stamp is None or close is None or close <= 0:
        return None
    volume = (
        _as_float(
            row.get("volume")
            or row.get("vol")
            or row.get("quantity")
            or row.get("qty")
            or row.get("traded_volume")
        )
        or 0.0
    )
    if volume < 0:
        return None
    ticker = str(row.get("symbol") or symbol).strip().upper() or symbol
    open_px = _as_float(row.get("open") or row.get("o"))
    high_px = _as_float(row.get("high") or row.get("h"))
    low_px = _as_float(row.get("low") or row.get("l"))
    adjusted = _as_float(row.get("adjusted_close") or row.get("adj_close"))
    final_flag = row.get("is_final")
    if final_flag is None:
        final_flag = not bool(row.get("partial"))
    return {
        "timestamp": stamp,
        "symbol": ticker,
        "open": open_px if open_px is not None else close,
        "high": high_px if high_px is not None else close,
        "low": low_px if low_px is not None else close,
        "close": close,
        "volume": volume,
        "turnover": _as_float(
            row.get("turnover")
            or row.get("value")
            or row.get("value_traded")
            or row.get("traded_value")
        )
        or 0.0,
        "trades": _as_int(row.get("number_of_trades") or row.get("trades") or row.get("trade_count")),
        "adjusted_close": adjusted if adjusted is not None else close,
        "interval": str(row.get("interval") or interval),
        "is_intraday": bool(row.get("is_intraday", is_intraday)),
        "is_final": bool(final_flag),
    }


def _extract_candle_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    raw_rows: list[Any] = []
    if isinstance(data, list):
        raw_rows = data
    elif isinstance(data, dict):
        for key in ("candles", "bars", "rows", "items"):
            rows = data.get(key)
            if isinstance(rows, list):
                raw_rows = rows
                break
    if not raw_rows:
        for key in ("candles", "bars", "results"):
            rows = payload.get(key)
            if isinstance(rows, list):
                raw_rows = rows
                break
    parsed: list[dict[str, Any]] = []
    for row in raw_rows:
        coerced = _coerce_candle_row(row)
        if coerced is not None:
            parsed.append(coerced)
    return parsed


def _coerce_candle_row(row: Any) -> dict[str, Any] | None:
    if isinstance(row, dict):
        return row
    if isinstance(row, (list, tuple)) and len(row) >= 6:
        return {
            "timestamp": row[0],
            "open": row[1],
            "high": row[2],
            "low": row[3],
            "close": row[4],
            "volume": row[5],
        }
    return None


def _historical_metadata(payload: Mapping[str, Any], interval: str) -> dict[str, Any]:
    nested = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    merged = {**nested, **{key: payload[key] for key in payload if key != "data"}}
    resolved = str(merged.get("interval") or interval)
    is_intraday = merged.get("is_intraday")
    if is_intraday is None:
        is_intraday = resolved in _INTRADAY_INTERVALS
    merged["interval"] = resolved
    merged["is_intraday"] = bool(is_intraday)
    return merged


def _parse_timestamp(value: Any, *, is_intraday: bool) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        stamp = value if value.tzinfo else value.replace(tzinfo=_RIYADH)
        return stamp.astimezone(timezone.utc)
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime(value.year, value.month, value.day, tzinfo=_RIYADH).astimezone(timezone.utc)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        unix = float(value)
        if unix > 1e12:
            unix /= 1000.0
        return datetime.fromtimestamp(unix, tz=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d{10,13}", text):
        return _parse_timestamp(int(text), is_intraday=is_intraday)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        parsed_date = date.fromisoformat(text)
        return datetime(parsed_date.year, parsed_date.month, parsed_date.day, tzinfo=_RIYADH).astimezone(
            timezone.utc
        )
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_RIYADH)
    return parsed.astimezone(timezone.utc)


def _normalize_interval(value: str, *, allowed: frozenset[str], fallback: str) -> str:
    mapped = _map_bridge_interval(value) or (value or fallback).strip().lower()
    interval = mapped or fallback
    if interval not in allowed:
        raise SahmApiError(
            f"Unsupported SAHMK interval '{value}'. Use one of: {', '.join(sorted(allowed))}",
            status_code=422,
            error_code="sahm_invalid_interval",
            details={"interval": value, "allowed": sorted(allowed)},
        )
    return interval


def _map_bridge_interval(value: str) -> str | None:
    interval = (value or "").strip().lower()
    aliases = {
        "d": "1d",
        "day": "1d",
        "daily": "1d",
        "1d": "1d",
        "w": "1w",
        "week": "1w",
        "weekly": "1w",
        "1w": "1w",
        "mo": "1m",
        "month": "1m",
        "monthly": "1m",
        "1mo": "1m",
        "1month": "1m",
        "1h": "60m",
        "1hr": "60m",
        "1hour": "60m",
        "60m": "60m",
        "60min": "60m",
        "30m": "30m",
        "30min": "30m",
    }
    if interval in aliases:
        return aliases[interval]
    if interval == "1m":
        return "1m"
    return None


def _as_date_param(value: date | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text[:10] if text else None


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _as_int(value: Any) -> int | None:
    number = _as_float(value)
    if number is None:
        return None
    return int(number)


def _response_json(response: httpx.Response) -> dict[str, Any] | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def _retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _api_error(response: httpx.Response, path: str) -> SahmApiError:
    payload = _response_json(response)
    nested = payload.get("error") if payload else None
    if nested:
        return _payload_error(nested, response.status_code, path)
    code = {
        401: "sahm_unauthorized",
        403: "sahm_plan_limit",
        404: "sahm_symbol_not_found",
    }.get(response.status_code, "sahm_api_error")
    return SahmApiError(
        f"SAHMK HTTP {response.status_code} for {path}",
        status_code=min(response.status_code, 502) if response.status_code >= 500 else response.status_code,
        error_code=code,
        details={"path": path, "status": response.status_code},
    )


def _payload_error(nested: Any, status_code: int, path: str) -> SahmApiError:
    if isinstance(nested, dict):
        code = str(nested.get("code") or "sahm_api_error")
        message = str(nested.get("message") or f"SAHMK error {code}")
    else:
        code = "sahm_api_error"
        message = str(nested)
    mapped = {
        "PLAN_LIMIT": "sahm_plan_limit",
        "INVALID_API_KEY": "sahm_unauthorized",
        "INVALID_SYMBOL": "sahm_symbol_not_found",
        "RATE_LIMIT": "sahm_rate_limit",
        "TEMP_SECURITY_LIMIT": "sahm_rate_limit",
    }.get(code, "sahm_api_error")
    http_status = 403 if code == "PLAN_LIMIT" else status_code
    return SahmApiError(
        message,
        status_code=http_status,
        error_code=mapped,
        details={"path": path, "sahm_code": code},
    )


__all__ = [
    "CANDLE_COLUMNS",
    "RADAR_COLUMNS",
    "SahmDataProvider",
    "candles_to_radar_frame",
    "empty_radar_frame",
    "normalize_sahm_symbol",
    "prefer_sahm_rest_url",
    "resolve_sahm_api_key",
    "sahm_auth_headers",
    "sahm_rest_candidates",
    "LiquidityRadarEngine",
]
