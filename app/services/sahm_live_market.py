from __future__ import annotations

import logging
from typing import Any

from app.core.exceptions import SahmApiError
from app.services.company_ranker import MAJOR_TASI_COMPANIES, CompanyRankingEngine
from app.services.sahm_data_provider import SahmDataProvider, normalize_sahm_symbol
from app.services.shariah import company_name_for, is_prohibited, sector_for

logger = logging.getLogger(__name__)

_QUOTE_FILL_LIMIT = 24


async def live_sector_rows(provider: SahmDataProvider) -> list[dict[str, Any]]:
    """Build the TASI sector tape from live Sahm market boards + company directory."""

    if not provider.enabled:
        raise SahmApiError(
            "SAHM_API_KEY is missing; cannot fetch sector rotation",
            status_code=503,
            error_code="sahm_not_configured",
        )
    directory = await _directory_by_symbol(provider)
    board = await provider.fetch_market_board()
    movers = _merge_board(board)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for symbol, quote in movers.items():
        if symbol in seen or is_prohibited(symbol):
            continue
        seen.add(symbol)
        profile = directory.get(symbol) or _major_profile(symbol)
        rows.append(_sector_row(symbol, quote, profile))
    missing = [
        item["symbol"]
        for item in MAJOR_TASI_COMPANIES
        if item["symbol"] not in seen and not is_prohibited(item["symbol"])
    ]
    extra = await provider.fetch_quotes_for(missing, limit=_QUOTE_FILL_LIMIT)
    for symbol, payload in extra.items():
        if symbol in seen or is_prohibited(symbol):
            continue
        seen.add(symbol)
        profile = directory.get(symbol) or _major_profile(symbol)
        rows.append(_sector_row(symbol, _flatten_quote(payload), profile))
    return rows


async def live_ranking_rows(provider: SahmDataProvider) -> list[dict[str, Any]]:
    """Rank major TASI names from live Sahm quotes and company profiles."""

    if not provider.enabled:
        raise SahmApiError(
            "SAHM_API_KEY is missing; cannot fetch ranking matrix",
            status_code=503,
            error_code="sahm_not_configured",
        )
    directory = await _directory_by_symbol(provider)
    board = await provider.fetch_market_board()
    movers = _merge_board(board)
    wanted = [item["symbol"] for item in MAJOR_TASI_COMPANIES if not is_prohibited(item["symbol"])]
    extra = await provider.fetch_quotes_for(
        [symbol for symbol in wanted if symbol not in movers],
        limit=_QUOTE_FILL_LIMIT,
    )
    financials: list[dict[str, Any]] = []
    seen: set[str] = set()
    for symbol in wanted:
        profile = directory.get(symbol) or _major_profile(symbol)
        quote = movers.get(symbol) or _flatten_quote(extra.get(symbol) or {})
        if not quote and not profile:
            continue
        seen.add(symbol)
        financials.append(_ranking_row(symbol, quote, profile))
    for symbol, quote in movers.items():
        if symbol in seen or is_prohibited(symbol):
            continue
        seen.add(symbol)
        profile = directory.get(symbol) or _major_profile(symbol)
        financials.append(_ranking_row(symbol, quote, profile))
    return CompanyRankingEngine(financials).get_ranked_payload()


def overlay_quote_on_report(report: dict[str, Any], quote_payload: dict[str, Any]) -> dict[str, Any]:
    """Fill radar zeros with the live Sahm quote when candles omit traded value."""

    quote = _flatten_quote(quote_payload)
    if not quote:
        return report
    merged = dict(report)
    if not merged.get("last_price"):
        merged["last_price"] = quote.get("price")
    if not merged.get("change_percent"):
        merged["change_percent"] = quote.get("change_percent")
    merged["volume"] = quote.get("volume") or merged.get("volume") or 0
    merged["value_traded"] = quote.get("value_traded") or merged.get("value_traded") or 0
    merged["live_quote"] = True
    return merged


async def _directory_by_symbol(provider: SahmDataProvider) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    try:
        companies = await provider.fetch_company_directory()
    except SahmApiError as exc:
        logger.warning("sahm company directory unavailable: %s", exc.message)
        return mapping
    for item in companies:
        try:
            symbol = normalize_sahm_symbol(str(item.get("symbol") or ""))
        except Exception:
            continue
        mapping[symbol] = item
    return mapping


def _merge_board(board: dict[str, Any]) -> dict[str, dict[str, Any]]:
    movers: dict[str, dict[str, Any]] = {}
    for key in ("gainers", "volume", "value"):
        rows = board.get(key) or []
        if not isinstance(rows, list):
            continue
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            quote = _flatten_quote(raw)
            symbol = str(quote.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            current = movers.setdefault(symbol, {"symbol": symbol, "sources": []})
            current.update({key: value for key, value in quote.items() if value not in (None, "")})
            sources = current.setdefault("sources", [])
            if key not in sources:
                sources.append(key)
    return movers


def _flatten_quote(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict) or not payload:
        return {}
    nested = payload.get("data")
    data = nested if isinstance(nested, dict) else payload
    symbol = str(data.get("symbol") or payload.get("symbol") or "").strip().upper()
    price = _num(data.get("price") or data.get("last") or data.get("close") or data.get("last_price"))
    change = _num(
        data.get("change_percent")
        or data.get("changePct")
        or data.get("pct_change")
        or data.get("profit_growth")
    )
    volume = _num(data.get("volume") or data.get("quantity") or data.get("qty"))
    value = _num(
        data.get("value")
        or data.get("value_traded")
        or data.get("traded_value")
        or data.get("turnover")
    )
    pe = _num(data.get("pe_ratio") or data.get("pe") or data.get("p_e"))
    dividend = _num(data.get("dividend_yield") or data.get("dy") or data.get("yield"))
    roe = _num(data.get("roe"))
    roa = _num(data.get("roa"))
    eps = _num(data.get("eps") or data.get("earnings_per_share"))
    market_cap = _num(data.get("market_cap") or data.get("marketCap"))
    net_income = _num(data.get("net_income") or data.get("netIncome"))
    if net_income is None and eps is not None and market_cap is not None and price not in (None, 0):
        net_income = eps * (market_cap / price)
    name = str(data.get("name") or data.get("name_ar") or data.get("nameAr") or payload.get("name") or "").strip()
    sector = str(data.get("sector") or payload.get("sector") or "").strip()
    return {
        "symbol": symbol,
        "name": name,
        "sector": sector,
        "price": price,
        "change_percent": change,
        "volume": volume,
        "value_traded": value,
        "pe_ratio": pe,
        "dividend_yield": dividend,
        "roe": roe,
        "roa": roa,
        "eps": eps,
        "market_cap": market_cap,
        "net_income": net_income,
    }


def _sector_row(symbol: str, quote: dict[str, Any], profile: dict[str, Any] | None) -> dict[str, Any]:
    change = float(quote.get("change_percent") or 0)
    value = float(quote.get("value_traded") or 0)
    volume = float(quote.get("volume") or 0)
    net_flow = value * (change / 100.0) if value else 0.0
    name = (
        str(quote.get("name") or "").strip()
        or company_name_for(symbol)
        or str((profile or {}).get("name_ar") or (profile or {}).get("name") or symbol)
    )
    sector = (
        str(quote.get("sector") or "").strip()
        or str((profile or {}).get("sector") or "").strip()
        or sector_for(symbol)
        or "أخرى"
    )
    return {
        "symbol": symbol,
        "name": name,
        "sector": sector,
        "price_change_pct": round(change, 4),
        "volume": round(volume, 4),
        "value_traded": round(value, 4),
        "net_flow": round(net_flow, 4),
        "inflow": round(max(net_flow, 0.0), 4),
        "outflow": round(max(-net_flow, 0.0), 4),
        "live": True,
    }


def _ranking_row(symbol: str, quote: dict[str, Any], profile: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(profile or {})
    merged.update({key: value for key, value in (quote or {}).items() if value not in (None, "")})
    name = (
        str(merged.get("name") or "").strip()
        or company_name_for(symbol)
        or str(merged.get("name_ar") or symbol)
    )
    return {
        "symbol": symbol,
        "name": name,
        "profit_growth": merged.get("change_percent") or merged.get("profit_growth"),
        "dividend_yield": merged.get("dividend_yield"),
        "roe": merged.get("roe"),
        "roa": merged.get("roa"),
        "pe_ratio": merged.get("pe_ratio"),
        "net_income": merged.get("net_income"),
        "volume": merged.get("volume"),
        "value_traded": merged.get("value_traded"),
        "last_price": merged.get("price"),
        "live": True,
    }


def _major_profile(symbol: str) -> dict[str, Any] | None:
    for item in MAJOR_TASI_COMPANIES:
        if item["symbol"] == symbol:
            return dict(item)
    return None


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or abs(number) == float("inf"):
        return None
    return number
