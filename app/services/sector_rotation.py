from __future__ import annotations

from typing import Any
from urllib.parse import unquote

import pandas as pd

STATUS_LEADER = "تدفق سيولة قوي (قائد السوق) 🚀"
STATUS_ACCUMULATION = "مرحلة تجميع وهدوء إيجابي 📈"
STATUS_OUTFLOW = "خروج سيولة / ضغط بيعي ⚠️"

SAMPLE_SECTOR_TAPE: list[dict[str, Any]] = [
    {"symbol": "1120", "name": "الراجحي", "sector": "المصارف", "price_change_pct": 1.8, "volume": 8_200_000, "value_traded": 640_000_000, "net_flow": 85_000_000},
    {"symbol": "1180", "name": "الأهلي", "sector": "المصارف", "price_change_pct": 0.9, "volume": 6_100_000, "value_traded": 410_000_000, "net_flow": 22_000_000},
    {"symbol": "2222", "name": "أرامكو السعودية", "sector": "الطاقة", "price_change_pct": 0.4, "volume": 12_400_000, "value_traded": 1_150_000_000, "net_flow": 48_000_000},
    {"symbol": "2380", "name": "البتروكيماويات", "sector": "الطاقة", "price_change_pct": -0.6, "volume": 3_200_000, "value_traded": 95_000_000, "net_flow": -18_000_000},
    {"symbol": "2010", "name": "سابك", "sector": "المواد الأساسية", "price_change_pct": -1.4, "volume": 4_800_000, "value_traded": 210_000_000, "net_flow": -62_000_000},
    {"symbol": "1211", "name": "معادن", "sector": "المواد الأساسية", "price_change_pct": 2.1, "volume": 5_500_000, "value_traded": 280_000_000, "net_flow": 31_000_000},
]

# Sample used when no live TASI tape is available (banks + energy).
DEMO_TASI_SECTOR_TAPE: list[dict[str, Any]] = [
    {"symbol": "1120", "name": "الراجحي", "sector": "البنوك", "price_change_pct": 1.5, "volume": 5_000_000, "value_traded": 450_000_000},
    {"symbol": "1180", "name": "الأهلي", "sector": "البنوك", "price_change_pct": 0.8, "volume": 3_000_000, "value_traded": 250_000_000},
    {"symbol": "2222", "name": "أرامكو السعودية", "sector": "الطاقة", "price_change_pct": -0.2, "volume": 12_000_000, "value_traded": 380_000_000},
    {"symbol": "2380", "name": "بترورابغ", "sector": "الطاقة", "price_change_pct": 2.1, "volume": 8_000_000, "value_traded": 110_000_000},
]


class SectorRotationEngine:
    def __init__(self, market_data: list[dict[str, Any]]):
        """
        تستقبل بيانات الشركات مع اسم القطاع، التغير السعري، وحجم التداول
        ['symbol', 'name', 'sector', 'price_change_pct', 'volume', 'value_traded']
        """
        self.df = pd.DataFrame(list(market_data or []))

    def analyze_sectors(self) -> list[dict[str, Any]]:
        if self.df.empty:
            return []

        frame = self.df.copy()
        if "sector" not in frame.columns:
            frame["sector"] = "أخرى"
        frame["sector"] = frame["sector"].fillna("أخرى").replace("", "أخرى")
        for column in ("price_change_pct", "volume", "value_traded", "net_flow"):
            if column not in frame.columns:
                frame[column] = 0.0
            frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
        if "net_flow" not in self.df.columns or frame["net_flow"].abs().sum() == 0:
            frame["net_flow"] = frame["value_traded"] * (frame["price_change_pct"] / 100.0)

        sector_summary = (
            frame.groupby("sector", dropna=False)
            .agg(
                total_value_traded=("value_traded", "sum"),
                avg_price_change=("price_change_pct", "mean"),
                total_volume=("volume", "sum"),
                net_flow=("net_flow", "sum"),
                companies_count=("symbol", "count"),
            )
            .reset_index()
        )
        mean_value = float(sector_summary["total_value_traded"].mean() or 0.0)
        value_factor = (
            sector_summary["total_value_traded"] / mean_value if mean_value else 1.0
        )
        sector_summary["sector_momentum_score"] = (
            sector_summary["avg_price_change"] * 0.5 + value_factor * 0.5
        )
        sector_summary = sector_summary.sort_values(
            by=["sector_momentum_score", "net_flow"],
            ascending=[False, False],
        ).reset_index(drop=True)
        sector_summary.insert(0, "rank", range(1, len(sector_summary) + 1))
        sector_summary["status"] = sector_summary["sector_momentum_score"].map(_status_for)
        return [_native_record(row) for row in sector_summary.to_dict(orient="records")]

    def ranked_payload(self) -> dict[str, Any]:
        leaders = self.analyze_sectors()
        laggards = list(reversed(leaders))
        for index, row in enumerate(laggards, start=1):
            row = dict(row)
            row["rank_asc"] = index
            laggards[index - 1] = row
        return {
            "success": True,
            "total_sectors": len(leaders),
            "leaders": leaders,
            "laggards": laggards,
            "data": leaders,
            "sectors": leaders,
        }


def rows_from_screener(screener: Any) -> list[dict[str, Any]]:
    from app.services.shariah import sector_for

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    tape = []
    all_rows = getattr(screener, "all_rows", None)
    if callable(all_rows):
        tape.extend(all_rows())
    snapshot = getattr(screener, "snapshot", None)
    if callable(snapshot):
        shot = snapshot()
        tape.extend(getattr(shot, "watchlist", []) or [])
        tape.extend(getattr(shot, "radar", []) or [])
    for row in tape:
        symbol = str(getattr(row, "symbol", "") or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        rows.append(
            {
                "symbol": symbol,
                "name": str(getattr(row, "name", "") or symbol),
                "sector": sector_for(symbol),
                "price_change_pct": float(getattr(row, "change_percent", 0) or 0),
                "volume": float(getattr(row, "volume", 0) or 0),
                "value_traded": float(getattr(row, "value", 0) or 0),
                "net_flow": float(getattr(row, "net_flow", 0) or 0),
                "inflow": float(getattr(row, "inflow", 0) or 0),
                "outflow": float(getattr(row, "outflow", 0) or 0),
            }
        )
    return rows


def companies_for_sector(
    sector_name: str,
    screener: Any = None,
    live_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    requested = unquote(sector_name or "").strip()
    wanted = _canonical_sector(requested)
    live: dict[str, dict[str, Any]] = {}
    for row in live_rows or []:
        symbol = str(row.get("symbol") or "").strip().upper()
        if symbol:
            live[symbol] = dict(row)
    for row in rows_from_screener(screener):
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        current = live.get(symbol, {})
        live[symbol] = {**current, **{key: value for key, value in row.items() if value not in (None, "")}}
    companies: list[dict[str, Any]] = []
    seen: set[str] = set()

    from app.services.shariah import company_name_for, compliance_universe, is_prohibited, sector_for

    for item in compliance_universe():
        symbol = str(item.get("symbol") or "").strip().upper()
        if not symbol or symbol in seen or is_prohibited(symbol):
            continue
        sector = str(item.get("sector") or sector_for(symbol) or "أخرى").strip() or "أخرى"
        if not _sectors_match(sector, wanted):
            continue
        seen.add(symbol)
        companies.append(
            _company_record(
                symbol=symbol,
                name=company_name_for(symbol) or str(item.get("companyNameAr") or symbol),
                sector=sector,
                live=live.get(symbol),
            )
        )

    companies.sort(key=lambda item: abs(float(item.get("net_flow") or 0)), reverse=True)
    return {
        "success": True,
        "sector": requested or wanted,
        "total_companies": len(companies),
        "companies": companies,
    }


def _company_record(
    *,
    symbol: str,
    name: str,
    sector: str,
    live: dict[str, Any] | None,
) -> dict[str, Any]:
    live_row = dict(live or {})
    change = _first_metric(live_row.get("price_change_pct"))
    volume = _first_metric(live_row.get("volume"))
    value = _first_metric(live_row.get("value_traded"))
    price = _first_metric(live_row.get("last_price"), live_row.get("price"), live_row.get("close"))
    net_flow = _first_metric(live_row.get("net_flow"))
    if net_flow == 0 and value and change:
        net_flow = value * (change / 100.0)
    inflow = _first_metric(live_row.get("inflow"))
    outflow = _first_metric(live_row.get("outflow"))
    if inflow == 0 and outflow == 0 and net_flow:
        inflow = max(net_flow, 0.0)
        outflow = max(-net_flow, 0.0)
    if net_flow > 0:
        flow_status = "تدفق داخل 🚀"
    elif net_flow < 0:
        flow_status = "تدفق خارج ⚠️"
    else:
        flow_status = "توازن"
    return {
        "symbol": symbol,
        "name": name,
        "sector": sector,
        "last_price": round(price, 4) if price else None,
        "price_change_pct": round(change, 4),
        "volume": round(volume, 4),
        "value_traded": round(value, 4),
        "net_flow": round(net_flow, 4),
        "inflow": round(inflow, 4),
        "outflow": round(outflow, 4),
        "flow_status": flow_status,
        "live": live is not None,
    }


def _first_metric(*values: Any) -> float:
    for value in values:
        if value is None or value == "":
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number != 0:
            return number
    return 0.0


def _canonical_sector(name: str) -> str:
    value = (name or "").strip()
    aliases = {
        "البنوك": "المصارف",
        "Banks": "المصارف",
        "Energy": "الطاقة",
        "Materials": "المواد الأساسية",
    }
    return aliases.get(value, value)


def _sectors_match(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return _canonical_sector(left) == _canonical_sector(right)


def _status_for(score: float) -> str:
    if score > 2.0:
        return STATUS_LEADER
    if score > 0:
        return STATUS_ACCUMULATION
    return STATUS_OUTFLOW


def _native_record(row: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in row.items():
        if value is None or (isinstance(value, float) and pd.isna(value)):
            payload[str(key)] = None
            continue
        if hasattr(value, "item"):
            payload[str(key)] = value.item()
            continue
        payload[str(key)] = value
    payload["rank"] = int(payload.get("rank") or 0)
    payload["companies_count"] = int(payload.get("companies_count") or 0)
    for key in ("total_value_traded", "avg_price_change", "total_volume", "net_flow", "sector_momentum_score"):
        if payload.get(key) is not None:
            payload[key] = round(float(payload[key]), 4)
    return payload
