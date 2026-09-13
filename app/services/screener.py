from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.core.config import Settings
from app.models.screener import MarketPulse, ScreenerRow, ScreenerSnapshot
from app.models.trade import SessionFlow
from app.services.liquidity_engine import LiquidityEngine
from app.services.market_cache import MarketCache
from app.services.shariah import is_prohibited
from app.services.signals import SignalEngine, SignalInputs, apply_levels
from app.services.watchlist import WatchlistService

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")


class ScreenerService:
    """Broad delayed-tape scanner. Badges come only from SignalEngine money-flow rules."""

    def __init__(
        self,
        settings: Settings,
        watchlist: WatchlistService,
        *,
        engine: SignalEngine | None = None,
        liquidity_engine: LiquidityEngine | None = None,
    ) -> None:
        self._settings = settings
        self._watchlist = watchlist
        self._engine = engine or SignalEngine(
            net_flow_threshold=settings.signal_net_flow_threshold,
            aggressive_ratio=settings.signal_aggressive_ratio,
            atr_target_mult=settings.signal_atr_target_mult,
            atr_stop_mult=settings.signal_atr_stop_mult,
        )
        self._liquidity_engine = liquidity_engine
        self._rest = (settings.sahmk_rest_url or "https://api.sahmk.sa/api/v1").rstrip("/")
        self._mode = (settings.sahmk_data_mode or "delayed").strip().lower()
        self._limit = settings.screener_leader_limit
        self.cache = MarketCache(ttl_seconds=settings.sahmk_cache_ttl_seconds)
        self._guard = threading.RLock()
        self._rows: dict[str, ScreenerRow] = {}
        self._prev_volume: dict[str, Decimal] = {}
        self._pulse = MarketPulse(delayed=self._mode != "realtime")
        self._updated_at: datetime | None = None
        self._priority: list[str] = []

    def all_rows(self) -> list[ScreenerRow]:
        with self._guard:
            return list(self._rows.values())

    def snapshot(self) -> ScreenerSnapshot:
        tracked = [symbol for symbol in self._watchlist.symbols() if not is_prohibited(symbol)]
        tracked_set = set(tracked)
        with self._guard:
            rows_by_symbol = dict(self._rows)
            pulse = self._pulse
            updated = self._updated_at

        watchlist: list[ScreenerRow] = []
        for symbol in tracked:
            row = rows_by_symbol.get(symbol)
            if row is None:
                watchlist.append(ScreenerRow(symbol=symbol, tracked=True))
            else:
                watchlist.append(row.model_copy(update={"tracked": True}))

        radar = [
            row.model_copy(update={"tracked": False})
            for row in rows_by_symbol.values()
            if row.symbol not in tracked_set
            and not is_prohibited(row.symbol)
            and (row.entry_signal or row.exit_signal or row.unexpected)
        ]
        radar.sort(key=lambda row: (row.score, abs(row.net_flow)), reverse=True)
        return ScreenerSnapshot(
            watchlist=watchlist,
            radar=radar[:12],
            pulse=pulse,
            scanned=len(rows_by_symbol),
            delayed=self._mode != "realtime",
            updated_at=updated,
        )

    def priority_symbols(self, limit: int = 8) -> list[str]:
        tracked = {symbol for symbol in self._watchlist.symbols() if not is_prohibited(symbol)}
        with self._guard:
            explicit = [symbol for symbol in self._priority if not is_prohibited(symbol)]
            rows = list(self._rows.values())
        extras = [
            row.symbol
            for row in rows
            if row.symbol not in tracked
            and not is_prohibited(row.symbol)
            and (
                row.entry_signal
                or row.exit_signal
                or "volume" in row.sources
                or "value" in row.sources
            )
        ]
        return list(dict.fromkeys([*explicit, *extras]))[:limit]

    def radar_universe(self, limit: int = 40) -> list[str]:
        """Untracked TASI names to rotate through in quote batches."""

        return self.priority_symbols(limit)

    async def refresh_leaders(self, client: httpx.AsyncClient, api_key: str) -> bool:
        headers = {"X-API-Key": api_key, "Accept": "application/json"}
        params = {"index": "TASI", "limit": self._limit, "data_mode": self._mode}
        gainers, gainers_ok = await self._fetch_market(
            client, "gainers", f"{self._rest}/market/gainers/", headers, params
        )
        await self._pace()
        volume, volume_ok = await self._fetch_market(
            client, "volume", f"{self._rest}/market/volume/", headers, params
        )
        await self._pace()
        value, value_ok = await self._fetch_market(
            client, "value", f"{self._rest}/market/value/", headers, params
        )
        await self._pace()
        summary, summary_ok = await self._fetch_market(
            client,
            "summary",
            f"{self._rest}/market/summary/",
            headers,
            {"index": "TASI", "data_mode": self._mode},
        )
        live_hits = sum(1 for ok in (gainers_ok, volume_ok, value_ok, summary_ok) if ok)
        if live_hits == 0:
            logger.warning("market scan using cached TASI leaders after fetch failure")
            if not any((gainers, volume, value)):
                return False

        movers: dict[str, dict[str, Any]] = {}
        _merge_movers(movers, _list_from(gainers, "gainers"), "gainers")
        _merge_movers(movers, _list_from(volume, "stocks"), "volume")
        _merge_movers(movers, _list_from(value, "stocks"), "value")

        tracked = set(self._watchlist.symbols())
        now = datetime.now(timezone.utc)

        with self._guard:
            previous_volumes = dict(self._prev_volume)
            existing_rows = dict(self._rows)

        rows: dict[str, ScreenerRow] = {}
        priority: list[str] = []

        for symbol, raw in movers.items():
            if is_prohibited(symbol):
                continue
            volume_now = _decimal(raw.get("volume"))
            prev = previous_volumes.get(symbol)
            existing = existing_rows.get(symbol)
            inflow, outflow, net, buy_volume, sell_volume = _flow_from_raw(raw, existing)
            session = self._session_for(symbol)
            inflow, outflow, net, buy_volume, sell_volume = _prefer_session(
                inflow, outflow, net, buy_volume, sell_volume, session
            )
            levels = None
            if self._liquidity_engine is not None:
                levels = self._liquidity_engine.observe_market(symbol, raw)
            decision = self._engine.evaluate(
                apply_levels(
                    SignalInputs(
                        change_percent=_decimal(raw.get("change_percent")),
                        volume=volume_now,
                        prev_volume=prev,
                        inflow=inflow,
                        outflow=outflow,
                        net_flow=net,
                        buy_volume=buy_volume,
                        sell_volume=sell_volume,
                        price=_optional_decimal(raw.get("price")),
                        bid=_optional_decimal(raw.get("bid")),
                        ask=_optional_decimal(raw.get("ask")),
                        bid_size=_optional_decimal(raw.get("bid_size")),
                        ask_size=_optional_decimal(raw.get("ask_size")),
                        in_gainers="gainers" in raw.get("sources", ()),
                        in_volume_leaders="volume" in raw.get("sources", ()),
                        in_value_leaders="value" in raw.get("sources", ()),
                        tracked=symbol in tracked,
                    ),
                    levels,
                )
            )
            row = _build_row(
                symbol=symbol,
                name=str(raw.get("name") or raw.get("name_en") or (existing.name if existing else "")),
                price=_decimal(raw.get("price")),
                change_percent=_decimal(raw.get("change_percent")),
                volume=volume_now,
                value=_decimal(raw.get("value") or raw.get("traded_value")),
                inflow=inflow,
                outflow=outflow,
                net=net,
                buy_volume=buy_volume,
                sell_volume=sell_volume,
                decision=decision,
                tracked=symbol in tracked,
                sources=sorted(raw.get("sources", [])),
                updated_at=_parse_time(raw.get("updated_at")) or now,
            )
            rows[symbol] = row
            if decision.unexpected or decision.entry or decision.exit:
                priority.append(symbol)
            elif symbol not in tracked and ("volume" in row.sources or "value" in row.sources):
                priority.append(symbol)

        pulse = MarketPulse(
            index=str((summary or {}).get("index") or "TASI"),
            index_value=_optional_decimal((summary or {}).get("index_value")),
            index_change_percent=_optional_decimal((summary or {}).get("index_change_percent")),
            advancing=_int((summary or {}).get("advancing")),
            declining=_int((summary or {}).get("declining")),
            delayed=bool((summary or {}).get("is_delayed", self._mode != "realtime")),
        )

        with self._guard:
            kept = {
                symbol: row.model_copy(update={"tracked": symbol in tracked})
                for symbol, row in existing_rows.items()
                if symbol not in rows and (symbol in tracked or row.entry_signal or row.exit_signal)
            }
            self._rows = {**kept, **rows}
            for symbol, raw in movers.items():
                vol = _decimal(raw.get("volume"))
                if vol > 0:
                    self._prev_volume[symbol] = vol
            self._pulse = pulse
            self._updated_at = now
            self._priority = list(dict.fromkeys(priority))
        return True

    def observe_quote(
        self,
        payload: dict[str, Any],
        *,
        tracked: bool,
        session: SessionFlow | None = None,
    ) -> ScreenerRow | None:
        merged, liquidity = _flatten_quote(payload)
        symbol = str(merged.get("symbol") or "").strip().upper()
        if not symbol:
            return None
        if is_prohibited(symbol) and not tracked:
            return None
        volume_now = _decimal(merged.get("volume"))
        with self._guard:
            prev = self._prev_volume.get(symbol)
            existing = self._rows.get(symbol)
        sources = list(existing.sources) if existing else ["watchlist" if tracked else "quote"]
        inflow = _optional_decimal(liquidity.get("inflow_value") or liquidity.get("inflow"))
        outflow = _optional_decimal(liquidity.get("outflow_value") or liquidity.get("outflow"))
        net = _optional_decimal(liquidity.get("net_value") or liquidity.get("net_flow"))
        buy_volume = _optional_decimal(
            liquidity.get("inflow_volume") or liquidity.get("buy_volume")
        )
        sell_volume = _optional_decimal(
            liquidity.get("outflow_volume") or liquidity.get("sell_volume")
        )
        if inflow is None and existing and existing.flow_verified:
            inflow, outflow, net = existing.inflow, existing.outflow, existing.net_flow
            buy_volume = buy_volume if buy_volume is not None else existing.buy_volume
            sell_volume = sell_volume if sell_volume is not None else existing.sell_volume
        session = session or self._session_for(symbol)
        inflow, outflow, net, buy_volume, sell_volume = _prefer_session(
            inflow, outflow, net, buy_volume, sell_volume, session
        )
        levels = None
        if self._liquidity_engine is not None:
            levels = self._liquidity_engine.observe_market(symbol, merged)
        decision = self._engine.evaluate(
            apply_levels(
                SignalInputs(
                    change_percent=_decimal(merged.get("change_percent")),
                    volume=volume_now,
                    prev_volume=prev,
                    inflow=inflow,
                    outflow=outflow,
                    net_flow=net,
                    buy_volume=buy_volume,
                    sell_volume=sell_volume,
                    price=_optional_decimal(merged.get("price") or merged.get("last_price")),
                    bid=_optional_decimal(merged.get("bid")),
                    ask=_optional_decimal(merged.get("ask")),
                    bid_size=_optional_decimal(merged.get("bid_size")),
                    ask_size=_optional_decimal(merged.get("ask_size")),
                    in_gainers="gainers" in sources,
                    in_volume_leaders="volume" in sources,
                    in_value_leaders="value" in sources,
                    tracked=tracked,
                ),
                levels,
            )
        )
        row = _build_row(
            symbol=symbol,
            name=str(merged.get("name") or (existing.name if existing else "")),
            price=_decimal(merged.get("price")),
            change_percent=_decimal(merged.get("change_percent")),
            volume=volume_now,
            value=_decimal(merged.get("value")),
            inflow=inflow,
            outflow=outflow,
            net=net,
            buy_volume=buy_volume,
            sell_volume=sell_volume,
            decision=decision,
            tracked=tracked,
            sources=sources or (["watchlist"] if tracked else ["quote"]),
            updated_at=_parse_time(merged.get("updated_at")),
        )
        with self._guard:
            self._rows[symbol] = row
            if volume_now > 0:
                self._prev_volume[symbol] = volume_now
            self._updated_at = datetime.now(timezone.utc)
            if decision.unexpected or decision.entry or decision.exit:
                priority = [item for item in self._priority if item != symbol]
                self._priority = [symbol, *priority]
        return row

    def _session_for(self, symbol: str) -> SessionFlow | None:
        if self._liquidity_engine is None:
            return None
        try:
            return self._liquidity_engine.session_snapshot(symbol)
        except Exception:
            return None

    async def _pace(self) -> None:
        if self.cache.cooling_down():
            return
        await asyncio.sleep(self._settings.sahmk_request_gap_seconds)

    async def _fetch_market(
        self,
        client: httpx.AsyncClient,
        key: str,
        url: str,
        headers: dict[str, str],
        params: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, bool]:
        if self.cache.cooling_down():
            cached = self.cache.get_market(key)
            return cached, False
        try:
            response = await client.get(url, headers=headers, params=params)
        except httpx.HTTPError:
            logger.warning("screener network error for %s; using cache", key)
            return self.cache.get_market(key), False
        if response.status_code == 429:
            wait = self.cache.trip_rate_limit(_retry_after(response))
            logger.warning("screener rate limited (HTTP 429) for %s; cooling %.0fs", key, wait)
            return self.cache.get_market(key), False
        if response.status_code >= 400:
            logger.warning("screener HTTP %s for %s", response.status_code, key)
            return self.cache.get_market(key), False
        payload = _response_json(response)
        if not isinstance(payload, dict):
            return self.cache.get_market(key), False
        self.cache.put_market(key, payload)
        return payload, True


def _build_row(
    *,
    symbol: str,
    name: str,
    price: Decimal,
    change_percent: Decimal,
    volume: Decimal,
    value: Decimal,
    inflow: Decimal | None,
    outflow: Decimal | None,
    net: Decimal | None,
    buy_volume: Decimal | None,
    sell_volume: Decimal | None,
    decision: Any,
    tracked: bool,
    sources: list[str],
    updated_at: datetime | None,
) -> ScreenerRow:
    resolved_net = net
    if resolved_net is None and inflow is not None and outflow is not None:
        resolved_net = inflow - outflow
    money = Decimal("0.01")
    return ScreenerRow(
        symbol=symbol,
        name=name,
        price=price,
        change_percent=change_percent,
        volume=volume,
        value=value,
        inflow=(inflow or _ZERO).quantize(money),
        outflow=(outflow or _ZERO).quantize(money),
        net_flow=(resolved_net or _ZERO).quantize(money),
        buy_volume=buy_volume or _ZERO,
        sell_volume=sell_volume or _ZERO,
        buy_ratio=decision.buy_ratio,
        sell_ratio=decision.sell_ratio,
        volume_surge=decision.volume_surge,
        score=decision.score,
        entry_signal=decision.entry,
        exit_signal=decision.exit,
        unexpected=decision.unexpected,
        flow_verified=decision.flow_verified,
        tracked=tracked,
        vwap=decision.vwap,
        atr=decision.atr,
        bid=None,
        ask=None,
        book_pressure=decision.book_pressure,
        suggested_entry=decision.suggested_entry,
        suggested_exit=decision.suggested_exit,
        target_price=decision.target_price,
        stop_loss=decision.stop_loss,
        reasons=list(decision.reasons),
        sources=sources,
        updated_at=updated_at,
    )


def _flow_from_raw(
    raw: dict[str, Any],
    existing: ScreenerRow | None,
) -> tuple[Decimal | None, Decimal | None, Decimal | None, Decimal | None, Decimal | None]:
    liquidity = raw.get("liquidity") if isinstance(raw.get("liquidity"), dict) else {}
    inflow = _optional_decimal(
        raw.get("inflow") or raw.get("inflow_value") or liquidity.get("inflow_value")
    )
    outflow = _optional_decimal(
        raw.get("outflow") or raw.get("outflow_value") or liquidity.get("outflow_value")
    )
    net = _optional_decimal(
        raw.get("net_flow") or raw.get("net_value") or liquidity.get("net_value")
    )
    buy_volume = _optional_decimal(
        raw.get("buy_volume") or liquidity.get("inflow_volume") or liquidity.get("buy_volume")
    )
    sell_volume = _optional_decimal(
        raw.get("sell_volume") or liquidity.get("outflow_volume") or liquidity.get("sell_volume")
    )
    if inflow is None and existing and existing.flow_verified:
        return (
            existing.inflow,
            existing.outflow,
            existing.net_flow,
            existing.buy_volume if existing.buy_volume else buy_volume,
            existing.sell_volume if existing.sell_volume else sell_volume,
        )
    return inflow, outflow, net, buy_volume, sell_volume


def _prefer_session(
    inflow: Decimal | None,
    outflow: Decimal | None,
    net: Decimal | None,
    buy_volume: Decimal | None,
    sell_volume: Decimal | None,
    session: SessionFlow | None,
) -> tuple[Decimal | None, Decimal | None, Decimal | None, Decimal | None, Decimal | None]:
    if session is None:
        return inflow, outflow, net, buy_volume, sell_volume
    has_quote_flow = inflow is not None or outflow is not None or net is not None
    if not has_quote_flow and (session.inflow or session.outflow):
        inflow = session.inflow
        outflow = session.outflow
        net = session.net_flow
    if buy_volume is None and (session.buy_volume or session.sell_volume):
        buy_volume = session.buy_volume
        sell_volume = session.sell_volume
    return inflow, outflow, net, buy_volume, sell_volume


def _flatten_quote(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    merged = {**data, **{key: value for key, value in payload.items() if key != "data"}}
    liquidity = merged.get("liquidity")
    if not isinstance(liquidity, dict):
        nested = data.get("liquidity") if isinstance(data.get("liquidity"), dict) else {}
        liquidity = nested
    return merged, liquidity if isinstance(liquidity, dict) else {}


def _merge_movers(target: dict[str, dict[str, Any]], rows: list[Any], source: str) -> None:
    for item in rows:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        current = target.setdefault(symbol, dict(item))
        current.update({key: value for key, value in item.items() if value is not None})
        sources = set(current.get("sources") or [])
        sources.add(source)
        current["sources"] = sources
        current["symbol"] = symbol


def _list_from(payload: dict[str, Any] | None, key: str) -> list[Any]:
    if not payload:
        return []
    rows = payload.get(key) or payload.get("stocks") or payload.get("gainers") or []
    return rows if isinstance(rows, list) else []


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


def _decimal(value: Any) -> Decimal:
    optional = _optional_decimal(value)
    return optional if optional is not None else _ZERO


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None
