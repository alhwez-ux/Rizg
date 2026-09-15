"""Read live TASI quotes from TickerChart 1-minute FlatFiles without UI."""

from __future__ import annotations

import json
import logging
import os
import struct
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.models.screener import is_tasi_main_symbol

logger = logging.getLogger(__name__)

_RECORD = struct.Struct("<d8f")
_OLE_EPOCH = datetime(1899, 12, 30)
_CACHE_NAME = "CategoriesAndCompaniesData.json"
_map_key: tuple[str, float] | None = None
_id_to_symbol: dict[str, str] = {}


@dataclass(frozen=True)
class Bar:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None


def tclive_root() -> Path:
    local = str(os.environ.get("LOCALAPPDATA") or "").strip()
    if local:
        return Path(local) / "UniTicker" / "TCLive"
    return Path.home() / "AppData" / "Local" / "UniTicker" / "TCLive"


def collect_live_quotes(root: Path | None = None) -> list[dict[str, Any]]:
    """Return one quote payload per main-market symbol from 1-minute + daily bars."""

    base = root or tclive_root()
    mapping = load_id_to_symbol(base / "Cache" / _CACHE_NAME)
    flat = base / "FlatFiles"
    minute_dir = discover_interval_dir(flat, 60.0) or discover_minute_dir(flat)
    daily_dir = discover_interval_dir(flat, 86_400.0)
    if minute_dir is None or not mapping:
        return []
    dailies = _index_last_bars(daily_dir, mapping) if daily_dir is not None else {}
    quotes: list[dict[str, Any]] = []
    for path in minute_dir.glob("*.dat"):
        symbol = mapping.get(path.stem)
        if not symbol:
            continue
        bar = read_last_bar(path)
        if bar is None or bar.close <= 0:
            continue
        daily_last, daily_prev = dailies.get(symbol, (None, None))
        prev_close = None
        if daily_last is not None and daily_prev is not None and daily_last.time.date() >= bar.time.date():
            prev_close = daily_prev.close
        elif daily_last is not None:
            prev_close = daily_last.close
        volume = _as_shares((daily_last.volume if daily_last else None) or bar.volume)
        change = None
        if prev_close and prev_close > 0:
            change = round((bar.close - prev_close) / prev_close * 100.0, 4)
        value = round(volume * bar.close, 2) if volume else None
        net_flow = round(value * change / 100.0, 2) if value is not None and change is not None else None
        session = daily_last if daily_last is not None else bar
        row: dict[str, Any] = {
            "type": "quote",
            "symbol": symbol,
            "price": round(bar.close, 4),
            "time": bar.time.isoformat(timespec="seconds"),
            "open": round(session.open, 4),
            "high": round(session.high, 4),
            "low": round(session.low, 4),
        }
        if prev_close:
            row["prev_close"] = round(prev_close, 4)
        if volume:
            row["session_volume"] = volume
        if value is not None:
            row["value"] = value
            row["value_traded"] = value
        if change is not None:
            row["change_percent"] = change
        if net_flow is not None:
            row["net_flow"] = net_flow
        quotes.append(row)
    quotes.sort(key=lambda item: str(item["symbol"]))
    return quotes


def discover_minute_dir(flat_root: Path) -> Path | None:
    return discover_interval_dir(flat_root, 60.0)


def discover_interval_dir(flat_root: Path, target_seconds: float) -> Path | None:
    if not flat_root.is_dir():
        return None
    best: Path | None = None
    best_score = 10_000.0
    for interval_dir in flat_root.iterdir():
        if not interval_dir.is_dir():
            continue
        sample = next(interval_dir.rglob("*.dat"), None)
        if sample is None:
            continue
        delta = bar_seconds(sample)
        if delta is None or delta <= 0:
            continue
        score = abs(delta - target_seconds)
        if score < best_score:
            best_score = score
            best = sample.parent
    return best


def bar_seconds(path: Path) -> float | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) < _RECORD.size * 2:
        return None
    first = _RECORD.unpack_from(data, 0)[0]
    second = _RECORD.unpack_from(data, _RECORD.size)[0]
    return abs(second - first) * 86400.0


def read_last_bar(path: Path) -> Bar | None:
    bars = read_last_bars(path, 1)
    return bars[-1] if bars else None


def read_last_bars(path: Path, count: int) -> list[Bar]:
    need = max(1, count)
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            take = min(size // _RECORD.size, need)
            if take <= 0:
                return []
            handle.seek(size - take * _RECORD.size)
            raw = handle.read(take * _RECORD.size)
    except OSError:
        return []
    bars: list[Bar] = []
    for offset in range(0, len(raw) - _RECORD.size + 1, _RECORD.size):
        ole, open_, high, low, close, _oi, volume_raw, _junk, _trades = _RECORD.unpack_from(raw, offset)
        try:
            moment = _OLE_EPOCH + timedelta(days=float(ole))
        except (OverflowError, ValueError, OSError):
            continue
        bars.append(
            Bar(
                time=moment,
                open=float(open_),
                high=float(high),
                low=float(low),
                close=float(close),
                volume=_as_shares(volume_raw),
            )
        )
    return bars


def load_id_to_symbol(cache_path: Path) -> dict[str, str]:
    global _map_key, _id_to_symbol
    try:
        mtime = cache_path.stat().st_mtime
        key = (str(cache_path.resolve()), mtime)
    except OSError:
        return _id_to_symbol
    if key == _map_key and _id_to_symbol:
        return _id_to_symbol
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        logger.warning("cannot read UniTicker company cache %s", cache_path)
        return _id_to_symbol
    mapping: dict[str, str] = {}
    companies = payload.get("Companies") if isinstance(payload, dict) else payload
    if not isinstance(companies, list):
        return _id_to_symbol
    for row in companies:
        if not isinstance(row, dict):
            continue
        if str(row.get("MarketAbrv") or "").upper() != "TAD":
            continue
        ticker = str(row.get("TickerID") or "").strip()
        company_id = str(row.get("ID") or "").strip()
        if not company_id or not is_tasi_main_symbol(ticker):
            continue
        mapping[company_id] = ticker
    _id_to_symbol = mapping
    _map_key = key
    return mapping


def _index_last_bars(folder: Path, mapping: dict[str, str]) -> dict[str, tuple[Bar | None, Bar | None]]:
    indexed: dict[str, tuple[Bar | None, Bar | None]] = {}
    for path in folder.glob("*.dat"):
        symbol = mapping.get(path.stem)
        if not symbol:
            continue
        bars = read_last_bars(path, 2)
        if not bars:
            continue
        last = bars[-1]
        prev = bars[-2] if len(bars) > 1 else None
        indexed[symbol] = (last, prev)
    return indexed


def _as_shares(raw: float | None) -> float | None:
    try:
        number = float(raw) if raw is not None else 0.0
    except (TypeError, ValueError):
        return None
    if number != number or number <= 0:
        return None
    if number < 500:
        return number * 1_000_000.0
    return number
